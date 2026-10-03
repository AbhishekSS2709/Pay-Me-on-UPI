from core.text import (place_citations_before_punctuation, quote_in_text, remove_sentences,
                       split_sentences, word_count)

PAGE = """# UPI Overview
Unified Payments Interface (UPI) is a system that powers multiple bank accounts into a single
mobile application. It was launched by **NPCI** in 2016, and in [March 2025](https://x.in) it
processed 18.30 billion transactions worth ₹24.77 lakh crore."""


def test_quote_matches_despite_case_markdown_and_line_breaks():
    assert quote_in_text("It was launched by NPCI in 2016", PAGE)
    assert quote_in_text("in March 2025 it processed 18.30 billion transactions", PAGE)


def test_quote_with_ellipsis_matches_parts_in_order():
    assert quote_in_text("Unified Payments Interface (UPI) is a system ... launched by NPCI in 2016", PAGE)
    assert not quote_in_text("launched by NPCI in 2016 ... Unified Payments Interface (UPI) is a system", PAGE)


def test_altered_numbers_do_not_match():
    assert not quote_in_text("it processed 19.30 billion transactions", PAGE)
    assert not quote_in_text("It was launched by NPCI in 2015", PAGE)


def test_partial_words_do_not_match():
    assert not quote_in_text("aunched by NPCI in 2016 and in March", PAGE)


def test_very_short_quotes_are_rejected():
    assert not quote_in_text("in 2016", PAGE)


def test_citations_after_full_stop_move_inside_sentence():
    body = "UPI arrived in 2016. [F1] It grew fast.[F2][F3] Good."
    assert place_citations_before_punctuation(body) == "UPI arrived in 2016 [F1]. It grew fast [F2][F3]. Good."


def test_split_sentences_and_remove_keep_paragraphs():
    body = "First one [F1]. Second one.\n\nThird one! Fourth one?"
    assert split_sentences(body) == ["First one [F1].", "Second one.", "Third one!", "Fourth one?"]
    assert remove_sentences(body, {"Second one.", "Third one!"}) == "First one [F1].\n\nFourth one?"


def test_word_count_ignores_citations():
    assert word_count("UPI is fast [F1][F2]. Very fast [F3].") == 5
