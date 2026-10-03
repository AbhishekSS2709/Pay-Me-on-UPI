"""Writer: drafts all chapters in one call (one consistent voice) and revises flagged chapters."""
import config
from core.llm import LLM
from core.state import Brief, Chapter, Draft, Fact, Issue, Outline

SYSTEM = """You are the Writer: a warm, experienced mentor who explains digital payments to people opening
their first shop in India. You write only from the fact list you are given and cite every fact."""


def write(llm: LLM, brief: Brief, outline: Outline, facts: list[Fact]) -> Draft:
    plan = "\n\n".join(
        f"Chapter {c.number}: {c.title}\nGoal: {c.goal}\nKey points: " + " | ".join(c.key_points)
        for c in outline.chapters)
    prompt = f"""Write all {brief.chapters} chapters of "{brief.title}".

{_context(brief, outline, facts)}

Outline:
{plan}

{_rules(brief)}"""
    return llm.generate(label="Writer", model=config.SMART_MODEL, system=SYSTEM,
                        prompt=prompt, schema=Draft, temperature=0.7)


def revise(llm: LLM, brief: Brief, outline: Outline, facts: list[Fact], chapters: list[Chapter],
           issues: list[Issue], final_round: bool) -> Draft:
    sections = []
    for chapter in chapters:
        notes = "\n".join(
            f"{n}. {i.problem}" + (f'\n   Where: "{i.excerpt}"' if i.excerpt else "") + (f"\n   Fix: {i.fix}" if i.fix else "")
            for n, i in enumerate((i for i in issues if i.chapter == chapter.number), 1))
        sections.append(f"""=== CHAPTER {chapter.number}: {chapter.title} ===
{chapter.body}

{chapter.takeaway}

Problems to fix:
{notes}""")

    final_note = ("This is the final revision. Any claim you cannot support with a fact from the list "
                  "must be removed, not reworded." if final_round else "")
    prompt = f"""The Editor and Fact-checker sent these chapters back. Fix every problem listed. Keep
everything else as it is unless a fix needs a nearby change, and keep the same voice.
For an unsupported claim, either cite a fact from the list that does support it or remove the claim.
{final_note}

{_context(brief, outline, facts)}

{chr(10).join(sections)}

{_rules(brief)}

Return only the chapters above, with the same numbers."""
    return llm.generate(label="Writer (revision)", model=config.SMART_MODEL, system=SYSTEM,
                        prompt=prompt, schema=Draft, temperature=0.4)


def _context(brief: Brief, outline: Outline, facts: list[Fact]) -> str:
    glossary = "\n".join(f"- {t.term}: {t.plain_explanation}" for t in outline.glossary)
    fact_list = "\n".join(f'{f.id} (chapter {f.chapter}): {f.claim}\n   Source says: "{f.quote}"' for f in facts)
    return f"""Audience: {brief.audience}
Tone: {brief.tone}
Voice guide (follow it in every chapter): {outline.voice_guide}

Glossary (explain each term in plain words the first time it appears in the book):
{glossary}

Fact list (the only facts you may use):
{fact_list}"""


def _rules(brief: Brief) -> str:
    return f"""Rules for every chapter:
1. body is {brief.min_words}-{brief.max_words} words; aim for about {config.TARGET_WORDS}.
2. Flowing prose in paragraphs separated by a blank line. No bullet points, numbered lists, headings
   or bold text. Do not repeat the chapter title or the takeaway inside body.
3. Every fact, figure, date or statistic must come from the fact list and be followed by its ID in
   square brackets before the full stop, like this: "UPI was launched in 2016 [F3]." Cite several
   with [F3][F7]. Never invent a figure and never cite an ID that is not in the list.
4. Advice, encouragement and explanations of ideas need no citation, but must not contain figures.
5. When you give a figure, say when it is from, for example "in March 2025".
6. Never write a web address. Write ₹ for rupees, never "Rs.".
7. takeaway is one sentence starting with "Takeaway:" that sums up the chapter's main lesson,
   with no figures and no citations.
8. {brief.style}
9. Use title for the chapter title only, without the word "Chapter" or a number."""
