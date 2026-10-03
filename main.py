"""Entry point.

    python main.py                 write the book from brief.yaml
    python main.py --resume        continue a stopped run from output/state.json
    python main.py --check-links   re-test every reference link in output/book.md
    python main.py --revise 2      one extra revision of a chapter that finished with warnings
"""
import argparse
import re
import sys

import config
from core.links import check_urls
from core.llm import LLM
from core.search import WebSearch
from core.state import BookState, Brief
from orchestrator import Orchestrator


def write_book(resume: bool) -> int:
    missing = [name for name in ("GEMINI_API_KEY", "TAVILY_API_KEY") if not getattr(config, name)]
    if missing:
        print(f"Missing {', '.join(missing)}. Copy .env.example to .env and add your keys.")
        return 1

    state_path = config.OUTPUT_DIR / "state.json"
    if resume and state_path.exists():
        state = BookState.load(state_path)
        state.note("Orchestrator", "resuming from saved state")
    else:
        state = BookState(brief=Brief.load(config.BRIEF_PATH))
        state.note("Orchestrator", f"new run: {state.brief.title}")

    llm = LLM(config.GEMINI_API_KEY, config.CACHE_DIR, config.MAX_LLM_CALLS, state.note, calls_used=state.llm_calls)
    search = WebSearch(config.TAVILY_API_KEY, config.CACHE_DIR, state.note)
    Orchestrator(state, llm, search, config.OUTPUT_DIR).run()
    return 0


def revise_chapter(number: int) -> int:
    state_path = config.OUTPUT_DIR / "state.json"
    if not state_path.exists():
        print("No output/state.json yet. Run python main.py first.")
        return 1
    state = BookState.load(state_path)
    llm = LLM(config.GEMINI_API_KEY, config.CACHE_DIR, config.MAX_LLM_CALLS, state.note, calls_used=state.llm_calls)
    search = WebSearch(config.TAVILY_API_KEY, config.CACHE_DIR, state.note)
    Orchestrator(state, llm, search, config.OUTPUT_DIR).extra_revision(number)
    return 0


def check_links() -> int:
    book = config.OUTPUT_DIR / "book.md"
    if not book.exists():
        print("No output/book.md yet. Run python main.py first.")
        return 1
    urls = re.findall(r"https?://\S+", book.read_text(encoding="utf-8"))
    results = check_urls(urls)
    for url, (status, detail) in results.items():
        print(f"{status.upper():8} {detail:>16}  {url}")
    broken = sum(status == "broken" for status, _ in results.values())
    print(f"\n{len(results)} links checked, {broken} broken. "
          "'BLOCKED' means the site refuses scripts; open it in a browser to confirm.")
    return 1 if broken else 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # the log uses → and ₹; Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description="Multi-agent writer for 'Pay Me on UPI'.")
    parser.add_argument("--resume", action="store_true", help="continue from output/state.json")
    parser.add_argument("--check-links", action="store_true", help="re-test links in output/book.md")
    parser.add_argument("--revise", type=int, metavar="N", help="one extra revision of chapter N, using its open issues")
    args = parser.parse_args()
    if args.revise:
        return revise_chapter(args.revise)
    return check_links() if args.check_links else write_book(args.resume)


if __name__ == "__main__":
    sys.exit(main())
