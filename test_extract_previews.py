import struct
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from extract_previews import extract, png_dimensions


def tiny_png():
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


class PreviewTests(unittest.TestCase):
    def test_preserves_png_and_source_and_can_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp) / "art.procreate", Path(tmp) / "preview.png"
            data = tiny_png()
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("QuickLook/Thumbnail.png", data)
                z.writestr("layers/untouched", b"layer data")
            before = source.read_bytes()
            self.assertEqual(extract(source, dest)["status"], "created")
            self.assertEqual(dest.read_bytes(), data)
            self.assertEqual(extract(source, dest)["status"], "unchanged")
            self.assertEqual(source.read_bytes(), before)
            dest.write_bytes(b"someone else's file")
            with self.assertRaises(FileExistsError):
                extract(source, dest)
            self.assertEqual(dest.read_bytes(), b"someone else's file")

    def test_bad_png_is_rejected(self):
        data = bytearray(tiny_png())
        data[20] ^= 1
        with self.assertRaises(ValueError):
            png_dimensions(bytes(data))
        with self.assertRaises(ValueError):
            png_dimensions(tiny_png()[:-12])

    def test_missing_preview_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, dest = Path(tmp) / "art.procreate", Path(tmp) / "preview.png"
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("Document.archive", b"metadata")
            with self.assertRaises(ValueError):
                extract(source, dest)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
