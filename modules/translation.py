import os
import requests
from abc import ABC, abstractmethod
from typing import List, Optional
from deep_translator import GoogleTranslator
from .utils import safe_print

LANGUAGE_NAMES = {
    "vi": "Vietnamese",
    "en": "English",
    "zh": "Chinese",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

def get_language_name(language_code: str) -> str:
    return LANGUAGE_NAMES.get(language_code, language_code)

try:
    from google import genai
    GEMINI_AVAILABLE = True
    SDK_VERSION = "new"
except ImportError:
    try:
        import google.generativeai as genai_old
        GEMINI_AVAILABLE = True
        SDK_VERSION = "old"
    except ImportError:
        GEMINI_AVAILABLE = False
        SDK_VERSION = None

class BaseTranslator(ABC):
    @abstractmethod
    def translate(self, text: str) -> str:
        pass
    
    def translate_batch(self, texts: List[str]) -> List[str]:
        """Default batch implementation (sequential)"""
        return [self.translate(t) for t in texts]
    
    def print_usage_stats(self):
        pass

class GoogleTranslatorWrapper(BaseTranslator):
    def __init__(self, target_lang='vi'):
        self.client = GoogleTranslator(source='auto', target=target_lang)
    
    def translate(self, text: str) -> str:
        try:
            return self.client.translate(text)
        except Exception as e:
            safe_print(f"Google Translate Error: {e}")
            return text

class GeminiTranslatorWrapper(BaseTranslator):
    FALLBACK_MODELS = [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ]

    def __init__(self, api_key: str = None, model: str = None, target_lang: str = "vi"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model_name = model or self.FALLBACK_MODELS[0]
        self.target_lang = target_lang
        self.disabled = False
        self.error_count = 0
        self.fallback = GoogleTranslatorWrapper(target_lang=target_lang)
        self.client = None
        
        # Stats
        self.request_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
        if not self.api_key or not GEMINI_AVAILABLE:
            self.disabled = True
            return

        try:
            if SDK_VERSION == "new":
                self.client = genai.Client(api_key=self.api_key)
            else:
                genai_old.configure(api_key=self.api_key)
                self.client = genai_old.GenerativeModel(self.model_name)
            safe_print(f"GeminiTranslator initialized ({SDK_VERSION} SDK)")
        except Exception as e:
            safe_print(f"Error initializing Gemini: {e}")
            self.disabled = True

    def _get_system_prompt(self) -> str:
        target = get_language_name(self.target_lang)
        vietnamese_name_rule = (
            "\n3. For Chinese names translated to Vietnamese, prefer established Hán-Việt readings when appropriate."
            if self.target_lang == "vi"
            else ""
        )
        return f"""You are a professional movie subtitle translator.
Translate the provided subtitle text into {target}. Detect the source language from the input instead of assuming a fixed source language.
RULES:
1. Translate naturally for movie dialogue (conversational).
2. Keep it concise.{vietnamese_name_rule}
3. Output ONLY the translation.
"""

    def _generate(self, prompt: str) -> str:
        self.request_count += 1
        if SDK_VERSION == "new":
            response = self.client.models.generate_content(model=self.model_name, contents=prompt)
            if hasattr(response, 'usage_metadata'):
                self.total_input_tokens += getattr(response.usage_metadata, 'prompt_token_count', 0)
                self.total_output_tokens += getattr(response.usage_metadata, 'candidates_token_count', 0)
            return response.text
        else:
            response = self.client.generate_content(prompt)
            return response.text

    def translate(self, text: str) -> str:
        if self.disabled: return self.fallback.translate(text)
        try:
            prompt = f"{self._get_system_prompt()}\nTranslate:\n{text}"
            return self._generate(prompt).strip()
        except Exception as e:
            safe_print(f"Gemini Translate Error: {e}")
            self.error_count += 1
            if self.error_count > 5: self.disabled = True
            return self.fallback.translate(text)

    def translate_batch(self, texts: List[str], batch_size: int = 30) -> List[str]:
        if self.disabled: return self.fallback.translate_batch(texts)
        if not texts: return []
        
        all_results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            numbered = "\n".join([f"{idx+1}. {txt}" for idx, txt in enumerate(batch)])
            prompt = f"{self._get_system_prompt()}\nTranslate each numbered line, keeping format '1. Translation':\n{numbered}"
            
            try:
                res = self._generate(prompt)
                lines = res.strip().split('\n')
                # Parse
                batch_results = []
                import re
                for line in lines:
                    cleaned = re.sub(r'^\d+[\.\)\:]\s*', '', line.strip())
                    if cleaned: batch_results.append(cleaned)
                
                # Fill missing
                while len(batch_results) < len(batch):
                    batch_results.append(self.fallback.translate(batch[len(batch_results)]))
                
                all_results.extend(batch_results[:len(batch)])
            except Exception as e:
                safe_print(f"Gemini Batch Error: {e}")
                all_results.extend(self.fallback.translate_batch(batch))
        
        return all_results

    def print_usage_stats(self):
        safe_print(f"Gemini Stats: {self.request_count} requests, {self.total_input_tokens + self.total_output_tokens} tokens")

class OllamaTranslator(BaseTranslator):
    def __init__(self, model="qwen:7b", target_lang='vi'):
        self.model = model
        self.target_lang = target_lang
        self.api_url = "http://localhost:11434/api/chat"
        self.fallback = GoogleTranslatorWrapper(target_lang=target_lang)
        self.disabled = False
        
        try:
            requests.get("http://localhost:11434/api/tags", timeout=2)
        except:
            safe_print("Ollama not reachable.")
            self.disabled = True

    def translate(self, text: str) -> str:
        if self.disabled: return self.fallback.translate(text)
        try:
            resp = requests.post(self.api_url, json={
                "model": self.model,
                "messages": [{
                    "role": "system", "content": f"Translate the provided text into {get_language_name(self.target_lang)}. Detect the source language automatically. Output ONLY the translation."
                }, {
                    "role": "user", "content": text
                }],
                "stream": False
            }, timeout=30)
            if resp.status_code == 200:
                return resp.json()['message']['content'].strip()
        except:
            pass
        return self.fallback.translate(text)

class OllamaCorrector:
    def __init__(self, model="deepseek-r1:latest"):
        self.model = model
        self.api_url = "http://localhost:11434/api/chat"
    
    def correct(self, text):
        # Implementation similar to auto_subtitle.py but simplified
        return text 

def test_gemini_connection(api_key: str = None) -> dict:
    """Test if Gemini API key is valid"""
    try:
        translator = GeminiTranslatorWrapper(api_key=api_key)
        if translator.disabled:
            return {"success": False, "error": "API key not configured or SDK not available"}
        
        # Test with simple translation
        result = translator.translate("你好")
        
        if result:
            return {
                "success": True, 
                "model": translator.model_name,
                "sdk_version": SDK_VERSION,
                "test_result": result
            }
        else:
            return {"success": False, "error": "Empty response from API"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}
