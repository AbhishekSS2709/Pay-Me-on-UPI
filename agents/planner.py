"""Planner: turns the brief into an outline, search queries, a shared voice guide and a glossary."""
import config
from core.llm import LLM
from core.state import Brief, Outline

SYSTEM = """You are the Planner in a small team that writes short, practical non-fiction books.
You design the outline that the Researcher, Writer, Editor and Fact-checker will all follow."""


def plan(llm: LLM, brief: Brief) -> Outline:
    prompt = f"""Plan a {brief.chapters}-chapter book.

Title: {brief.title}
Audience: {brief.audience}
Length: {brief.min_words}-{brief.max_words} words per chapter
Tone: {brief.tone}

Return:
- chapters: for each chapter, its number (1 to {brief.chapters}), a title without the word "Chapter",
  a one-sentence goal, 4-6 key points in the order they should be covered, the specific facts and
  figures it needs (for example "the year UPI was launched" or "UPI transactions in a recent month"),
  and 4-6 web search queries likely to find official or reputable sources for those facts. Write
  queries the way a person types into a search engine; add NPCI, RBI or PIB where that helps.
- voice_guide: 4-6 sentences describing one voice for the whole book: who is speaking, how the reader
  is addressed, a recurring example shop owner, sentence length, and how terms are explained.
- glossary: the technical terms the book will need (such as UPI or QR code), each with a plain
  explanation a first-time shop owner would understand.

The chapters should form a clear arc from what changed, to getting started, to growing the business.
They must not repeat the same facts."""
    return llm.generate(label="Planner", model=config.SMART_MODEL, system=SYSTEM,
                        prompt=prompt, schema=Outline, temperature=0.5)
