"""Run settings. Secrets come from .env; everything else is tuned here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
BRIEF_PATH = ROOT / "brief.yaml"
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / ".cache"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Smart model for planning, writing and judging; fast model for bulk fact extraction.
SMART_MODEL = os.getenv("SMART_MODEL", "gemini-3.8-flash")
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-3.5-flash-lite")

# Stop rules
MAX_REVISION_ROUNDS = 2
MAX_LLM_CALLS = 15            # hard safety cap per book

# Research
RESULTS_PER_QUERY = 5
PAGES_PER_CHAPTER = 8
MIN_OFFICIAL_PAGES = 4        # fewer than this and the news pass runs for that chapter
MIN_PAGE_CHARS = 400          # thinner pages are usually JavaScript shells or paywalls
MAX_PAGE_CHARS = 8000         # page text kept and shown to the Researcher
MAX_GAP_QUERIES = 6           # follow-up searches when the Researcher reports gaps

# Chapter checks
TARGET_WORDS = 750
MIN_CITED_FACTS = 4
