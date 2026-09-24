import unittest
from unittest.mock import MagicMock, patch

import modules.workflow as workflow


class WhisperModelCacheTests(unittest.TestCase):
    def setUp(self):
        workflow._whisper_model = None
        workflow._whisper_model_size = None

    @patch("modules.workflow.TranscriptionService")
    def test_reuses_model_for_same_size(self, service_cls):
        small_model = MagicMock(name="small_model")
        service_cls.return_value = small_model

        first = workflow.get_whisper_model("small")
        second = workflow.get_whisper_model("small")

        self.assertIs(first, small_model)
        self.assertIs(second, small_model)
        service_cls.assert_called_once_with("small")

    @patch("modules.workflow.TranscriptionService")
    def test_reloads_model_when_size_changes(self, service_cls):
        small_model = MagicMock(name="small_model")
        medium_model = MagicMock(name="medium_model")
        service_cls.side_effect = [small_model, medium_model]

        first = workflow.get_whisper_model("small")
        second = workflow.get_whisper_model("medium")

        self.assertIs(first, small_model)
        self.assertIs(second, medium_model)
        self.assertEqual(
            service_cls.call_args_list,
            [unittest.mock.call("small"), unittest.mock.call("medium")],
        )
        self.assertEqual(workflow._whisper_model_size, "medium")


if __name__ == "__main__":
    unittest.main()
