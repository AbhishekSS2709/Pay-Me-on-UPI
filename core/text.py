"""Text helpers shared by the checks, the Fact-checker and the assembler."""
import re

CITE_RE = re.compile(r"\[(F\d+)\]")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'“‘(₹A-Z0-9])")
_ELLIPSIS_RE = re.compile(r"\.\.\.|…")
_CITES_AFTER_STOP_RE = re.compile(r"([.!?])((?:[ \t]*\[F\d+\])+)")


def normalize(text: str) -> str:
    """Keep only lower-case words and numbers, so quotes match despite formatting differences."""
    text = _MD_LINK_RE.sub(r"\1", text).lower()
    return " ".join(re.findall(r"[a-z0-9₹%]+", text))


def quote_in_text(quote: str, text: str, min_chars: int = 20) -> bool:
    """True if the quote appears word for word in the text ('...' may skip words)."""
    parts = [p for p in (normalize(part) for part in _ELLIPSIS_RE.split(quote)) if p]
    if sum(len(p) for p in parts) < min_chars:
        return False
    haystack = f" {normalize(text)} "
    position = 0
    for part in parts:
        found = haystack.find(f" {part} ", position)
        if found == -1:
            return False
        position = found + len(part)
    return True


def paragraph_sentences(body: str) -> list[list[str]]:
    """Split a chapter body into paragraphs, each a list of sentences."""
    paragraphs = []
    for para in re.split(r"\n\s*\n", body.strip()):
        sentences = [s for s in _SENTENCE_BREAK_RE.split(" ".join(para.split())) if s]
        if sentences:
            paragraphs.append(sentences)
    return paragraphs


def split_sentences(body: str) -> list[str]:
    return [s for para in paragraph_sentences(body) for s in para]


def remove_sentences(body: str, doomed: set[str]) -> str:
    paragraphs = [[s for s in para if s not in doomed] for para in paragraph_sentences(body)]
    return "\n\n".join(" ".join(para) for para in paragraphs if para)


def word_count(body: str) -> int:
    return sum(1 for token in CITE_RE.sub(" ", body).split() if re.search(r"\w", token))


def place_citations_before_punctuation(body: str) -> str:
    """'in 2016. [F1]' -> 'in 2016 [F1].' so every citation stays inside its sentence."""
    def move(match: re.Match) -> str:
        cites = "".join(f"[{c}]" for c in CITE_RE.findall(match.group(2)))
        return f" {cites}{match.group(1)}"

    body = _CITES_AFTER_STOP_RE.sub(move, body)
    return re.sub(r"[ \t]{2,}", " ", body)
