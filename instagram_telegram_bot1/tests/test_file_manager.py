import os
import tempfile
import time
import unittest
from pathlib import Path

from services.file_manager import TempDirManager


class FileManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "base"
        self.mgr = TempDirManager(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_cleanup(self):
        d = self.mgr.create_job_dir()
        (d / "a.mp4").write_bytes(b"1")
        self.assertTrue(self.mgr.cleanup(d))
        self.assertFalse(d.exists())
        self.assertTrue(self.mgr.cleanup(d))  # ikkinchi marta ham xatosiz

    def test_refuses_outside_dirs(self):
        outside = Path(self.tmp.name) / "job_outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("x")
        self.assertFalse(self.mgr.cleanup(outside))
        self.assertFalse(self.mgr.cleanup(self.base))
        other = self.base / "not_a_job"
        other.mkdir()
        self.assertFalse(self.mgr.cleanup(other))
        self.assertTrue((outside / "keep.txt").exists())
        self.assertTrue(other.exists())

    def test_stale_cleanup(self):
        old, new = self.mgr.create_job_dir(), self.mgr.create_job_dir()
        f = old / "x.part"
        f.write_bytes(b"1")
        past = time.time() - 3600
        os.utime(f, (past, past))
        os.utime(old, (past, past))
        self.assertEqual(self.mgr.cleanup_stale(1800), 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertEqual(self.mgr.cleanup_all(), 1)
        self.assertFalse(new.exists())


if __name__ == "__main__":
    unittest.main()
