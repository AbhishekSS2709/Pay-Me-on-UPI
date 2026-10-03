"""Shared data models. Agents read and write these; BookState is saved after every step."""
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class Brief(BaseModel):
    title: str
    audience: str
    chapters: int
    min_words: int
    max_words: int
    tone: str
    style: str
    official_domains: dict[str, str]
    news_domains: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Brief":
        return cls(**yaml.safe_load(path.read_text(encoding="utf-8")))


class GlossaryTerm(BaseModel):
    term: str
    plain_explanation: str


class ChapterPlan(BaseModel):
    number: int
    title: str
    goal: str
    key_points: list[str]
    facts_needed: list[str]
    search_queries: list[str]


class Outline(BaseModel):
    chapters: list[ChapterPlan]
    voice_guide: str
    glossary: list[GlossaryTerm]


class Page(BaseModel):
    """A fetched web page that facts can be taken from."""
    id: str
    url: str
    title: str
    source: str
    official: bool
    text: str
    score: float = 0.0


class Fact(BaseModel):
    """A claim with the exact words on its page that back it up."""
    id: str
    chapter: int
    claim: str
    quote: str
    page_id: str


class ChapterDraft(BaseModel):
    number: int
    title: str
    body: str
    takeaway: str


class Draft(BaseModel):
    chapters: list[ChapterDraft]


class Chapter(ChapterDraft):
    approved: bool = False


class Issue(BaseModel):
    """One problem found in a chapter, sent back to the Writer."""
    chapter: int
    source: Literal["checks", "editor", "fact_checker"]
    problem: str
    fix: str = ""
    excerpt: str = ""
    blocking: bool = True
    claim_problem: bool = False  # an unsupported or uncited claim; removed if still unfixed at the end


class SentenceCheck(BaseModel):
    chapter: int
    sentence_id: str
    sentence: str
    verdict: Literal["supports", "partly", "does_not_support", "uncited_claim"]
    note: str


class BookState(BaseModel):
    brief: Brief
    outline: Outline | None = None
    pages: list[Page] = []
    facts: list[Fact] = []
    research_gap_filled: bool = False
    chapters: list[Chapter] = []
    revision_round: int = 0
    review_done: bool = False
    open_issues: list[Issue] = []
    fact_checks: list[SentenceCheck] = []
    warnings: list[str] = []
    llm_calls: int = 0
    log: list[str] = []

    def note(self, who: str, message: str) -> None:
        line = f"[{datetime.now():%H:%M:%S}] {who}: {message}"
        print(line, flush=True)
        self.log.append(line)

    def page(self, page_id: str) -> Page | None:
        return next((p for p in self.pages if p.id == page_id), None)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "BookState":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
