"""Rule checks that need no model call: length, format and citation hygiene."""
import re

import config
from core.state import Brief, Chapter, Issue
from core.text import CITE_RE, split_sentences, word_count

BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
HEADING_RE = re.compile(r"^\s*#", re.MULTILINE)
URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
# Digits, rupee amounts, percentages and Indian number words all signal a checkable figure.
FIGURE_RE = re.compile(r"\d|₹|%|\bper ?cent\b|\blakh\b|\bcrore\b", re.IGNORECASE)
HARMLESS_FIGURES = ("24/7", "24x7", "24 hours a day")


def check_chapter(chapter: Chapter, fact_ids: set[str], brief: Brief) -> list[Issue]:
    issues: list[Issue] = []

    def add(problem: str, fix: str, excerpt: str = "", claim_problem: bool = False) -> None:
        issues.append(Issue(chapter=chapter.number, source="checks", problem=problem, fix=fix,
                            excerpt=excerpt, claim_problem=claim_problem))

    body, takeaway = chapter.body, chapter.takeaway.strip()

    words = word_count(body)
    if words < brief.min_words:
        add(f"The chapter is {words} words; the brief needs {brief.min_words}-{brief.max_words}.",
            f"Add about {config.TARGET_WORDS - words} words by explaining ideas more fully or adding "
            "a practical example. Do not add figures without citations.")
    elif words > brief.max_words:
        add(f"The chapter is {words} words; the brief needs {brief.min_words}-{brief.max_words}.",
            f"Cut about {words - config.TARGET_WORDS} words by removing repetition.")

    if BULLET_RE.search(body):
        add("The chapter contains a bullet point or numbered list.", "Rewrite the list as flowing prose.")
    if HEADING_RE.search(body):
        add("The chapter body contains a heading.", "Remove headings from the body.")
    if URL_RE.search(body) or URL_RE.search(takeaway):
        add("The chapter contains a web address.", "Remove it; cite sources only with [F#] IDs.")
    if "takeaway:" in body.lower():
        add("The takeaway is inside the body.", "Move it to the takeaway field only.")
    if not takeaway.startswith("Takeaway:") or "\n" in takeaway:
        add("The takeaway must be a single line starting with 'Takeaway:'.", "Rewrite the takeaway as one line.")
    if FIGURE_RE.search(_without_harmless(takeaway)):
        add("The takeaway contains a figure.", "Keep figures in the body, where they can be cited.")

    cited = set(CITE_RE.findall(body))
    unknown = sorted(cited - fact_ids)
    if unknown:
        add(f"The chapter cites unknown fact IDs: {', '.join(unknown)}.",
            "Cite only IDs from the fact list, or remove those claims.")
    if len(cited & fact_ids) < config.MIN_CITED_FACTS:
        add(f"The chapter cites only {len(cited & fact_ids)} facts.",
            f"Use at least {config.MIN_CITED_FACTS} facts from the fact list, each with its [F#].")

    for sentence in split_sentences(body):
        if not CITE_RE.search(sentence) and FIGURE_RE.search(_without_harmless(sentence)):
            add("This sentence states a number, amount or date without a citation.",
                "Add the [F#] of the fact that supports it, or remove the figure.",
                excerpt=sentence, claim_problem=True)
    return issues


def _without_harmless(text: str) -> str:
    for phrase in HARMLESS_FIGURES:
        text = text.replace(phrase, "")
    return text
