#!/usr/bin/env python3
"""Archive all canvases from a completed Finder backup into a dated folder.

Run after Finder finishes backing up. No packages required. This does not start
device backups or install a schedule. Existing snapshots are never overwritten.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import zipfile
from datetime import datetime, timezone

from procreate_backup import open_backup, inventory, extract, payload



def digest_file(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def source_signature(backup):
    result = {}
    for name in ("Status.plist", "Manifest.plist", "Manifest.db"):
        s = (backup / name).stat()
        result[name] = [s.st_ino, s.st_size, s.st_mtime_ns]
    return result


def assert_unchanged(backup, signature):
    if source_signature(backup) != signature:
        raise ValueError("Source backup changed during extraction; rerun after Finder finishes")


def write_json_new(path, data):
    serialized = json.dumps(data, indent=2)
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x") as f:
        f.write(serialized)
        f.flush()
        os.fsync(f.fileno())
    os.link(temporary, path)
    temporary.unlink()


def verify_previous(backup, doc, entries, directory, receipt_directory=None):
    receipt_directory = receipt_directory or directory
    receipts = list(receipt_directory.glob(f"*--{doc['id']}.verification.json"))
    if not receipts:
        return None
    if len(receipts) != 1:
        raise ValueError(f"Ambiguous receipts for {doc['id']}")
    record = json.loads(receipts[0].read_text())
    if record["canvas"] != doc:
        raise ValueError(f"Canvas changed within the same snapshot: {doc['id']}")
    archive = directory / receipts[0].with_suffix("").with_suffix(".procreate").name
    expected = record["member_sha256"]
    if len(entries) != len(expected) or {e[1] for e in entries} != set(expected):
        raise ValueError("Receipt does not cover all canvas files")
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist()) != len(expected) or set(z.namelist()) != set(expected):
            raise ValueError("Archive member list mismatch")
        for file_id, member, size, _ in entries:
            source = payload(backup, file_id)
            if source.stat().st_size != size or digest_file(source) != expected[member]:
                raise ValueError(f"Source no longer matches receipt: {member}")
            with z.open(member) as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != expected[member]:
                    raise ValueError(f"Archive verification failed: {member}")
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True,
                        help="Folder containing Manifest.db, Manifest.plist, and Status.plist")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "archives")
    args = parser.parse_args()
    backup, connection = open_backup(args.backup)
    signature = source_signature(backup)
    status = plistlib.loads((backup / "Status.plist").read_bytes())
    stamp = status["Date"].strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    output = args.output.expanduser().resolve() / backup.name / stamp
    if output.is_relative_to(backup):
        raise ValueError("Output must be outside the source backup")
    output.mkdir(parents=True, exist_ok=True)
    # Exclusive lock prevents overlapping archive jobs. A crash leaves the lock
    # for inspection, rather than allowing another process to overwrite output.
    lock = output / ".running"
    with lock.open("x") as f:
        f.write(str(os.getpid()))
    try:
        report, files = inventory(backup, connection)
        connection.close()
        assert_unchanged(backup, signature)
        if not report["canvases"]:
            raise ValueError("No Procreate canvases found")
        report["backup"] = str(backup)
        report["source_signature"] = signature
        catalog = output / "catalog.json"
        if catalog.exists():
            if json.loads(catalog.read_text()) != report:
                raise ValueError("Existing snapshot catalog differs from source")
        else:
            write_json_new(catalog, report)
        canvases = output / "canvases"
        canvases.mkdir(exist_ok=True)
        verification = output / "verification"
        verification.mkdir(exist_ok=True)
        # Conservative whole-run estimate; existing completed files need no space.
        needed = sum(d["bytes"] for d in report["canvases"]
                     if not list(verification.glob(f"*--{d['id']}.verification.json")))
        if shutil.disk_usage(output).free < needed * 1.05 + 2_000_000_000:
            raise ValueError("Insufficient free space for library plus 2 GB reserve")
        print(f"Archiving {report['canvas_count']} canvases ({report['canvas_bytes']/1e9:.2f} GB)", flush=True)
        archived = []
        for n, doc in enumerate(report["canvases"], 1):
            assert_unchanged(backup, signature)
            path = verify_previous(backup, doc, files[doc["id"]], canvases, verification)
            reused = path is not None
            if path is None:
                path = extract(backup, doc, files[doc["id"]], canvases, verification)
            assert_unchanged(backup, signature)
            archived.append({"id": doc["id"], "file": str(path.relative_to(output)),
                             "bytes": path.stat().st_size, "sha256": digest_file(path)})
            print(f"{n}/{report['canvas_count']} {'verified existing' if reused else 'extracted'}: {doc['name']}", flush=True)
        assert_unchanged(backup, signature)
        summary = {"completed_utc": datetime.now(timezone.utc).isoformat(),
                   "backup": str(backup), "canvas_count": len(archived),
                   "archive_bytes": sum(a["bytes"] for a in archived),
                   "all_members_sha256_verified_against_backup": True,
                   "archives": archived}
        complete = output / "complete.json"
        if complete.exists():
            if json.loads(complete.read_text())["archives"] != archived:
                raise ValueError("Previously completed snapshot failed comparison")
        else:
            write_json_new(complete, summary)
        print(f"COMPLETE: {len(archived)} canvases, {summary['archive_bytes']/1e9:.2f} GB at {output}", flush=True)
    finally:
        connection.close()
        lock.unlink()


if __name__ == "__main__":
    main()
