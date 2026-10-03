"""Runs the agents in order and owns the revision loop and stop rules.

Each step is skipped if its output is already in the state, so a crashed run can resume.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import assemble
import config
from agents import editor, fact_checker, planner, researcher, writer
from agents.researcher import FoundFact
from core import checks
from core.links import page_headline
from core.llm import LLM
from core.search import WebSearch
from core.state import BookState, Chapter, Draft, Fact, Issue, Page
from core.text import normalize, place_citations_before_punctuation, remove_sentences, word_count

FACT_CHECK_PROBLEMS = {
    "partly": ("The cited source only partly supports this sentence",
               "Change the sentence to say only what the source says, or cite a fact that supports it fully."),
    "does_not_support": ("The cited source does not support this sentence",
                         "Cite a fact that does support it, or remove the claim."),
    "uncited_claim": ("This sentence states a fact without a citation",
                      "Cite the fact that supports it, or remove the claim."),
}


class Orchestrator:
    def __init__(self, state: BookState, llm: LLM, search: WebSearch, output_dir: Path):
        self.state = state
        self.llm = llm
        self.search = search
        self.output_dir = output_dir

    def run(self) -> None:
        for step in (self._plan, self._gather_sources, self._research, self._draft, self._review_loop, self._publish):
            step()
            self._save()

    # Step 1: Planner
    def _plan(self) -> None:
        s = self.state
        if s.outline:
            return
        outline = planner.plan(self.llm, s.brief)
        if len(outline.chapters) != s.brief.chapters:
            raise RuntimeError(f"Planner returned {len(outline.chapters)} chapters, expected {s.brief.chapters}.")
        for number, chapter in enumerate(outline.chapters, 1):
            chapter.number = number
        s.outline = outline
        queries = sum(len(c.search_queries) for c in outline.chapters)
        titles = "; ".join(f"{c.number}. {c.title}" for c in outline.chapters)
        s.note("Planner → Researcher", f"outline ready ({titles}), {queries} search queries")

    # Step 2: Search (code)
    def _gather_sources(self) -> None:
        s = self.state
        if s.pages:
            return
        for chapter in s.outline.chapters:
            pages = self._find_pages(chapter.search_queries)
            s.pages += pages
            official = sum(p.official for p in pages)
            s.note("Search", f"chapter {chapter.number}: kept {len(pages)} pages ({official} official)")
        if not s.pages:
            raise RuntimeError("No usable sources were found. Check the TAVILY_API_KEY and your connection.")

    def _find_pages(self, queries: list[str]) -> list[Page]:
        """Official sites first; reputable news only if official sources are thin. Live links only."""
        s = self.state
        seen = {p.url for p in s.pages}
        candidates = self._search(queries, s.brief.official_domains, official=True, seen=seen)
        if len(candidates) < config.MIN_OFFICIAL_PAGES:
            candidates += self._search(queries, s.brief.news_domains, official=False,
                                       seen=seen | {p.url for p in candidates})

        live, dropped = fact_checker.filter_live_pages(candidates)
        for page in dropped:
            s.note("Fact-checker", f"dropped broken link {page.url}")
        live.sort(key=lambda p: (not p.official, -p.score))
        chosen = live[:config.PAGES_PER_CHAPTER]
        for offset, page in enumerate(chosen, 1):
            page.id = f"P{len(s.pages) + offset}"
        return chosen

    def _search(self, queries: list[str], domains: dict[str, str], official: bool, seen: set[str]) -> list[Page]:
        found: dict[str, Page] = {}
        for query in queries:
            for result in self.search.search(query, list(domains), config.RESULTS_PER_QUERY):
                url = result["url"]
                if not url or url in seen or url in found:
                    continue
                text = f"{result['content']}\n\n{result['raw_content']}".strip()[:config.MAX_PAGE_CHARS]
                if len(text) < config.MIN_PAGE_CHARS:
                    continue
                found[url] = Page(id="", url=url, title=result["title"] or url, official=official,
                                  source=_source_name(url, domains), text=text, score=result["score"])
        return list(found.values())

    # Step 3: Researcher, with one optional gap-filling round
    def _research(self) -> None:
        s = self.state
        if s.facts:
            return
        result = researcher.find_facts(self.llm, s.outline, s.pages)
        self._accept_facts(result.facts, "Researcher")

        if result.missing and not s.research_gap_filled:
            s.research_gap_filled = True
            queries = list(dict.fromkeys(g.query for g in result.missing))[:config.MAX_GAP_QUERIES]
            s.note("Researcher → Search", f"{len(result.missing)} gaps reported, running {len(queries)} follow-up searches")
            new_pages = self._find_pages(queries)
            s.pages += new_pages
            if new_pages:
                more = researcher.find_facts(self.llm, s.outline, new_pages, gaps=result.missing)
                self._accept_facts(more.facts, "Researcher (gap fill)")

        for chapter in s.outline.chapters:
            count = sum(f.chapter == chapter.number for f in s.facts)
            if count < config.MIN_CITED_FACTS:
                s.warnings.append(f"Chapter {chapter.number} has only {count} verified facts.")
                s.note("Researcher", f"warning: chapter {chapter.number} has only {count} verified facts")
        if not s.facts:
            raise RuntimeError("No facts could be verified against their sources.")

    def _accept_facts(self, found: list[FoundFact], who: str) -> None:
        """Keep only facts whose quote really is on the cited page."""
        s = self.state
        known_quotes = {normalize(f.quote) for f in s.facts}
        accepted = rejected = 0
        for fact in found:
            page = s.page(fact.page_id)
            if page is None or not fact_checker.quote_on_page(fact.quote, page):
                rejected += 1
                continue
            if normalize(fact.quote) in known_quotes:
                continue
            known_quotes.add(normalize(fact.quote))
            s.facts.append(Fact(id=f"F{len(s.facts) + 1}", chapter=fact.chapter,
                                claim=fact.claim, quote=fact.quote, page_id=page.id))
            accepted += 1
        s.note(f"{who} → Fact-checker",
               f"{len(found)} facts proposed; {accepted} quotes verified on their pages, {rejected} rejected")

    # Step 4: Writer drafts every chapter in one call
    def _draft(self) -> None:
        s = self.state
        if s.chapters:
            return
        draft = writer.write(self.llm, s.brief, s.outline, s.facts)
        s.chapters = self._to_chapters(draft, expected=set(range(1, s.brief.chapters + 1)))
        words = ", ".join(str(word_count(c.body)) for c in s.chapters)
        s.note("Writer → Editor & Fact-checker", f"draft of {len(s.chapters)} chapters (words: {words})")

    # Step 5-6: review and revise until approved or out of rounds
    def _review_loop(self) -> None:
        s = self.state
        if s.review_done:
            return
        while True:
            pending = [c for c in s.chapters if not c.approved]
            if not pending:
                break
            issues = self._review(pending)
            for chapter in pending:
                if not any(i.chapter == chapter.number and i.blocking for i in issues):
                    chapter.approved = True
                    s.note("Orchestrator", f"chapter {chapter.number} approved")
            s.open_issues = issues
            pending = [c for c in pending if not c.approved]
            self._save()
            if not pending:
                break
            if s.revision_round >= config.MAX_REVISION_ROUNDS:
                self._final_safety_net(pending, issues)
                break

            s.revision_round += 1
            numbers = ", ".join(str(c.number) for c in pending)
            s.note("Editor & Fact-checker → Writer", f"round {s.revision_round}: chapters {numbers} sent back for fixes")
            draft = writer.revise(self.llm, s.brief, s.outline, s.facts, pending,
                                  [i for i in issues if i.blocking],
                                  final_round=s.revision_round == config.MAX_REVISION_ROUNDS)
            revised = {c.number: c for c in self._to_chapters(draft, expected={c.number for c in pending})}
            s.chapters = [revised.get(c.number, c) for c in s.chapters]
            self._save()
        s.review_done = True

    def _review(self, pending: list[Chapter]) -> list[Issue]:
        s = self.state
        fact_ids = {f.id for f in s.facts}
        issues = [issue for c in pending for issue in checks.check_chapter(c, fact_ids, s.brief)]
        approved = [c for c in s.chapters if c.approved]

        with ThreadPoolExecutor(max_workers=2) as pool:
            edit_job = pool.submit(editor.review, self.llm, s.brief, s.outline, pending, approved)
            check_job = pool.submit(fact_checker.check, self.llm, pending, s.facts, s.pages)
            edit_report = edit_job.result()
            sentence_checks, skipped = check_job.result()

        pending_numbers = {c.number for c in pending}
        for note in edit_report.notes:
            if note.chapter in pending_numbers:
                issues.append(Issue(chapter=note.chapter, source="editor", problem=note.problem, fix=note.fix,
                                    excerpt=note.excerpt, blocking=note.severity == "must_fix"))
        for result in sentence_checks:
            if result.verdict in FACT_CHECK_PROBLEMS:
                problem, fix = FACT_CHECK_PROBLEMS[result.verdict]
                issues.append(Issue(chapter=result.chapter, source="fact_checker", problem=f"{problem}: {result.note}",
                                    fix=fix, excerpt=result.sentence, claim_problem=True))
        s.fact_checks = [c for c in s.fact_checks if c.chapter not in pending_numbers] + sentence_checks
        if skipped:
            s.note("Fact-checker", f"warning: {skipped} cited sentences got no verdict")

        for chapter in pending:
            mine = [i for i in issues if i.chapter == chapter.number]
            counts = {source: sum(i.source == source and i.blocking for i in mine)
                      for source in ("checks", "editor", "fact_checker")}
            minor = sum(not i.blocking for i in mine)
            s.note("Review", f"chapter {chapter.number}: {counts['checks']} rule, {counts['editor']} editor, "
                             f"{counts['fact_checker']} fact-check issues to fix ({minor} minor notes)")
        return issues

    def _final_safety_net(self, pending: list[Chapter], issues: list[Issue]) -> None:
        """Out of rounds: delete still-unsupported sentences; log everything else as warnings."""
        s = self.state
        fact_ids = {f.id for f in s.facts}
        for chapter in pending:
            doomed = {i.excerpt for i in issues if i.chapter == chapter.number and i.claim_problem and i.excerpt}
            if doomed:
                chapter.body = remove_sentences(chapter.body, doomed)
                s.note("Fact-checker", f"chapter {chapter.number}: removed {len(doomed)} sentence(s) "
                                       f"still unsupported after {config.MAX_REVISION_ROUNDS} rounds")
            leftovers = [i for i in issues if i.chapter == chapter.number and i.source == "editor" and i.blocking]
            leftovers += [i for i in checks.check_chapter(chapter, fact_ids, s.brief) if not i.claim_problem]
            for issue in leftovers:
                s.warnings.append(f"Chapter {chapter.number}: {issue.problem}")
            s.note("Orchestrator", f"chapter {chapter.number} finished with {len(leftovers)} warning(s); see run_log.md")

    # Optional, run by hand: one more pass for a chapter that finished with warnings
    def extra_revision(self, number: int) -> None:
        s = self.state
        chapter = next(c for c in s.chapters if c.number == number)
        issues = [i for i in s.open_issues if i.chapter == number and i.blocking]
        if not issues:
            s.note("Orchestrator", f"chapter {number} has no open issues; nothing to revise")
            return
        s.note("Orchestrator → Writer", f"extra revision: chapter {number}, {len(issues)} leftover issues")
        draft = writer.revise(self.llm, s.brief, s.outline, s.facts, [chapter], issues, final_round=True)
        revised = self._to_chapters(draft, expected={number})[0]
        s.chapters = [revised if c.number == number else c for c in s.chapters]
        self._save()

        new_issues = self._review([revised])
        s.open_issues = [i for i in s.open_issues if i.chapter != number] + new_issues
        s.warnings = [w for w in s.warnings if not w.startswith(f"Chapter {number}:")]
        if any(i.blocking for i in new_issues):
            self._final_safety_net([revised], new_issues)
        else:
            revised.approved = True
            s.note("Orchestrator", f"chapter {number} approved")
        self._publish()
        self._save()

    # Step 7: assemble the outputs (code)
    def _publish(self) -> None:
        s = self.state
        s.llm_calls = self.llm.calls
        for page in {s.page(f.page_id).url: s.page(f.page_id) for f in s.facts}.values():
            headline = page_headline(page.url)
            if headline and headline != page.title:
                page.title = headline
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "book.md").write_text(assemble.render_book(s), encoding="utf-8")
        (self.output_dir / "evidence.md").write_text(assemble.render_evidence(s), encoding="utf-8")
        s.note("Assembler", f"book written to {self.output_dir / 'book.md'} "
                            f"({self.llm.calls} Gemini calls, {s.revision_round} revision rounds)")
        (self.output_dir / "run_log.md").write_text(assemble.render_run_log(s), encoding="utf-8")

    def _to_chapters(self, draft: Draft, expected: set[int]) -> list[Chapter]:
        got = {c.number for c in draft.chapters}
        if got != expected:
            raise RuntimeError(f"Writer returned chapters {sorted(got)}, expected {sorted(expected)}.")
        return [
            Chapter(number=c.number, title=_clean_title(c.title), takeaway=c.takeaway.strip(),
                    body=place_citations_before_punctuation(c.body.strip()))
            for c in sorted(draft.chapters, key=lambda c: c.number)
        ]

    def _save(self) -> None:
        self.state.llm_calls = self.llm.calls
        self.state.save(self.output_dir / "state.json")


def _source_name(url: str, domains: dict[str, str]) -> str:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    for domain, name in domains.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host


def _clean_title(title: str) -> str:
    """'Chapter 1: Getting Started' -> 'Getting Started'."""
    return re.sub(r"^chapter\s+\w+\s*[:.\-–—]\s*", "", title.strip(), flags=re.IGNORECASE)
