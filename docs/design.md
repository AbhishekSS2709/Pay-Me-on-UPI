# Design: multi-agent book writer

Brief: write *Pay Me on UPI* (3 chapters, 600–900 words each) for first-time small-business owners in India, with a real, working, supporting citation for every fact.

## Goals

1. **Citation accuracy first.** No invented sources, no broken links, every citation supports its sentence.
2. **Clear roles.** Planner, Researcher, Writer, Editor and Fact-checker are separate agents with their own prompt and typed output.
3. **Low, predictable cost.** 5 model calls in the best case, 12 in the worst, with a hard cap of 15. Free tiers of Gemini and Tavily.
4. **Simple.** Plain Python, no agent framework. One orchestrator owns the order, the loops and the stop rules.

## The core idea

> The model decides *what* to say and judges quality. Code fetches every source, verifies every quote and builds every citation.

- The Writer only cites fact IDs such as `[F3]`. It never writes a URL or a reference number.
- Every fact in the pool carries an exact quote, and code confirms that the quote is really on the fetched page.
- Code turns `[F#]` into `[1]`, `[2]`, … and builds the reference list from the fetched page's source name, title and URL.

So the book can only cite pages that were actually fetched, that load, and that contain the quoted words.

## Agents

| Agent | Model | Receives | Returns |
|---|---|---|---|
| Planner | smart | brief | outline: 3 chapters (goal, key points, facts needed, search queries), voice guide, glossary |
| Researcher | fast | outline + text of every fetched page | fact pool (claim, exact quote, page ID) + `missing` gaps with follow-up queries |
| Writer | smart | outline, voice guide, glossary, fact pool | 3 chapters citing `[F#]` (also revises flagged chapters) |
| Editor | smart | chapter text, voice guide, glossary | notes: excerpt, problem, fix, `must_fix` / `nice_to_have` |
| Fact-checker | smart + code | cited sentences with the quotes they cite | verdict per sentence: `supports` / `partly` / `does_not_support` / `uncited_claim` |

The Fact-checker also owns the code-only verification tools: the link check (does the URL load?) and the quote check (are these words really on the page?).

## Tools are code-driven, not model-driven

Agents request tools through their structured output, and code runs the tools. The Planner returns search queries and code runs them. The Researcher returns `missing` gaps and code runs one follow-up search round. This keeps the call count fixed and the tools reliable.

## Flow

1. **Planner** (1 call) produces the outline.
2. **Search** (code): each query runs against official domains first (NPCI, RBI, PIB, …). If a chapter gets fewer than 4 usable official pages, its queries also run against an allowlist of reputable news sites. Pages with almost no text are dropped. Links are checked, broken ones dropped, and up to 8 pages are kept per chapter, official first.
3. **Researcher** (1 call, +1 for gaps) builds the fact pool. Code drops any fact whose quote is not on its page.
4. **Writer** (1 call) drafts all three chapters together, which keeps the voice consistent.
5. **Review** of the chapters that aren't approved yet:
   - **Code checks**, free: 600–900 words, no bullets or headings, no URLs, one `Takeaway:` line, every `[F#]` exists, at least 4 facts cited, and any sentence with a digit, ₹, % or year has a citation.
   - **Editor** and **Fact-checker**, run in parallel (1 call each).
6. **Decision.** A chapter with no blocking issues is approved and frozen. Otherwise the **Writer revises only the flagged chapters** (1 call), and step 5 runs again for those chapters.
7. **Assemble** (code): renumber citations per chapter, add the reference list, and write `book.md`, `evidence.md`, `run_log.md` and `state.json`.

## Stop rules

- Stop when every chapter is approved, **or** after 2 revision rounds.
- After the last round, the safety net runs. Code deletes any sentence that is still unsupported or uncited, so facts never ship uncited. Any other remaining issues are written to the run log as warnings, and the book is still produced.
- The gap-fill research round runs at most once.
- There is a hard cap of 15 Gemini calls per run.

**Blocking issues:** any code-check failure, any Fact-checker verdict other than `supports`, and Editor `must_fix` notes.
**Non-blocking:** Editor `nice_to_have` notes, which are only logged.

## Errors

| Problem | Handling |
|---|---|
| Gemini 429 or 5xx | Back off and retry (5 tries), honouring the server's suggested delay |
| Invalid JSON | Gemini's response-schema mode, plus one retry that includes the validation error |
| Tavily failure | One retry, then skip the query |
| Thin page (JavaScript shell or paywall) | Dropped |
| Link 404 or DNS failure | Source dropped |
| Link 403/429 (bot block), but Tavily fetched the page text | Kept, since the page exists and readers' browsers will load it |
| Crash | `state.json` is saved after every step; `--resume` continues, and the disk cache makes repeated calls free |

## Calls per run

Planner 1 + Researcher 1 (+1) + Writer 1 + (Editor 1 + Fact-checker 1) per review + Writer 1 per revision.
Best case 5, worst case 1 + 2 + 1 + 3×2 + 2 = **12**.
