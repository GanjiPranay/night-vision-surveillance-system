import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import camera


class PreviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        camera._preview_process = None
        camera._recording_state["process"] = None
        camera._recording_state["filepath"] = None
        camera._recording_state["filename"] = None
        camera._recording_state["started_at"] = None

    @patch("camera.CAMERA_AVAILABLE", True)
    @patch("camera.subprocess.Popen")
    def test_start_preview_stops_previous_and_starts_new(self, mock_popen):
        mock_prev = object()
        camera._preview_process = mock_prev
        camera.start_preview("still")
        self.assertEqual(camera._preview_process, mock_popen.return_value)
        self.assertEqual(mock_popen.call_count, 1)

    @patch("camera.CAMERA_AVAILABLE", False)
    def test_stop_recording_saves_placeholder_when_no_process(self):
        camera._recording_state["process"] = None
        camera._recording_state["filepath"] = os.path.join(camera.VIDEO_DIR, "test.mp4")
        camera._recording_state["filename"] = "test.mp4"
        camera._recording_state["started_at"] = 1

        with patch("camera._make_placeholder_video") as mock_placeholder:
            filename = camera.stop_recording()

        self.assertEqual(filename, "test.mp4")
        mock_placeholder.assert_called_once()


if __name__ == "__main__":
    unittest.main()
