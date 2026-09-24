import os
import tempfile
import unittest

from modules.utils import normalize_relative_path, resolve_managed_path


class ManagedPathTests(unittest.TestCase):
    def test_accepts_nested_relative_path(self):
        normalized = normalize_relative_path("folder/video.mp4")
        self.assertEqual(normalized, os.path.join("folder", "video.mp4"))

    def test_rejects_posix_absolute_path(self):
        with self.assertRaises(ValueError):
            normalize_relative_path("/tmp/video.mp4")

    def test_rejects_windows_absolute_path(self):
        with self.assertRaises(ValueError):
            normalize_relative_path(r"C:\\temp\\video.mp4")

    def test_rejects_posix_traversal(self):
        with self.assertRaises(ValueError):
            normalize_relative_path("../outside.mp4")

    def test_rejects_windows_traversal(self):
        with self.assertRaises(ValueError):
            normalize_relative_path(r"..\\outside.mp4")

    def test_resolved_path_stays_under_root(self):
        with tempfile.TemporaryDirectory() as root:
            resolved = resolve_managed_path(root, "folder/video.mp4")
            self.assertEqual(
                os.path.commonpath([os.path.abspath(root), resolved]),
                os.path.abspath(root),
            )


if __name__ == "__main__":
    unittest.main()
