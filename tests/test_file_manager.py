import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from modules.file_manager import VideoFileManager


class VideoFileManagerValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manager = VideoFileManager(
            self.temp_dir.name,
            max_upload_bytes=10,
            ffprobe_path="ffprobe",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_file(self, name="video.mp4", payload=b"1234"):
        path = os.path.join(self.temp_dir.name, name)
        with open(path, "wb") as handle:
            handle.write(payload)
        return path

    def test_rejects_file_over_configured_size(self):
        path = self._write_file(payload=b"x" * 11)

        result = self.manager.validate_media(path)

        self.assertFalse(result["success"])
        self.assertIn("size limit", result["error"])

    @patch("modules.file_manager.subprocess.run")
    def test_rejects_corrupt_media(self, run):
        run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Invalid data found when processing input",
        )
        path = self._write_file()

        result = self.manager.validate_media(path)

        self.assertFalse(result["success"])
        self.assertIn("Invalid or corrupt media file", result["error"])

    @patch("modules.file_manager.subprocess.run")
    def test_rejects_media_without_video_stream(self, run):
        run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "format": {"format_name": "matroska,webm", "duration": "1.0"},
                "streams": [{"index": 0, "codec_type": "audio", "codec_name": "opus"}],
            }),
            stderr="",
        )
        path = self._write_file()

        result = self.manager.validate_media(path)

        self.assertFalse(result["success"])
        self.assertIn("video stream", result["error"])

    @patch("modules.file_manager.subprocess.run")
    def test_rejects_unsupported_video_codec(self, run):
        run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "format": {"format_name": "avi", "duration": "1.0"},
                "streams": [{"index": 0, "codec_type": "video", "codec_name": "theora"}],
            }),
            stderr="",
        )
        path = self._write_file()

        result = self.manager.validate_media(path)

        self.assertFalse(result["success"])
        self.assertIn("Unsupported video codec", result["error"])

    @patch("modules.file_manager.subprocess.run")
    def test_accepts_supported_video_stream(self, run):
        run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "12.5"},
                "streams": [{"index": 0, "codec_type": "video", "codec_name": "h264"}],
            }),
            stderr="",
        )
        path = self._write_file()

        result = self.manager.validate_media(path)

        self.assertTrue(result["success"])
        self.assertEqual(result["codec"], "h264")
        self.assertEqual(result["duration"], 12.5)


if __name__ == "__main__":
    unittest.main()
