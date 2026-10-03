from assemble import number_citations, reference_line, render_book, render_evidence
from core.state import BookState, Brief, Chapter, Fact, Page, SentenceCheck

PAGES = {
    "P1": Page(id="P1", url="https://www.npci.org.in/upi", title="UPI Product Overview",
               source="NPCI", official=True, text="..."),
    "P2": Page(id="P2", url="https://pib.gov.in/release", title="UPI crosses a milestone",
               source="PIB", official=True, text="..."),
}
FACTS = {
    "F1": Fact(id="F1", chapter=1, claim="", quote="launched in 2016 by NPCI", page_id="P1"),
    "F2": Fact(id="F2", chapter=1, claim="", quote="crossed 18 billion", page_id="P2"),
    "F3": Fact(id="F3", chapter=1, claim="", quote="run by NPCI", page_id="P1"),
}


def test_numbers_follow_first_use_and_same_page_shares_a_number():
    body = "UPI grew to 18 billion [F2]. It began in 2016 [F1] and NPCI runs it [F3]."
    text, refs = number_citations(body, FACTS, PAGES)
    assert text == "UPI grew to 18 billion [1]. It began in 2016 [2] and NPCI runs it [2]."
    assert [p.id for p in refs] == ["P2", "P1"]


def test_duplicate_numbers_collapse_and_unknown_ids_vanish():
    text, refs = number_citations("NPCI launched UPI [F1][F3][F9].", FACTS, PAGES)
    assert text == "NPCI launched UPI [1]."
    assert len(refs) == 1


def test_reference_line_has_source_title_and_link():
    assert reference_line(1, PAGES["P1"]) == '[1] NPCI. "UPI Product Overview." https://www.npci.org.in/upi'


def make_state() -> BookState:
    brief = Brief(title="Pay Me on UPI", audience="First-time owners", chapters=1, min_words=1, max_words=9,
                  tone="", style="", official_domains={}, news_domains={})
    body = "UPI grew to 18 billion [F2]. It began in 2016 [F1]."
    return BookState(
        brief=brief, pages=list(PAGES.values()), facts=list(FACTS.values()),
        chapters=[Chapter(number=1, title="What changed", body=body, takeaway="Takeaway: Go digital.")],
        fact_checks=[SentenceCheck(chapter=1, sentence_id="C1-S1", sentence="UPI grew to 18 billion [F2].",
                                   verdict="supports", note="ok")],
    )


def test_book_has_takeaway_before_references():
    book = render_book(make_state())
    assert "## Chapter 1: What changed" in book
    assert book.index("Takeaway: Go digital.") < book.index("### References")
    assert '[1] PIB. "UPI crosses a milestone." https://pib.gov.in/release' in book
    assert "[F" not in book


def test_evidence_uses_book_numbering_and_shows_quotes_and_verdicts():
    evidence = render_evidence(make_state())
    assert "**Sentence:** It began in 2016 [2]." in evidence
    assert '> "launched in 2016 by NPCI"' in evidence
    assert "✅ supports" in evidence
    assert "not reviewed" in evidence
