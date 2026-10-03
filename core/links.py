"""Checks that links load, the way a reader's browser would."""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LinkStatus = Literal["ok", "blocked", "broken"]
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
}
# Codes that usually mean "bots are not welcome" rather than "page does not exist".
BOT_BLOCK_CODES = {401, 403, 405, 429, 503}


def check_url(url: str) -> tuple[LinkStatus, str]:
    try:
        response = _get(url, verify=True)
    except requests.exceptions.SSLError:
        # Some government sites send incomplete certificate chains that browsers repair themselves.
        try:
            response = _get(url, verify=False)
        except requests.RequestException as error:
            return "broken", type(error).__name__
    except requests.RequestException as error:
        return "broken", type(error).__name__

    if response.status_code < 400:
        return "ok", str(response.status_code)
    if response.status_code in BOT_BLOCK_CODES:
        return "blocked", str(response.status_code)
    return "broken", str(response.status_code)


def check_urls(urls: list[str]) -> dict[str, tuple[LinkStatus, str]]:
    unique = list(dict.fromkeys(urls))
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(unique, pool.map(check_url, unique)))


def page_headline(url: str) -> str | None:
    """The page's og:title, which on sites like PIB is the real headline rather than a generic <title>."""
    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
    except requests.exceptions.SSLError:
        try:  # same incomplete-certificate fallback as check_url
            response = requests.get(url, headers=BROWSER_HEADERS, timeout=20, verify=False)
        except requests.RequestException:
            return None
    except requests.RequestException:
        return None
    match = re.search(r'og:title"\s+content="([^"]+)"', response.text)
    return " ".join(html.unescape(match.group(1)).split()) if match else None


def _get(url: str, verify: bool) -> requests.Response:
    response = requests.get(url, headers=BROWSER_HEADERS, timeout=20,
                            allow_redirects=True, verify=verify, stream=True)
    response.close()
    return response
