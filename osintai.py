import os
import re
import json
import time
import random
import subprocess
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from googlesearch import search
from utils import initialize_model, check_tool_installed, get_base_dir

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HTTP_HEADERS = {"User-Agent": _UA, "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"}

_TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})

# Phrases that signal we hit a bot-wall / login-wall / JS-shell rather than
# real content — very common on LinkedIn, Facebook, Instagram, Twitter/X
# when fetched without a logged-in browser session.
_BLOCK_SIGNS = [
    "log in to continue", "you must log in", "please log in", "giriş yapmalısınız",
    "giriş yap", "oturum açın", "sign up to see", "kaydolarak", "javascript is not available",
    "enable javascript", "javascript'i etkinleştir", "checking your browser",
    "verify you are a human", "access denied", "erişim engellendi", "403 forbidden",
    "captcha", "are you a robot", "this content isn't available", "içerik şu anda kullanılamıyor",
]


# ── Browser fallback (used only when a static fetch isn't enough) ───────────
def get_webdriver():
    try:
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(f"user-agent={_UA}")
        driver = webdriver.Chrome(options=opts)
        return driver
    except WebDriverException:
        pass

    try:
        from selenium.webdriver.firefox.options import Options
        opts = Options()
        opts.add_argument("-headless")
        driver = webdriver.Firefox(options=opts)
        return driver
    except WebDriverException:
        pass

    return None


# ── Entity extraction ─────────────────────────────────────────────────────────
def extract_entities_with_ai(user_input: str, model) -> dict:
    prompt = f"""
        [TASK]
        You are an information extraction system. From the user's request, extract:
        a probable username (only if one is actually given or clearly implied), the person's full name,
        the city/location mentioned (if any), and any other descriptive keywords (profession, school,
        employer, hobbies, birth year, team/club, etc).
        The request may contain ONLY a full name and a city with no username at all — this is the most
        common and perfectly valid case. Extract what is available and leave the rest empty/null.

        [OUTPUT FORMAT]
        Your response MUST be a single, valid JSON object with the keys "username", "full_name", "city",
        and "keywords" (a list of strings). Never invent information that isn't in the request.

        [USER REQUEST]
        "{user_input}"

        [YOUR JSON RESPONSE]
    """
    try:
        response = model.generate_content(prompt)
        clean = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        entities = json.loads(clean)
        return entities
    except Exception:
        return None


# ── Username-guessing (no AI needed — fast, deterministic, cheap) ───────────
def generate_username_candidates(full_name: str, max_candidates: int = 8) -> list:
    if not full_name:
        return []
    ascii_name = full_name.translate(_TR_MAP).lower()
    parts = re.findall(r"[a-z]+", ascii_name)
    if not parts:
        return []

    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""

    candidates = []

    def add(c):
        if c and c not in candidates:
            candidates.append(c)

    add(first + last)
    add(last + first)
    if last:
        add(f"{first}.{last}")
        add(f"{first}_{last}")
        add(f"{first[0]}{last}")
        add(f"{first}{last[0]}")
        add(f"{last}.{first}")
    add(first)

    return candidates[:max_candidates]


def check_github_username(username: str):
    try:
        r = requests.get(
            f"https://api.github.com/users/{username}",
            headers={**_HTTP_HEADERS, "Accept": "application/vnd.github+json"},
            timeout=6,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("html_url", f"https://github.com/{username}")
    except requests.exceptions.RequestException:
        pass
    return None


def check_reddit_username(username: str):
    """Reddit's JSON API is clean and deterministic — no scraping needed."""
    try:
        r = requests.get(
            f"https://www.reddit.com/user/{username}/about.json",
            headers=_HTTP_HEADERS, timeout=6,
        )
        if r.status_code == 200:
            data = r.json()
            if (data.get("data") or {}).get("name"):
                return f"https://www.reddit.com/user/{username}"
    except (requests.exceptions.RequestException, ValueError):
        pass
    return None


def check_keybase_username(username: str):
    """Keybase's lookup API is public and deterministic; also surfaces any
    other platforms (Twitter, GitHub, HN, etc.) the person has proven
    ownership of, which is genuinely high-value corroborating evidence."""
    try:
        r = requests.get(
            "https://keybase.io/_/api/1.0/user/lookup.json",
            params={"usernames": username}, timeout=6,
        )
        if r.status_code == 200:
            data = r.json()
            them = data.get("them") or []
            if them and them[0]:
                return f"https://keybase.io/{username}"
    except (requests.exceptions.RequestException, ValueError):
        pass
    return None


_USERNAME_CHECKERS = [
    ("GitHub", check_github_username, 95),
    ("Reddit", check_reddit_username, 88),
    ("Keybase", check_keybase_username, 88),
]


def probe_username_candidates(candidates: list, progress_callback=None, max_workers: int = 8) -> list:
    """Checks every username candidate against several platforms with clean,
    deterministic APIs (no scraping/false-positive risk). Confirmed hits
    skip AI verification entirely."""
    confirmed = []
    if not candidates:
        return confirmed

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for c in candidates:
            for platform, checker, conf in _USERNAME_CHECKERS:
                futures[executor.submit(checker, c)] = (c, platform, conf)
        for future in as_completed(futures):
            candidate, platform, conf = futures[future]
            try:
                url = future.result()
                if url:
                    confirmed.append({
                        "url": url, "verification_status": "Confirmed_Profile",
                        "confidence": conf, "source": f"{platform.lower()}_api_username_guess",
                        "matched_on": ["username"], "evidence_source": f"{platform}_api",
                    })
                    if progress_callback:
                        progress_callback(f"{platform}'da kullanıcı adı eşleşmesi bulundu: {candidate}")
            except Exception:
                pass
    return confirmed


# ── URL normalization / dedup ────────────────────────────────────────────────
def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc.startswith("m.") and "facebook" not in netloc:
            netloc = netloc[2:]
        path = parts.path.rstrip("/") or "/"
        return urlunsplit(("https", netloc, path, parts.query, ""))
    except Exception:
        return url


def merge_search_hits(hits: list) -> dict:
    """Merge hits (dicts with url/title/snippet/engine/query) from multiple
    engines into one record per normalized URL, keeping the richest title
    and snippet seen for it."""
    merged = {}
    for hit in hits:
        url = hit.get("url")
        if not url:
            continue
        key = normalize_url(url)
        entry = merged.setdefault(key, {"url": url, "title": "", "snippet": "", "engines": set(), "query": ""})
        if len(hit.get("title", "")) > len(entry["title"]):
            entry["title"] = hit.get("title", "")
        if len(hit.get("snippet", "")) > len(entry["snippet"]):
            entry["snippet"] = hit.get("snippet", "")
        if hit.get("engine"):
            entry["engines"].add(hit["engine"])
        if hit.get("query") and not entry["query"]:
            entry["query"] = hit["query"]
    return merged


# ── Static fetch + hybrid verification with confidence scoring ──────────────
def _fetch_static(url: str, timeout: int = 10):
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            return None
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
    except requests.exceptions.RequestException:
        return None


def fetch_wayback_snapshot(url: str, timeout: int = 8):
    """Checks the Wayback Machine for an archived snapshot of the page.
    Genuinely useful when the live page is behind a bot/login wall: the
    archived copy is often a real, previously-crawled version of the page
    with the actual profile content intact — a standard professional OSINT
    technique for reaching content that blocks live automated fetches."""
    try:
        r = requests.get(
            "https://archive.org/wayback/available",
            params={"url": url}, timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        snap = (data.get("archived_snapshots") or {}).get("closest")
        if snap and snap.get("available") and snap.get("url"):
            return _fetch_static(snap["url"], timeout=timeout)
    except (requests.exceptions.RequestException, ValueError):
        pass
    return None


def _name_tokens(full_name: str) -> list:
    if not full_name:
        return []
    return [t for t in re.findall(r"\w+", full_name.lower()) if len(t) > 1]


def _looks_blocked(text: str) -> bool:
    low = text.lower()
    return any(sign in low for sign in _BLOCK_SIGNS)


def verify_profile_existence(
    url: str, model, target_name: str = None, city: str = None, keywords: list = None,
    title_hint: str = "", snippet_hint: str = "", matched_query: str = "", engine_count: int = 1,
) -> dict:
    """Hybrid, snippet-aware verification pipeline:
      1. Fetch statically (fast, no browser needed).
      2. Escalate to a headless browser only if content is too thin AND a
         driver is actually available.
      3. If that still looks blocked (bot/login wall — common on LinkedIn,
         Facebook, Instagram, Twitter/X without an authenticated session),
         check the Wayback Machine for an archived snapshot before giving up
         — this often recovers real, previously-crawled page content.
      4. If even that fails, fall back to the search engine's own
         title+snippet as evidence rather than discarding the URL.
      5. AI classification returns a confidence score and is told exactly
         which evidence tier it's working from, plus whether multiple
         independent search engines corroborated this URL.
    """
    page_source = _fetch_static(url)
    page_text = ""
    if page_source:
        page_text = BeautifulSoup(page_source, "html.parser").get_text(separator=" ", strip=True)

    if len(page_text) < 200:
        driver = get_webdriver()
        if driver:
            try:
                driver.get(url)
                time.sleep(4)
                for text in ["Accept", "Allow all", "Agree", "Kabul Et", "Onayla", "Tümünü kabul et"]:
                    try:
                        xpath = (
                            f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZÇĞİÖŞÜ', "
                            f"'abcdefghijklmnopqrstuvwxyzçğıöşü'), '{text.lower()}')]"
                        )
                        btn = driver.find_element(By.XPATH, xpath)
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            time.sleep(2)
                            break
                    except NoSuchElementException:
                        pass
                rendered = driver.page_source
                if rendered:
                    rendered_text = BeautifulSoup(rendered, "html.parser").get_text(separator=" ", strip=True)
                    if len(rendered_text) > len(page_text):
                        page_text = rendered_text
            except Exception:
                pass
            finally:
                driver.quit()

    live_fetch_ok = len(page_text) >= 200 and not _looks_blocked(page_text)
    evidence = "full_page" if live_fetch_ok else None

    # Escalate to an archived snapshot before falling back to snippet-only.
    if not live_fetch_ok:
        archived_html = fetch_wayback_snapshot(url)
        if archived_html:
            archived_text = BeautifulSoup(archived_html, "html.parser").get_text(separator=" ", strip=True)
            if len(archived_text) >= 200 and not _looks_blocked(archived_text):
                page_text = archived_text
                live_fetch_ok = True
                evidence = "wayback_archive"

    tokens = _name_tokens(target_name)
    combined_hint_text = f"{title_hint} {snippet_hint}".lower()

    if not live_fetch_ok and not title_hint and not snippet_hint:
        return {"status": "NO_CONTENT_FOUND", "confidence": 0, "matched_on": [], "evidence": "none"}

    if tokens:
        text_has_name = any(tok in page_text.lower() for tok in tokens)
        hint_has_name = any(tok in combined_hint_text for tok in tokens)
        if not text_has_name and not hint_has_name:
            return {"status": "GENERIC_ERROR", "confidence": 0, "matched_on": [], "evidence": "none"}

    if live_fetch_ok:
        evidence_text = page_text[:4000]
    else:
        evidence = "search_snippet_only"
        evidence_text = f"Title: {title_hint}\nSnippet: {snippet_hint}"

    corroboration_note = (
        f"This URL was independently returned by {engine_count} different search engines, "
        "which is a moderately strong signal that it's a real, consistently indexed page."
        if engine_count >= 2 else
        "This URL was returned by a single search engine."
    )

    evidence_source_desc = {
        "full_page": "The FULL PAGE content was retrieved successfully.",
        "wayback_archive": (
            "The live page was blocked (login/JS wall), so an ARCHIVED SNAPSHOT from the Wayback "
            "Machine was used instead. This is real, previously-crawled page content — treat it with "
            "similar confidence to a full page read, noting it may be somewhat dated."
        ),
        "search_snippet_only": (
            "The live page could not be retrieved directly (likely a login/JS wall — common for social "
            "platforms without an authenticated session), and no archived snapshot was available. The "
            "evidence below is the SEARCH ENGINE's own indexed title and snippet for this URL. Treat this "
            "as slightly less certain than a full page read, but don't dismiss it just because the full "
            "page wasn't accessible to you."
        ),
    }[evidence]

    verification_prompt = f"""
        [TASK]
        Decide whether the evidence below genuinely belongs to / is meaningfully about a SPECIFIC person.

        [TARGET DETAILS]
        - Full name: {target_name or "unknown"}
        - City: {city or "unknown"}
        - Other known details: {keywords or []}

        [EVIDENCE SOURCE]
        {evidence_source_desc}
        {corroboration_note}
        This URL was returned by a search engine for the query: "{matched_query or "N/A"}"

        [EVIDENCE]
        {evidence_text}

        [RULES]
        - VALID_PROFILE: this is a profile, bio, article, or document genuinely about this specific
          person (name matches, plus ideally at least one other detail like city/profession/school —
          but an unambiguous, low-collision full-name match on a personal profile URL is enough on its
          own, especially for evidence from search_snippet_only).
        - NOT_FOUND: explicit error signals — 'page not found', 'user does not exist', '404',
          'account doesn't exist', 'profile is private'.
        - GENERIC_ERROR: real evidence, but NOT about this specific person — a different person sharing
          the name, a generic homepage, or unrelated content.

        [OUTPUT FORMAT]
        Respond with ONLY a single valid JSON object, no markdown:
        {{"status": "VALID_PROFILE" | "NOT_FOUND" | "GENERIC_ERROR",
          "confidence": <integer 0-100>,
          "matched_on": ["short list of which target details this evidence actually confirms"]}}
    """
    try:
        ai_response = model.generate_content(verification_prompt)
        clean = ai_response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(clean)
        result.setdefault("confidence", 0)
        result.setdefault("matched_on", [])
        if result.get("status") == "VALID_PROFILE" and engine_count >= 2:
            bonus = 5 if engine_count == 2 else 10
            result["confidence"] = min(100, result["confidence"] + bonus)
        result["evidence"] = evidence
        return result
    except Exception:
        try:
            text = ai_response.text.strip().upper()
            if "VALID" in text:
                return {"status": "VALID_PROFILE", "confidence": 50, "matched_on": [], "evidence": evidence}
            if "NOT_FOUND" in text:
                return {"status": "NOT_FOUND", "confidence": 0, "matched_on": [], "evidence": evidence}
        except Exception:
            pass
        return {"status": "UNKNOWN_ERROR", "confidence": 0, "matched_on": [], "evidence": evidence}


def run_social_analyzer(username: str) -> dict:
    if not username:
        return None
    try:
        command = ["social-analyzer", "--username", username, "--output", "json"]
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8"
        )
        stdout, _ = process.communicate()
        if process.returncode != 0:
            return None
        return json.loads(stdout)
    except Exception:
        return None


# ── Search dorks (Google + Bing + DuckDuckGo, run concurrently) ─────────────
def build_dork_queries(full_name: str, city: str = None, keywords: list = None) -> list:
    if not full_name:
        return []

    keywords = keywords or []
    base = f'"{full_name}"'
    queries = [base]

    if city:
        queries.append(f'{base} "{city}"')
    if keywords:
        queries.append(f'{base} {" ".join(keywords)}')
        if city:
            queries.append(f'{base} "{city}" {" ".join(keywords)}')

    platform_sites = [
        "linkedin.com/in",
        "facebook.com",
        "instagram.com",
        "twitter.com OR site:x.com",
        "github.com",
        "medium.com",
    ]
    for site in platform_sites:
        q = f'{base} site:{site}'
        if city:
            q += f' "{city}"'
        queries.append(q)

    queries.append(f'{base} filetype:pdf OR filetype:doc OR filetype:docx')
    if city:
        queries.append(f'{base} "{city}" haber OR "basın" OR news')

    if city:
        queries.append(f'{full_name} {city}')
    else:
        queries.append(full_name)

    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)
    return unique_queries


def run_google_dorks(queries: list, num_results: int = 8, progress_callback=None) -> list:
    hits = []
    for i, query in enumerate(queries):
        results = None
        for attempt in range(2):
            try:
                results = list(search(query, num_results=num_results, lang="tr", advanced=True))
                break
            except Exception:
                if attempt == 0:
                    time.sleep(random.uniform(2.0, 3.5))
        if results:
            for r in results:
                hits.append({"url": r.url, "title": r.title or "", "snippet": r.description or "",
                              "engine": "google", "query": query})
            if progress_callback:
                progress_callback(f"Google [{i + 1}/{len(queries)}]: '{query[:60]}' → {len(results)} sonuç")
        elif progress_callback:
            progress_callback(f"Google [{i + 1}/{len(queries)}]: '{query[:60]}' → engellendi, devam ediliyor")
        time.sleep(random.uniform(1.2, 2.5))
    return hits


def run_bing_dorks(queries: list, num_results: int = 8, progress_callback=None) -> list:
    hits = []
    for i, query in enumerate(queries):
        resp = None
        for attempt in range(2):
            try:
                resp = requests.get(
                    "https://www.bing.com/search",
                    params={"q": query, "count": num_results},
                    headers=_HTTP_HEADERS,
                    timeout=10,
                )
                resp.raise_for_status()
                break
            except Exception:
                resp = None
                if attempt == 0:
                    time.sleep(random.uniform(1.5, 2.5))
        if resp is not None:
            try:
                soup = BeautifulSoup(resp.text, "html.parser")
                count = 0
                for li in soup.select("li.b_algo")[:num_results]:
                    a = li.select_one("h2 a")
                    if not a or not a.get("href", "").startswith("http"):
                        continue
                    caption = li.select_one(".b_caption p") or li.select_one(".b_caption")
                    snippet = caption.get_text(" ", strip=True) if caption else ""
                    hits.append({"url": a["href"], "title": a.get_text(" ", strip=True), "snippet": snippet,
                                 "engine": "bing", "query": query})
                    count += 1
                if progress_callback:
                    progress_callback(f"Bing [{i + 1}/{len(queries)}]: '{query[:60]}' → {count} sonuç")
            except Exception:
                if progress_callback:
                    progress_callback(f"Bing [{i + 1}/{len(queries)}]: '{query[:60]}' → ayrıştırma hatası")
        elif progress_callback:
            progress_callback(f"Bing [{i + 1}/{len(queries)}]: '{query[:60]}' → hata, devam ediliyor")
        time.sleep(random.uniform(0.8, 1.6))
    return hits


def run_duckduckgo_dorks(queries: list, num_results: int = 8, progress_callback=None) -> list:
    hits = []
    for i, query in enumerate(queries):
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=_HTTP_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            count = 0
            for result in soup.select(".result")[:num_results]:
                a = result.select_one("a.result__a")
                if not a:
                    continue
                href = a.get("href")
                if not href:
                    continue
                if "uddg=" in href:
                    qs = parse_qs(urlparse(href).query)
                    real = qs.get("uddg", [None])[0]
                    href = unquote(real) if real else None
                if not href or not href.startswith("http"):
                    continue
                snippet_el = result.select_one("a.result__snippet") or result.select_one(".result__snippet")
                snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
                hits.append({"url": href, "title": a.get_text(" ", strip=True), "snippet": snippet,
                             "engine": "duckduckgo", "query": query})
                count += 1
            if progress_callback:
                progress_callback(f"DuckDuckGo [{i + 1}/{len(queries)}]: '{query[:60]}' → {count} sonuç")
        except Exception:
            if progress_callback:
                progress_callback(f"DuckDuckGo [{i + 1}/{len(queries)}]: '{query[:60]}' → hata, devam ediliyor")
        time.sleep(random.uniform(0.6, 1.4))
    return hits


def run_all_dorks(queries: list, progress_callback=None) -> dict:
    """Runs Google, Bing, and DuckDuckGo concurrently and returns a merged
    {normalized_url: {url, title, snippet, engines, query}} dict."""
    engines = [run_google_dorks, run_bing_dorks, run_duckduckgo_dorks]
    all_hits = []
    with ThreadPoolExecutor(max_workers=len(engines)) as executor:
        futures = [executor.submit(engine, queries, 8, progress_callback) for engine in engines]
        for future in as_completed(futures):
            try:
                all_hits.extend(future.result())
            except Exception:
                pass
    return merge_search_hits(all_hits)


def verify_urls_parallel(
    merged_hits: dict, model, target_name: str = None, city: str = None, keywords: list = None,
    progress_callback=None, max_workers: int = 5, min_confidence: int = 40,
) -> list:
    verified = []
    total = len(merged_hits)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                verify_profile_existence, entry["url"], model, target_name, city, keywords,
                entry.get("title", ""), entry.get("snippet", ""), entry.get("query", ""),
                max(1, len(entry.get("engines", set()))),
            ): entry["url"]
            for entry in merged_hits.values()
        }
        for future in as_completed(futures):
            url = futures[future]
            completed += 1
            if progress_callback:
                short_url = url[:65] + "..." if len(url) > 65 else url
                progress_callback(f"[{completed}/{total}] Doğrulanıyor: {short_url}")
            try:
                result = future.result()
                if result.get("status") == "VALID_PROFILE" and result.get("confidence", 0) >= min_confidence:
                    key = normalize_url(url)
                    verified.append({
                        "url": url,
                        "verification_status": "Confirmed_Profile",
                        "confidence": result.get("confidence", 0),
                        "matched_on": result.get("matched_on", []),
                        "evidence_source": result.get("evidence", "unknown"),
                        "sources": sorted(merged_hits.get(key, {}).get("engines", set())),
                    })
            except Exception:
                pass

    verified.sort(key=lambda v: v.get("confidence", 0), reverse=True)
    return verified


def analyze_fused_data_with_ai(
    user_input: str,
    verified_data: list,
    keywords: list,
    model,
    language_code: str,
    methodology: list = None,
) -> str:
    LANG_MAP = {
        "en": "English",
        "tr": "Turkish (Türkçe)",
        "ru": "Russian (Русский)",
    }
    language_name = LANG_MAP.get(language_code, "English")
    methodology = methodology or []

    prompt = f"""
        [REPORT LANGUAGE]
        You MUST produce the entire report in: **{language_name}**.
        All headers, analyses, and summaries must be written strictly in {language_name}.

        [PERSONA]
        You are a senior intelligence analyst and investigative journalist. Your guiding principle is
        "Evidence First." Back every claim with a verifiable source link. Goal: maximum detail and transparency.

        [PRIMARY TASK]
        Produce an exhaustive intelligence profile from all data below. Each item includes a confidence
        score (0-100), which sources/engines independently corroborated it, and whether it came from a
        full page read, an archived snapshot, or a search-engine snippet only — use these to calibrate
        how confidently you state each finding.
        1. Synthesize ALL data points. Do not omit details.
        2. Correlate information. State connections between different accounts explicitly.
        3. Provide Direct Evidence. Include source links for every profile or document mentioned.
        4. Incorporate initial keywords into your analysis.
        5. Flag any items with confidence below 60 as "needs manual verification" rather than fact.

        [INITIAL CONTEXT]
        - Original User Request: "{user_input}"
        - Extracted Keywords: {keywords}
        - Sources/tools used in this investigation: {methodology}

        [VERIFIED OSINT DATA] (sorted by confidence, highest first)
        {json.dumps(verified_data, indent=2, ensure_ascii=False)}

        [MANDATORY REPORT STRUCTURE]
        Use the following Markdown structure:

        # Intelligence Profile: [Target's Inferred Full Name]

        ## 1. Methodology
        Briefly list which sources/tools were used for this investigation (from the list above) and
        how confidence scores should be interpreted (full page > archived snapshot > search snippet only;
        corroboration by multiple independent sources increases confidence).

        ## 2. Executive Summary
        One-paragraph overview of the target's digital identity, primary activities, and key characteristics.

        ## 3. Detailed Findings & Evidence

        ### 3.1. Verified Professional & Technical Profiles
        Analyze profiles from GitHub, LinkedIn, Reddit, Keybase, etc. Include confidence and corroborating
        sources for each.
        - **[Platform]:** [URL] — Confidence: [X]% — Corroborated by: [sources] — [Detailed analysis]

        ### 3.2. Verified Social Media Presence
        Analyze confirmed accounts from Facebook, Instagram, Twitter/X, etc. Include confidence for each.
        - **[Platform]:** [URL] — Confidence: [X]% — Corroborated by: [sources] — [Detailed analysis]

        ### 3.3. Verified Public Documents & Footprints
        Documents, articles, and public posts found via search dorking.
        - **[URL]** — Type: [CV/Paper/Post] — Confidence: [X]% — [Analysis]

        ## 4. Analyst's Assessment & Conclusion
        - **Synthesis:** Coherent narrative about the target's digital persona.
        - **Inconsistencies:** Note any contradictions in the data.
        - **Low-Confidence Items:** List anything under 60% confidence and why it needs manual review.
        - **Actionable Intelligence:** Key takeaways.
        - **Next Steps:** Specific suggestions for deeper investigation.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Final AI analysis failed: {e}"


def osint(
    user_input: str,
    language_code: str = "en",
    backend: str = None,
    model_name: str = None,
    ollama_host: str = None,
    progress_callback=None,
) -> str:
    if progress_callback:
        progress_callback("Initializing AI model...")

    try:
        model = initialize_model(backend, model_name, ollama_host)
        social_analyzer_available = check_tool_installed("social-analyzer")
    except Exception as e:
        raise RuntimeError(str(e))

    if progress_callback:
        progress_callback("Extracting target entities with AI...")

    entities = extract_entities_with_ai(user_input, model)
    if not entities:
        raise RuntimeError("Could not understand the initial request. Please be more specific.")

    target_username = entities.get("username") or None
    target_name = entities.get("full_name") or None
    target_city = entities.get("city") or None
    target_keywords = entities.get("keywords") or []

    if not target_name and not target_username:
        raise RuntimeError(
            "Could not extract a name or username from the request. "
            "Please provide at least a full name (and ideally a city)."
        )

    merged_hits = {}
    preconfirmed = []
    methodology = []

    if target_username and social_analyzer_available:
        if progress_callback:
            progress_callback(f"Running social-analyzer for username: {target_username}...")
        social_results = run_social_analyzer(target_username)
        methodology.append("social-analyzer (username scan)")
        if social_results and social_results.get("detected"):
            extra_hits = [
                {"url": item["link"], "title": "", "snippet": "", "engine": "social-analyzer", "query": target_username}
                for item in social_results["detected"] if item.get("link")
            ]
            merged_hits.update(merge_search_hits(extra_hits))
    elif target_username and not social_analyzer_available and progress_callback:
        progress_callback("'social-analyzer' kurulu değil, bu adım atlanıyor...")

    if target_name:
        guess_pool = [target_username] if target_username else []
        guess_pool += generate_username_candidates(target_name)
        guess_pool = list(dict.fromkeys(filter(None, guess_pool)))

        if progress_callback:
            progress_callback(f"Olası kullanıcı adları deneniyor: {', '.join(guess_pool[:8])}...")
        preconfirmed = probe_username_candidates(guess_pool, progress_callback=progress_callback)
        methodology.append("GitHub / Reddit / Keybase API (username-guess verification)")

        dork_queries = build_dork_queries(target_name, target_city, target_keywords)
        if progress_callback:
            progress_callback(
                f"Built {len(dork_queries)} search dorks for '{target_name}'"
                + (f" in '{target_city}'" if target_city else "") + " (Google + Bing + DuckDuckGo)..."
            )
        dork_hits = run_all_dorks(dork_queries, progress_callback=progress_callback)
        methodology.append("Google, Bing, and DuckDuckGo search dorking")
        methodology.append("Wayback Machine archive fallback (for blocked/JS-walled pages)")
        for key, entry in dork_hits.items():
            if key in merged_hits:
                existing = merged_hits[key]
                if len(entry["title"]) > len(existing["title"]):
                    existing["title"] = entry["title"]
                if len(entry["snippet"]) > len(existing["snippet"]):
                    existing["snippet"] = entry["snippet"]
                existing["engines"] |= entry["engines"]
            else:
                merged_hits[key] = entry

    preconfirmed_urls = {normalize_url(p["url"]) for p in preconfirmed}
    merged_hits = {k: v for k, v in merged_hits.items() if k not in preconfirmed_urls}

    if not merged_hits and not preconfirmed:
        return (
            "**Info:** No potential profiles or links found for the target. "
            "Try adding more details (city, profession, school) to the request."
        )

    verified_data = list(preconfirmed)
    if merged_hits:
        if progress_callback:
            progress_callback(f"Starting verification of {len(merged_hits)} URLs (parallel)...")
        verified_data.extend(
            verify_urls_parallel(
                merged_hits, model,
                target_name=target_name, city=target_city, keywords=target_keywords,
                progress_callback=progress_callback,
            )
        )

    if not verified_data:
        return (
            f"**Info:** {len(merged_hits)} potansiyel bağlantı bulundu ancak hiçbiri yeterli güvenle "
            "doğrulanamadı. Kişi bilgilerini biraz daha detaylandırmayı (meslek, okul, ilgi alanı) "
            "deneyebilirsin."
        )

    verified_data.sort(key=lambda v: v.get("confidence", 0), reverse=True)

    if progress_callback:
        progress_callback(f"Generating final intelligence report ({len(verified_data)} confirmed profiles)...")

    final_report = analyze_fused_data_with_ai(
        user_input, verified_data, target_keywords, model, language_code, methodology
    )

    try:
        base_dir = get_base_dir()
        out_dir = os.path.join(base_dir, "osints")
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(
            c for c in (target_username or target_name or "report") if c.isalnum() or c in ("_", "-", " ")
        ).strip().replace(" ", "_")
        filename = os.path.join(out_dir, f"OSINT_Report_{safe_name}_{timestamp}.md")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_report)
        if progress_callback:
            progress_callback(f"Report saved → {os.path.basename(filename)}")
    except Exception:
        pass

    return final_report
