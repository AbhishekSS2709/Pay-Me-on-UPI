"""Thin Gemini wrapper: structured JSON output, retries, a disk cache and a call budget."""
import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Callable, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
RETRYABLE_CODES = {429, 500, 502, 503, 504}
MAX_TRIES = 5


class BudgetExceeded(RuntimeError):
    pass


class LLM:
    def __init__(self, api_key: str, cache_dir: Path, max_calls: int,
                 log: Callable[[str, str], None], calls_used: int = 0):
        self._client = genai.Client(api_key=api_key) if api_key else None
        self._cache_dir = cache_dir / "llm"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = log
        self._lock = threading.Lock()
        self.max_calls = max_calls
        self.calls = calls_used

    def generate(self, *, label: str, model: str, system: str, prompt: str,
                 schema: type[T], temperature: float = 0.4) -> T:
        """Return the model's reply parsed into `schema`. Identical requests are served from disk."""
        key = hashlib.sha256(json.dumps(
            [model, system, prompt, schema.model_json_schema(), temperature]).encode()).hexdigest()
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            self._log(label, "reused cached reply (no API call)")
            return schema.model_validate_json(cache_file.read_text(encoding="utf-8"))

        self._spend_call(label)
        text = self._request(model, system, prompt, schema, temperature)
        try:
            result = schema.model_validate_json(text)
        except ValidationError as error:
            self._spend_call(f"{label} (repairing invalid JSON)")
            retry_prompt = f"{prompt}\n\nYour previous reply did not match the JSON schema:\n{error}\nReply again with valid JSON only."
            text = self._request(model, system, retry_prompt, schema, temperature)
            result = schema.model_validate_json(text)

        cache_file.write_text(text, encoding="utf-8")
        return result

    def _spend_call(self, label: str) -> None:
        with self._lock:
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"Reached the cap of {self.max_calls} model calls.")
            self.calls += 1
            number = self.calls
        self._log(label, f"Gemini call {number}/{self.max_calls}")

    def _request(self, model: str, system: str, prompt: str, schema: type[BaseModel],
                 temperature: float) -> str:
        if self._client is None:
            raise RuntimeError("GEMINI_API_KEY is missing. Copy .env.example to .env and add your key.")
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # tools are run by code
        )
        for attempt in range(1, MAX_TRIES + 1):
            try:
                response = self._client.models.generate_content(model=model, contents=prompt, config=config)
                return response.text or ""
            except errors.APIError as error:
                if error.code not in RETRYABLE_CODES or attempt == MAX_TRIES:
                    raise
                wait = _suggested_delay(error) or min(60, 5 * 2 ** (attempt - 1))
                self._log("Gemini", f"error {error.code}, waiting {wait}s before retry {attempt + 1}/{MAX_TRIES}")
                time.sleep(wait)
        raise AssertionError("unreachable")


def _suggested_delay(error: errors.APIError) -> int | None:
    """Gemini's 429 replies include a retryDelay such as '37s'."""
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", str(error))
    return int(match.group(1)) + 1 if match else None
