#!/usr/bin/env python3
"""Inspect completed Finder backups and reconstruct selected Procreate archives.

Only reads the source backup. Output archives retain original document bytes.
Reconstructed archives still require an import test in Procreate.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import sqlite3
import stat
import zipfile
from collections import defaultdict
from datetime import datetime, timezone

DOMAIN = "AppDomain-au.com.savageinteractive.procreate"


def archive_root(data):
    value = plistlib.loads(data)
    objects = value["$objects"]
    root = objects[value["$top"]["root"].data]
    return root, objects


def resolve(value, objects):
    if isinstance(value, plistlib.UID):
        return None if value.data == 0 else objects[value.data]
    return value


def open_backup(path):
    path = path.expanduser().resolve()
    status = plistlib.loads((path / "Status.plist").read_bytes())
    manifest = plistlib.loads((path / "Manifest.plist").read_bytes())
    if status.get("SnapshotState") != "finished":
        raise ValueError("Backup is not marked finished; wait for Finder to finish.")
    if manifest.get("IsEncrypted"):
        raise ValueError("Encrypted backups require a separate decryption step.")
    if (path / "Manifest.db-wal").exists():
        raise ValueError("Manifest has a WAL file; cannot safely read as immutable.")
    connection = sqlite3.connect(
        (path / "Manifest.db").as_uri() + "?mode=ro&immutable=1", uri=True
    )
    return path, connection


def payload(backup, file_id):
    if not re.fullmatch(r"[0-9a-f]{40}", file_id):
        raise ValueError("Invalid backup file ID")
    return backup / file_id[:2] / file_id


def inventory(backup, connection):
    docs = {}
    for file_id, relative in connection.execute(
        "SELECT fileID, relativePath FROM Files WHERE domain=? AND flags=1 "
        "AND relativePath LIKE '%/Document.archive'", (DOMAIN,)
    ):
        root_path = str(PurePosixPath(relative).parent)
        root, objects = archive_root(payload(backup, file_id).read_bytes())
        name = resolve(root.get("name"), objects) or "Untitled Artwork"
        if isinstance(name, dict) and "NS.string" in name:
            name = resolve(name["NS.string"], objects)
        if not isinstance(name, str):
            raise ValueError(f"Unsupported canvas name representation: {root_path}")
        layers = resolve(root.get("layers"), objects) or {}
        docs[root_path] = {
            "id": PurePosixPath(root_path).name,
            "path": root_path,
            "name": name,
            "canvas_size": resolve(root.get("size"), objects),
            "top_level_layer_entries": len(layers.get("NS.objects", [])),
            "video_enabled": resolve(root.get("videoEnabled"), objects),
            "files": 0,
            "bytes": 0,
            "video_files": 0,
            "modified_unix": 0,
        }
    files = defaultdict(list)
    total_bytes = 0
    for file_id, relative, flags, metadata in connection.execute(
        "SELECT fileID, relativePath, flags, file FROM Files WHERE domain=?", (DOMAIN,)
    ):
        if flags != 1:
            continue
        meta, objects = archive_root(metadata)
        size = resolve(meta.get("Size"), objects) or 0
        modified = resolve(meta.get("LastModified"), objects) or 0
        total_bytes += size
        # Document roots are direct children of Library/Application Support.
        parts = PurePosixPath(relative).parts
        root_path = "/".join(parts[:3])
        if root_path not in docs:
            continue
        member = "/".join(parts[3:])
        if not member or ".." in parts or PurePosixPath(relative).is_absolute():
            raise ValueError("Unsafe document path")
        doc = docs[root_path]
        doc["files"] += 1
        doc["bytes"] += size
        doc["modified_unix"] = max(doc["modified_unix"], modified)
        doc["video_files"] += member.startswith("video/")
        files[doc["id"]].append((file_id, member, size, modified))
    result = sorted(docs.values(), key=lambda x: (-x["modified_unix"], x["id"]))
    for doc in result:
        doc["modified_utc"] = datetime.fromtimestamp(
            doc["modified_unix"], timezone.utc
        ).isoformat()
    return {"domain": DOMAIN, "canvas_count": len(result),
            "app_regular_file_bytes": total_bytes,
            "canvas_bytes": sum(d["bytes"] for d in result),
            "canvases": result}, files


def extract(backup, doc, entries, output, receipt_output=None):
    receipt_output = receipt_output or output
    if any(p.resolve().is_relative_to(backup.resolve()) for p in (output, receipt_output)):
        raise ValueError("Output must be outside the source backup")
    output.mkdir(parents=True, exist_ok=True)
    receipt_output.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[\x00-\x1f/\\:*?"<>|]', "_", doc["name"]).strip(". ")
    name = (name or "Untitled Artwork")[:80]
    while len(name.encode("utf-8")) > 160:
        name = name[:-1]
    destination = output / f"{name}--{doc['id']}.procreate"
    temporary = destination.with_suffix(".procreate.partial")
    receipt = receipt_output / destination.with_suffix(".verification.json").name
    if destination.exists() or temporary.exists() or receipt.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    if shutil.disk_usage(output).free < doc["bytes"] * 1.05 + 2_000_000_000:
        raise ValueError("Insufficient free space with a 2 GB reserve")
    seen = set()
    for file_id, member, size, _ in entries:
        parts = PurePosixPath(member)
        if parts.is_absolute() or ".." in parts.parts or not member:
            raise ValueError("Unsafe archive member path")
        source = payload(backup, file_id)
        info = source.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            raise ValueError(f"Missing, irregular, or size-mismatched payload: {member}")
        if member in seen:
            raise ValueError(f"Duplicate archive member: {member}")
        seen.add(member)
    if "Document.archive" not in seen:
        raise ValueError("Document.archive missing")
    hashes = {}
    with zipfile.ZipFile(temporary, "x", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for file_id, member, size, modified in sorted(entries, key=lambda x: x[1]):
            date = datetime.fromtimestamp(max(315532800, modified), timezone.utc)
            info = zipfile.ZipInfo(member, date.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.file_size = size
            digest = hashlib.sha256()
            with payload(backup, file_id).open("rb") as src, z.open(info, "w", force_zip64=True) as dst:
                while chunk := src.read(1024 * 1024):
                    digest.update(chunk)
                    dst.write(chunk)
            hashes[member] = digest.hexdigest()
    with zipfile.ZipFile(temporary) as z:
        if set(z.namelist()) != seen:
            raise ValueError("Archive member list mismatch")
        for member, expected in hashes.items():
            digest = hashlib.sha256()
            with z.open(member) as src:
                while chunk := src.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError(f"Archive content verification failed: {member}")
    # Hard link promotes without overwriting an existing destination.
    os.link(temporary, destination)
    temporary.unlink()
    os.utime(destination, (doc["modified_unix"], doc["modified_unix"]))
    with receipt.open("x") as f:
        json.dump({"backup": str(backup), "canvas": doc,
                   "file": str(destination), "archive_bytes": destination.stat().st_size,
                   "all_members_sha256_verified": True,
                   "procreate_import_test": "pending", "member_sha256": hashes}, f, indent=2)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--extract", nargs="*", default=[], metavar="CANVAS_ID")
    parser.add_argument("--output", type=Path, default=Path("samples"))
    args = parser.parse_args()
    backup, connection = open_backup(args.backup)
    report, files = inventory(backup, connection)
    connection.close()
    report["backup"] = str(backup)
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(report, indent=2)
    with args.catalog.open("x") as f:
        f.write(serialized)
    print(f"{report['canvas_count']} canvases, {report['canvas_bytes']/1e9:.2f} GB", flush=True)
    by_id = {d["id"]: d for d in report["canvases"]}
    unknown = set(args.extract) - by_id.keys()
    if unknown:
        raise ValueError(f"Unknown canvas IDs: {sorted(unknown)}")
    for identifier in args.extract:
        print(extract(backup, by_id[identifier], files[identifier], args.output), flush=True)


if __name__ == "__main__":
    main()
