"""Tavily web search with a disk cache. Returns each result's URL, title, score and page text."""
import hashlib
import json
from pathlib import Path
from typing import Callable

from tavily import TavilyClient


class WebSearch:
    def __init__(self, api_key: str, cache_dir: Path, log: Callable[[str, str], None]):
        self._client = TavilyClient(api_key=api_key) if api_key else None
        self._cache_dir = cache_dir / "search"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._log = log

    def search(self, query: str, domains: list[str], max_results: int) -> list[dict]:
        key = hashlib.sha256(json.dumps([query, domains, max_results]).encode()).hexdigest()
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        if self._client is None:
            raise RuntimeError("TAVILY_API_KEY is missing. Copy .env.example to .env and add your key.")

        for attempt in (1, 2):
            try:
                response = self._client.search(
                    query=query,
                    search_depth="basic",
                    max_results=max_results,
                    include_domains=domains,
                    include_raw_content=True,
                )
                break
            except Exception as error:  # Tavily raises several error types; any failure is retried once
                if attempt == 2:
                    self._log("Search", f"skipped query {query!r}: {error}")
                    return []

        results = [
            {
                "url": r.get("url", ""),
                "title": " ".join((r.get("title") or "").split()),
                "score": r.get("score") or 0.0,
                "content": r.get("content") or "",
                "raw_content": r.get("raw_content") or "",
            }
            for r in response.get("results", [])
        ]
        cache_file.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        return results
