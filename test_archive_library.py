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
import uuid
import zipfile
from datetime import datetime
from contextlib import closing

from procreate_backup import DOMAIN
from test_extract_previews import tiny_png

CANVAS_ID = "00000000-0000-0000-0000-000000000001"
SECOND_ID = "00000000-0000-0000-0000-000000000002"
THIRD_ID = "00000000-0000-0000-0000-000000000003"
STACK_ID = "10000000-0000-0000-0000-000000000001"
OTHER_STACK_ID = "10000000-0000-0000-0000-000000000002"


def gallery_archive(items):
    """Use the keyed-archive structure found in Finder.archive, with fake IDs."""
    objects = ["$null", {}]

    def add(value):
        objects.append(value)
        return plistlib.UID(len(objects) - 1)

    def node(item, parent=plistlib.UID(0)):
        record = {}
        ref = add(record)
        identifier = item if isinstance(item, str) else item["id"]
        record["FinderModelDocumentArchiveIdentifierKey"] = add({"NS.uuidbytes": uuid.UUID(identifier).bytes})
        record["FinderModelDocumentArchiveParentKey"] = parent
        record["FinderModelDocumentArchiveStackKey"] = isinstance(item, dict)
        if isinstance(item, dict):
            record["FinderModelDocumentArchiveStackNameKey"] = add(item["name"]) if item["name"] is not None else plistlib.UID(0)
            record["FinderModelDocumentArchiveSubDocumentsKey"] = add({
                "NS.objects": [node(child, ref) for child in item["items"]]})
        else:
            record["FinderModelDocumentArchivePathKey"] = add(identifier)
        return ref

    objects[1]["FinderModelControllerArchiveDocumentsKey"] = add({"NS.objects": [node(i) for i in items]})
    return keyed(objects[1], objects[2:])


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
            "QuickLook/Thumbnail.png": tiny_png(),
        }
        with closing(sqlite3.connect(self.backup / "Manifest.db")) as db:
            db.execute("CREATE TABLE Files(fileID TEXT, domain TEXT, relativePath TEXT, flags INT, file BLOB)")
            for member, data in self.members.items():
                relative = f"Library/Application Support/{CANVAS_ID}/{member}"
                fid = hashlib.sha1((DOMAIN + "-" + relative).encode()).hexdigest()
                p = self.backup / fid[:2] / fid
                p.parent.mkdir(exist_ok=True)
                p.write_bytes(data)
                metadata = keyed({"Size": len(data), "LastModified": 1700000000})
                db.execute("INSERT INTO Files VALUES(?,?,?,?,?)", (fid, DOMAIN, relative, 1, metadata))
            db.commit()

    def add_file(self, relative, data):
        fid = hashlib.sha1((DOMAIN + "-" + relative).encode()).hexdigest()
        p = self.backup / fid[:2] / fid
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(data)
        with closing(sqlite3.connect(self.backup / "Manifest.db")) as db:
            db.execute("DELETE FROM Files WHERE domain=? AND relativePath=?", (DOMAIN, relative))
            db.execute("INSERT INTO Files VALUES(?,?,?,?,?)", (fid, DOMAIN, relative, 1,
                       keyed({"Size": len(data), "LastModified": 1700000000})))
            db.commit()

    def add_canvas(self, identifier):
        for member, data in self.members.items():
            self.add_file(f"Library/Application Support/{identifier}/{member}", data)

    def add_gallery(self, items):
        self.add_file("Library/Application Support/Finder.archive", gallery_archive(items))

    def run_job(self, *options):
        return subprocess.run([sys.executable, str(Path(__file__).with_name("archive_library.py")),
                               "--backup", str(self.backup), "--output", str(self.output), *options],
                              capture_output=True, text=True)

    def test_stack_folders_default_repeat_and_recursive_previews(self):
        self.add_canvas(SECOND_ID)
        self.add_canvas(THIRD_ID)
        items = [{"id": STACK_ID, "name": "Studies", "items": [SECOND_ID, CANVAS_ID]}, THIRD_ID]
        self.add_gallery(items)
        before = {str(p.relative_to(self.backup)): p.read_bytes()
                  for p in self.backup.rglob("*") if p.is_file()}
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = next(self.output.rglob("complete.json")).parent
        stack = snapshot / "canvases" / f"Studies--{STACK_ID}"
        self.assertEqual(len(list(stack.glob("*.procreate"))), 2)
        self.assertEqual(len(list((snapshot / "canvases").glob("*.procreate"))), 1)
        layout = json.loads((snapshot / "layout.json").read_text())
        self.assertEqual([c["id"] for c in layout["gallery"]["items"][0]["items"]], [SECOND_ID, CANVAS_ID])
        self.assertEqual(len(list((snapshot / "verification" / stack.name).glob("*.json"))), 2)
        for archive in snapshot.rglob("*.procreate"):
            with zipfile.ZipFile(archive) as z:
                self.assertEqual({n: z.read(n) for n in z.namelist()}, self.members)
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("verified existing"), 3)
        previews = self.root / "previews"
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("extract_previews.py")),
                                 str(snapshot / "canvases"), "--output", str(previews), "--recursive"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list((previews / stack.name).glob("*.png"))), 2)
        self.assertEqual(len(list(previews.glob("*.png"))), 1)
        self.assertEqual(before, {str(p.relative_to(self.backup)): p.read_bytes()
                                 for p in self.backup.rglob("*") if p.is_file()})
        result = self.run_job("--flat")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different --output", result.stderr)

    def test_flat_option_and_later_default_keep_flat_paths(self):
        self.add_gallery([{"id": STACK_ID, "name": "Studies", "items": [CANVAS_ID]}])
        result = self.run_job("--flat")
        self.assertEqual(result.returncode, 0, result.stderr)
        archive, = self.output.rglob("*.procreate")
        self.assertEqual(archive.parent.name, "canvases")
        self.assertEqual(self.run_job().returncode, 0)
        self.assertEqual(len(list(self.output.rglob("*.procreate"))), 1)

    def test_legacy_snapshot_without_layout_keeps_flat_paths(self):
        self.add_gallery([{"id": STACK_ID, "name": "Studies", "items": [CANVAS_ID]}])
        self.assertEqual(self.run_job("--flat").returncode, 0)
        next(self.output.rglob("layout.json")).unlink()
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("older flat snapshot", result.stdout)
        self.assertIn("verified existing", result.stdout)
        self.assertFalse(list(self.output.rglob("layout.json")))

    def test_duplicate_and_unsafe_stack_names_are_distinct_and_contained(self):
        self.add_canvas(SECOND_ID)
        name = '../CON: \\?*'
        self.add_gallery([{"id": STACK_ID, "name": name, "items": [CANVAS_ID]},
                          {"id": OTHER_STACK_ID, "name": name, "items": [SECOND_ID]}])
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        archives = list(self.output.rglob("*.procreate"))
        self.assertEqual(len({p.parent for p in archives}), 2)
        for p in archives:
            self.assertEqual(p.parent.parent.name, "canvases")
            self.assertNotRegex(p.parent.name, r'[\\/:*?"<>|]')

    def test_unnamed_nested_and_empty_stacks(self):
        self.add_gallery([{"id": STACK_ID, "name": None, "items": [
            {"id": OTHER_STACK_ID, "name": "Empty", "items": []}, CANVAS_ID]}])
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        archive, = self.output.rglob("*.procreate")
        self.assertEqual(archive.parent.name, f"Stack--{STACK_ID}")
        self.assertTrue((archive.parent / f"Empty--{OTHER_STACK_ID}").is_dir())

    def test_bad_gallery_is_rejected_but_flat_can_extract(self):
        for items in ([CANVAS_ID, CANVAS_ID], [], [SECOND_ID]):
            with self.subTest(items=items):
                self.add_gallery(items)
                result = self.run_job()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Use --flat", result.stderr)
                self.assertFalse(list(self.output.rglob("complete.json")))
        self.assertEqual(self.run_job("--flat").returncode, 0)

    def test_resume_after_partial_stack_extraction(self):
        self.add_gallery([{"id": STACK_ID, "name": "Studies", "items": [CANVAS_ID]}])
        self.assertEqual(self.run_job().returncode, 0)
        next(self.output.rglob("complete.json")).unlink()
        next(self.output.rglob("*.procreate")).unlink()
        next(self.output.rglob("*.verification.json")).unlink()
        result = self.run_job()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(list(self.output.rglob("*.procreate"))), 1)

    def test_changed_gallery_rejects_resume(self):
        self.add_gallery([{"id": STACK_ID, "name": "Studies", "items": [CANVAS_ID]}])
        self.assertEqual(self.run_job().returncode, 0)
        self.add_gallery([CANVAS_ID])
        result = self.run_job()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("layout differs", result.stderr)

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
