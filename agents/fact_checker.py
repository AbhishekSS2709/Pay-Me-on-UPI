"""Fact-checker: confirms sources are real and that each one supports the sentence citing it.

Code does the mechanical checks (does the link load? are the quoted words really on the page?);
the model judges whether the quoted words support the sentence.
"""
from typing import Literal

from pydantic import BaseModel

import config
from core.links import check_urls
from core.llm import LLM
from core.state import Chapter, Fact, Page, SentenceCheck
from core.text import CITE_RE, quote_in_text, split_sentences

SYSTEM = """You are the Fact-checker. You judge whether each cited sentence is supported by the evidence
quoted under it. Use only the evidence shown, never your own knowledge: a reader must be able to
confirm every claim from the cited source alone."""


class Verdict(BaseModel):
    sentence_id: str
    verdict: Literal["supports", "partly", "does_not_support", "uncited_claim"]
    note: str


class FactCheckReport(BaseModel):
    verdicts: list[Verdict]


def filter_live_pages(pages: list[Page]) -> tuple[list[Page], list[Page]]:
    """Split pages into (kept, dropped) by whether their link works.

    A bot-blocked link (403, 429…) is kept: the search service already fetched the page's text,
    so the page exists and a reader's browser will load it.
    """
    statuses = check_urls([p.url for p in pages])
    kept = [p for p in pages if statuses[p.url][0] != "broken"]
    dropped = [p for p in pages if statuses[p.url][0] == "broken"]
    return kept, dropped


def quote_on_page(quote: str, page: Page) -> bool:
    return quote_in_text(quote, page.text)


def check(llm: LLM, chapters: list[Chapter], facts: list[Fact],
          pages: list[Page]) -> tuple[list[SentenceCheck], int]:
    """Return a verdict per sentence, plus how many cited sentences the model skipped."""
    facts_by_id = {f.id: f for f in facts}
    pages_by_id = {p.id: p for p in pages}
    sentences: dict[str, tuple[int, str]] = {}
    blocks = []
    for chapter in chapters:
        blocks.append(f"=== CHAPTER {chapter.number} ===")
        for n, sentence in enumerate(split_sentences(chapter.body), 1):
            sentence_id = f"C{chapter.number}-S{n}"
            sentences[sentence_id] = (chapter.number, sentence)
            blocks.append(f"{sentence_id}: {sentence}")
            for fact_id in dict.fromkeys(CITE_RE.findall(sentence)):
                if fact := facts_by_id.get(fact_id):
                    source = pages_by_id[fact.page_id].source
                    blocks.append(f'    evidence for {fact_id} ({source}): "{fact.quote}"')

    prompt = f"""Below are chapters split into numbered sentences. Under each sentence that cites a fact
you will see the exact words from the cited source.

{chr(10).join(blocks)}

For every sentence that has evidence under it, return one verdict:
- supports: every fact, number, date and name in the sentence is stated in, or directly follows from,
  the evidence.
- partly: the evidence backs the main point, but the sentence adds or changes a detail (a number, a
  date, a name, "all" instead of "some", or a cause the evidence does not state).
- does_not_support: the evidence is about something else or contradicts the sentence.

For a sentence with no evidence under it, return uncited_claim only if it states a specific checkable
fact (a number, date, statistic, named event, law, rule or fee). General advice, encouragement and
plain explanations of what a term means need no citation; return nothing for them.

In note, say briefly what is wrong, or "ok" when the evidence supports the sentence."""
    report = llm.generate(label="Fact-checker", model=config.SMART_MODEL, system=SYSTEM,
                          prompt=prompt, schema=FactCheckReport, temperature=0.0)

    results = [
        SentenceCheck(chapter=sentences[v.sentence_id][0], sentence_id=v.sentence_id,
                      sentence=sentences[v.sentence_id][1], verdict=v.verdict, note=v.note)
        for v in report.verdicts if v.sentence_id in sentences
    ]
    cited = {sid for sid, (_, sentence) in sentences.items() if CITE_RE.search(sentence)}
    skipped = len(cited - {r.sentence_id for r in results})
    return results, skipped
