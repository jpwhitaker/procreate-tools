#!/usr/bin/env python3
"""Extract embedded PNG previews from .procreate files without changing them.

Python 3.11+, standard library only. Works offline. These are embedded previews,
not full-resolution renders. Matching existing PNGs are skipped; different files
are never overwritten. Subfolder structure is preserved with --recursive.
"""

import argparse
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib

MEMBER = "quicklook/thumbnail.png"
MAX_BYTES = 32 * 1024 * 1024


def png_dimensions(data):
    """Check PNG framing and CRCs without decoding or altering its pixels."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Embedded preview is not a PNG")
    pos = 8
    dimensions = None
    image_data = False
    while pos + 12 <= len(data):
        length = struct.unpack_from(">I", data, pos)[0]
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("Truncated PNG chunk")
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack_from(">I", data, pos + 8 + length)[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError("PNG chunk checksum failed")
        if pos == 8:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG header missing or malformed")
            dimensions = struct.unpack_from(">II", body)
            if not all(dimensions) or dimensions[0] * dimensions[1] > 100_000_000:
                raise ValueError("Invalid or unusually large preview dimensions")
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG header")
        if kind == b"IDAT":
            image_data = True
        if kind == b"IEND":
            if length or not image_data or end != len(data):
                raise ValueError("Malformed PNG end")
            return dimensions
        pos = end
    raise ValueError("PNG end marker missing")


def read_preview(source):
    with zipfile.ZipFile(source) as archive:
        candidates = [i for i in archive.infolist() if i.filename.lower() == MEMBER]
        if len(candidates) != 1:
            raise ValueError("Expected one QuickLook/Thumbnail.png; found " + str(len(candidates)))
        info = candidates[0]
        if info.file_size > MAX_BYTES:
            raise ValueError("Embedded preview exceeds 32 MB limit")
        with archive.open(info) as f:
            data = f.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or len(data) != info.file_size:
            raise ValueError("Invalid preview size")
    return data, png_dimensions(data)


def write_new_or_identical(destination, data):
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = destination.open("xb")
    except FileExistsError:
        if destination.is_file() and destination.stat().st_size == len(data) and destination.read_bytes() == data:
            return "unchanged"
        raise FileExistsError(f"Refusing to overwrite different content: {destination}")
    try:
        with f:
            f.write(data)
    except BaseException:
        destination.unlink()
        raise
    return "created"


def extract(source, destination):
    data, dimensions = read_preview(source)
    status = write_new_or_identical(destination, data)
    return {"source": str(source), "preview": str(destination), "status": status,
            "width": dimensions[0], "height": dimensions[1], "bytes": len(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="One .procreate file or a folder")
    parser.add_argument("--output", "-o", type=Path, required=True, help="Destination folder for PNG previews")
    parser.add_argument("--recursive", "-r", action="store_true", help="Include subfolders and preserve their structure")
    parser.add_argument("--report", type=Path, help="Optional new JSON report file; existing reports are not overwritten")
    args = parser.parse_args()
    source = args.input.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if source.is_file() and source.suffix.lower() == ".procreate":
        files, base = [source], source.parent
    elif source.is_dir():
        base = source
        iterator = source.rglob("*") if args.recursive else source.iterdir()
        files = sorted(p for p in iterator if p.is_file() and p.suffix.lower() == ".procreate")
    else:
        parser.error("Input must be a .procreate file or an existing folder")
    if not files:
        parser.error("No .procreate files found (try --recursive for subfolders)")
    results, errors = [], []
    for file in files:
        destination = output / file.relative_to(base).with_suffix(".png")
        try:
            results.append(extract(file, destination))
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, EOFError, NotImplementedError) as e:
            errors.append({"source": str(file), "error": str(e)})
            print(f"ERROR {file.name}: {e}", file=sys.stderr)
    report = {"created": sum(r["status"] == "created" for r in results),
              "unchanged": sum(r["status"] == "unchanged" for r in results),
              "failed": len(errors), "previews": results, "errors": errors}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"{report['created']} PNGs created; {report['unchanged']} unchanged; {report['failed']} failed. Output: {output}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
