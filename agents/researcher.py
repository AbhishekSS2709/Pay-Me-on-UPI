"""Researcher: reads the fetched pages and builds a pool of facts, each with its exact supporting quote."""
from pydantic import BaseModel

import config
from core.llm import LLM
from core.state import Outline, Page

SYSTEM = """You are the Researcher. You report only facts that are written on the pages you are given,
each with the exact words from the page. You never use your own memory as a source, because every
fact must be checkable by a reader who opens the page."""


class FoundFact(BaseModel):
    chapter: int
    claim: str
    quote: str
    page_id: str


class Gap(BaseModel):
    chapter: int
    need: str
    query: str


class ResearchResult(BaseModel):
    facts: list[FoundFact]
    missing: list[Gap]


def find_facts(llm: LLM, outline: Outline, pages: list[Page], gaps: list[Gap] | None = None) -> ResearchResult:
    if gaps:
        label = "Researcher (gap fill)"
        needs = "\n".join(f"Chapter {g.chapter}: {g.need}" for g in gaps)
    else:
        label = "Researcher"
        needs = "\n".join(
            f"Chapter {c.number} ({c.title}): " + "; ".join(c.facts_needed) for c in outline.chapters)

    sources = "\n\n".join(
        f"=== PAGE {p.id} | {p.source} | {'official' if p.official else 'news'} | {p.title} ===\n{p.text}"
        for p in pages)

    prompt = f"""What each chapter needs:
{needs}

Pages:
{sources}

Find facts on these pages that cover what each chapter needs. For each fact return:
- chapter: the chapter number it is for
- claim: one plain-English sentence stating the fact. For a figure, include the date or period it
  refers to, exactly as the page gives it.
- quote: one or two sentences copied word for word from the page that state the fact. Do not fix,
  shorten or reword anything inside the quote. Use "..." only to skip words in the middle.
- page_id: the page the quote is from, such as P3.

Prefer official pages when an official and a news page say the same thing, and prefer the most recent
figures. Aim for 6-10 facts per chapter. Never report a fact that is not on the pages.

In missing, list anything a chapter needs that is not on any page, each with one search query that
could find it (at most 3 per chapter). Return an empty list if nothing important is missing."""
    return llm.generate(label=label, model=config.FAST_MODEL, system=SYSTEM,
                        prompt=prompt, schema=ResearchResult, temperature=0.1)
