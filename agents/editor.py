"""Editor: checks grammar, spelling, tone, readability and voice, and sends chapters back with fixes."""
from typing import Literal

from pydantic import BaseModel

import config
from core.llm import LLM
from core.state import Brief, Chapter, Outline

SYSTEM = """You are the Editor at a publisher of friendly, practical business guides. You are a careful
copy editor and you care about the reader: a first-time shop owner who may not be confident with
technology or with formal English."""


class EditNote(BaseModel):
    chapter: int
    excerpt: str
    problem: str
    fix: str
    severity: Literal["must_fix", "nice_to_have"]


class EditReport(BaseModel):
    notes: list[EditNote]


def review(llm: LLM, brief: Brief, outline: Outline, chapters: list[Chapter],
           approved: list[Chapter]) -> EditReport:
    to_review = "\n\n".join(_render(c) for c in chapters)
    reference = ""
    if approved:
        reference = ("Already approved chapters, shown only so you can check the voice matches. Do not review them:\n\n"
                     + "\n\n".join(_render(c) for c in approved))
    glossary = ", ".join(t.term for t in outline.glossary)

    prompt = f"""Review these chapters of "{brief.title}".

Audience: {brief.audience}
Tone: {brief.tone}
Style: {brief.style}
Voice guide: {outline.voice_guide}
Terms that must be explained the first time they appear: {glossary}

{to_review}

{reference}

Check grammar, spelling and punctuation; clarity for this reader; jargon used before it is explained;
tone (a friendly, encouraging mentor); whether the voice matches across chapters; flow between
paragraphs; and repetition. Ignore the [F#] citation markers and do not judge the facts, because the
Fact-checker does that.

For each problem return the chapter number, excerpt (the exact words from the chapter, kept short),
problem, a concrete fix (the rewritten words), and severity:
- must_fix: a grammar, spelling or punctuation error; an unexplained technical term; a sentence that
  is confusing; or a clear break from the tone or voice.
- nice_to_have: a style preference.
Only report real problems. If a chapter is clean, return no notes for it."""
    return llm.generate(label="Editor", model=config.SMART_MODEL, system=SYSTEM,
                        prompt=prompt, schema=EditReport, temperature=0.2)


def _render(chapter: Chapter) -> str:
    return f"=== CHAPTER {chapter.number}: {chapter.title} ===\n{chapter.body}\n\n{chapter.takeaway}"
