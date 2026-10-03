import pytest

from core.checks import check_chapter
from core.state import Brief, Chapter

BRIEF = Brief(title="T", audience="A", chapters=3, min_words=600, max_words=900, tone="", style="",
              official_domains={}, news_domains={})
FACT_IDS = {"F1", "F2", "F3", "F4", "F5"}
FILLER = "Keep your QR code where every customer can see it and thank them warmly. " * 50  # 700 words
CITED = "UPI was launched in 2016 [F1]. It is run by NPCI [F2]. Many shops use it [F3]. Payments are instant [F4]."


def chapter(body: str = "", takeaway: str = "Takeaway: Start small and stay safe.") -> Chapter:
    return Chapter(number=1, title="Start", body=body or f"{CITED}\n\n{FILLER}", takeaway=takeaway)


def problems(ch: Chapter) -> list[str]:
    return [i.problem for i in check_chapter(ch, FACT_IDS, BRIEF)]


def test_clean_chapter_passes():
    assert problems(chapter()) == []


def test_too_short_chapter_is_flagged_with_word_count():
    issues = check_chapter(chapter(body=CITED), FACT_IDS, BRIEF)
    assert any("words" in i.problem for i in issues)
    assert any("Add about" in i.fix for i in issues)


@pytest.mark.parametrize("extra, expected", [
    ("- first point\n- second point", "bullet"),
    ("1. first point", "bullet"),
    ("## A heading", "heading"),
    ("See https://npci.org.in for more.", "web address"),
    ("Takeaway: oops.", "takeaway is inside"),
])
def test_format_problems_are_flagged(extra, expected):
    body = f"{CITED}\n\n{extra}\n\n{FILLER}"
    assert any(expected in p for p in problems(chapter(body=body)))


def test_uncited_figure_is_flagged_as_claim_problem():
    body = f"{CITED} About 40% of shops now take UPI.\n\n{FILLER}"
    issues = check_chapter(chapter(body=body), FACT_IDS, BRIEF)
    flagged = [i for i in issues if i.claim_problem]
    assert len(flagged) == 1
    assert flagged[0].excerpt == "About 40% of shops now take UPI."


def test_harmless_numbers_are_not_flagged():
    body = f"{CITED} UPI works 24/7, even on holidays.\n\n{FILLER}"
    assert problems(chapter(body=body)) == []


def test_unknown_fact_ids_and_too_few_citations_are_flagged():
    body = f"UPI is popular [F9].\n\n{FILLER}"
    found = problems(chapter(body=body))
    assert any("unknown fact IDs: F9" in p for p in found)
    assert any("cites only 0 facts" in p for p in found)


def test_takeaway_must_be_one_line_without_figures():
    assert any("starting with 'Takeaway:'" in p for p in problems(chapter(takeaway="Remember: be safe.")))
    assert any("takeaway contains a figure" in p for p in problems(chapter(takeaway="Takeaway: 90% of it is trust.")))
