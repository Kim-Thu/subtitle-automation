import unittest
from unittest.mock import MagicMock, patch

from modules.translation import (
    GeminiTranslatorWrapper,
    OllamaTranslator,
    get_language_name,
)


class TranslationPromptTests(unittest.TestCase):
    def test_language_names_cover_ui_targets(self):
        expected = {
            "vi": "Vietnamese",
            "en": "English",
            "zh-CN": "Simplified Chinese",
            "ja": "Japanese",
            "ko": "Korean",
        }
        for code, name in expected.items():
            self.assertEqual(get_language_name(code), name)

    @patch("modules.translation.GoogleTranslator")
    def test_gemini_prompt_uses_selected_target_without_fixed_source(self, _google):
        translator = GeminiTranslatorWrapper(api_key="", target_lang="ko")
        prompt = translator._get_system_prompt()

        self.assertIn("Korean", prompt)
        self.assertIn("Detect the source language", prompt)
        self.assertNotIn("Translate Chinese to", prompt)

    @patch("modules.translation.requests.get")
    @patch("modules.translation.requests.post")
    @patch("modules.translation.GoogleTranslator")
    def test_ollama_prompt_uses_selected_target(self, _google, post, get):
        get.return_value = MagicMock(status_code=200)
        post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"message": {"content": "translated"}},
        )

        translator = OllamaTranslator(model="qwen:7b", target_lang="ja")
        translator.translate("hello")

        payload = post.call_args.kwargs["json"]
        system_prompt = payload["messages"][0]["content"]
        self.assertIn("Japanese", system_prompt)
        self.assertNotIn("Vietnamese", system_prompt)


if __name__ == "__main__":
    unittest.main()
