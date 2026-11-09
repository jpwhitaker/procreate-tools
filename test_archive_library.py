"""Recovery checks using a small synthetic Finder backup, never the real iPad."""
import hashlib
import json
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from contextlib import closing

from procreate_backup import DOMAIN


def keyed(root, extra=()):
    return plistlib.dumps({"$archiver": "NSKeyedArchiver", "$version": 100000,
                          "$objects": ["$null", root, *extra],
                          "$top": {"root": plistlib.UID(1)}}, fmt=plistlib.FMT_BINARY)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="procreate-recovery-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.backup = self.root / "backup"
        self.backup.mkdir()
        self.output = self.root / "archives"
        (self.backup / "Status.plist").write_bytes(plistlib.dumps({
            "SnapshotState": "finished", "Date": datetime(2026, 11, 9)}))
        (self.backup / "Manifest.plist").write_bytes(plistlib.dumps({"IsEncrypted": False}))
        self.members = {
            "Document.archive": keyed({"name": plistlib.UID(2), "layers": plistlib.UID(3),
                                       "size": "{100, 100}", "videoEnabled": True},
                                      [{"NS.string": "Test Artwork"}, {"NS.objects": []}]),
            "layers/layer.chunk": b"exact layer pixels\x00\xff",
            "video/segment": b"exact time-lapse bytes\x00\xfe",
        }
        with closing(sqlite3.connect(self.backup / "Manifest.db")) as db:
            db.execute("CREATE TABLE Files(fileID TEXT, domain TEXT, relativePath TEXT, flags INT, file BLOB)")
            for member, data in self.members.items():
                relative = f"Library/Application Support/test-canvas/{member}"
                fid = hashlib.sha1((DOMAIN + "-" + relative).encode()).hexdigest()
                p = self.backup / fid[:2] / fid
                p.parent.mkdir(exist_ok=True)
                p.write_bytes(data)
                metadata = keyed({"Size": len(data), "LastModified": 1700000000})
                db.execute("INSERT INTO Files VALUES(?,?,?,?,?)", (fid, DOMAIN, relative, 1, metadata))
            db.commit()

    def run_job(self):
        return subprocess.run([sys.executable, str(Path(__file__).with_name("archive_library.py")),
                               "--backup", str(self.backup), "--output", str(self.output)],
                              capture_output=True, text=True)

    def test_round_trip_and_repeat_preserve_every_byte(self):
        before = {str(p.relative_to(self.backup)): p.read_bytes()
                  for p in self.backup.rglob("*") if p.is_file()}
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        archive, = self.output.rglob("*.procreate")
        with zipfile.ZipFile(archive) as z:
            self.assertEqual({n: z.read(n) for n in z.namelist()}, self.members)
        first = archive.read_bytes()
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verified existing", result.stdout)
        self.assertEqual(archive.read_bytes(), first)
        self.assertEqual(len(list(self.output.rglob("*.procreate"))), 1)
        self.assertEqual(before, {str(p.relative_to(self.backup)): p.read_bytes()
                                 for p in self.backup.rglob("*") if p.is_file()})
        complete, = self.output.rglob("complete.json")
        self.assertEqual(json.loads(complete.read_text())["canvas_count"], 1)

    def test_corrupt_archive_is_rejected_on_repeat(self):
        self.assertEqual(self.run_job().returncode, 0)
        archive, = self.output.rglob("*.procreate")
        with zipfile.ZipFile(archive, "w") as z:
            for member, data in self.members.items():
                z.writestr(member, b"corrupt" if member.startswith("layers/") else data)
        result = self.run_job()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Archive verification failed", result.stderr)

    def test_missing_source_never_marks_snapshot_complete(self):
        next(p for p in self.backup.glob("*/*") if p.is_file()).unlink()
        self.assertNotEqual(self.run_job().returncode, 0)
        self.assertFalse(list(self.output.rglob("complete.json")))

    def test_incomplete_backup_is_rejected(self):
        (self.backup / "Status.plist").write_bytes(plistlib.dumps({"SnapshotState": "in-progress"}))
        result = self.run_job()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not marked finished", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
