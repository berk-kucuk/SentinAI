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
    """Realistic username permutations from a full name, the same way a
    person would actually pick a handle. Lets the tool find profiles even
    when the user never gave a username."""
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
    """GitHub's REST API gives a clean, deterministic 200/404 — no scraping,
    no false positives from SPA shells."""
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


def probe_username_candidates(candidates: list, progress_callback=None, max_workers: int = 6) -> list:
    """Directly checks GitHub for each candidate handle. Confirmed hits are
    deterministic — no AI classification needed for these."""
    confirmed = []
    if not candidates:
        return confirmed

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_github_username, c): c for c in candidates}
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                url = future.result()
                if url:
                    confirmed.append({"url": url, "verification_status": "Confirmed_Profile",
                                       "confidence": 95, "source": "github_api_username_guess"})
                    if progress_callback:
                        progress_callback(f"GitHub'da kullanıcı adı eşleşmesi bulundu: {candidate}")
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


def dedupe_urls(urls: list) -> list:
    seen = set()
    result = []
    for u in urls:
        if not u:
            continue
        key = normalize_url(u)
        if key not in seen:
            seen.add(key)
            result.append(u)
    return result


# ── Static fetch + hybrid verification with confidence scoring ──────────────
def _fetch_static(url: str, timeout: int = 10):
    """Fast, browser-less fetch. Covers the large majority of pages (news
    sites, blogs, GitHub, public LinkedIn/Facebook snapshots, forums,
    government/company pages, PDFs served as HTML, etc.) with no local
    Chrome/Firefox install required."""
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code >= 400:
            return None
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text
    except requests.exceptions.RequestException:
        return None


def _name_tokens(full_name: str) -> list:
    if not full_name:
        return []
    return [t for t in re.findall(r"\w+", full_name.lower()) if len(t) > 1]


def verify_profile_existence(url: str, model, target_name: str = None, city: str = None, keywords: list = None) -> dict:
    """Hybrid verification pipeline:
      1. Fetch statically (fast, no browser needed).
      2. Escalate to a headless browser only if content is too thin AND a
         driver is actually available — a missing browser never silently
         drops a URL anymore.
      3. Cheap relevance pre-filter: if NONE of the person's name tokens
         appear anywhere on the page, skip the AI call entirely.
      4. AI classification now returns a confidence score, not just a
         keyword, to guard against common-name false positives.
    """
    page_source = _fetch_static(url)
    text_len = 0
    if page_source:
        text_len = len(BeautifulSoup(page_source, "html.parser").get_text(strip=True))

    if text_len < 200:
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
                    page_source = rendered
            except Exception:
                pass
            finally:
                driver.quit()

    if not page_source:
        return {"status": "NO_CONTENT_FOUND", "confidence": 0}

    soup = BeautifulSoup(page_source, "html.parser")
    page_text = soup.get_text(separator=" ", strip=True)
    if not page_text:
        return {"status": "NO_TEXT_FOUND", "confidence": 0}

    # Cheap relevance gate — avoids wasting an AI call (and avoids false
    # positives) on pages that don't mention the person at all.
    tokens = _name_tokens(target_name)
    lower_text = page_text.lower()
    if tokens and not any(tok in lower_text for tok in tokens):
        return {"status": "GENERIC_ERROR", "confidence": 0}

    truncated = page_text[:4000]
    verification_prompt = f"""
        [TASK]
        Analyze the webpage text below and decide whether it genuinely belongs to / is meaningfully
        about a SPECIFIC person, given the target details.

        [TARGET DETAILS]
        - Full name: {target_name or "unknown"}
        - City: {city or "unknown"}
        - Other known details: {keywords or []}

        [RULES]
        - VALID_PROFILE: the page is a profile, bio, article, or document that is genuinely about this
          specific person (matches name plus at least one other detail like city/profession/school, OR
          is an unambiguous, low-collision name match).
        - NOT_FOUND: explicit error messages like 'page not found', 'user does not exist', '404',
          'this account doesn't exist', 'profile is private'.
        - GENERIC_ERROR: a real page, but NOT about this specific person — a different person who
          happens to share the name, a login screen, cookie wall, homepage, or unrelated content.

        [PAGE TEXT]
        "{truncated}"

        [OUTPUT FORMAT]
        Respond with ONLY a single valid JSON object, no markdown:
        {{"status": "VALID_PROFILE" | "NOT_FOUND" | "GENERIC_ERROR",
          "confidence": <integer 0-100, how sure you are this page is genuinely about the target>,
          "matched_on": ["short list of which target details this page actually confirms"]}}
    """
    try:
        ai_response = model.generate_content(verification_prompt)
        clean = ai_response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(clean)
        result.setdefault("confidence", 0)
        result.setdefault("matched_on", [])
        return result
    except Exception:
        # Fall back to a plain keyword read if the model didn't return valid JSON
        try:
            text = ai_response.text.strip().upper()
            if "VALID" in text:
                return {"status": "VALID_PROFILE", "confidence": 60, "matched_on": []}
            if "NOT_FOUND" in text:
                return {"status": "NOT_FOUND", "confidence": 0, "matched_on": []}
        except Exception:
            pass
        return {"status": "UNKNOWN_ERROR", "confidence": 0, "matched_on": []}


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
    """Broad set of dork queries. Works with just a full name + city
    (no username required). Mixes precise (quoted, site:-filtered) queries
    with a couple of looser ones for recall."""
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

    # Loose (unquoted) variant for extra recall — catches pages where the
    # name appears with different word order/spacing than an exact quote.
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
    all_urls = []
    for i, query in enumerate(queries):
        try:
            results = list(search(query, num_results=num_results, lang="tr"))
            all_urls.extend(results)
            if progress_callback:
                progress_callback(f"Google [{i + 1}/{len(queries)}]: '{query[:60]}' → {len(results)} sonuç")
        except Exception:
            if progress_callback:
                progress_callback(f"Google [{i + 1}/{len(queries)}]: '{query[:60]}' → engellendi, devam ediliyor")
        time.sleep(random.uniform(1.2, 2.5))
    return dedupe_urls(all_urls)


def run_bing_dorks(queries: list, num_results: int = 8, progress_callback=None) -> list:
    all_urls = []
    for i, query in enumerate(queries):
        try:
            resp = requests.get(
                "https://www.bing.com/search",
                params={"q": query, "count": num_results},
                headers=_HTTP_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            links = [a.get("href") for a in soup.select("li.b_algo h2 a") if a.get("href", "").startswith("http")]
            all_urls.extend(links[:num_results])
            if progress_callback:
                progress_callback(f"Bing [{i + 1}/{len(queries)}]: '{query[:60]}' → {len(links)} sonuç")
        except Exception:
            if progress_callback:
                progress_callback(f"Bing [{i + 1}/{len(queries)}]: '{query[:60]}' → hata, devam ediliyor")
        time.sleep(random.uniform(0.8, 1.6))
    return dedupe_urls(all_urls)


def run_duckduckgo_dorks(queries: list, num_results: int = 8, progress_callback=None) -> list:
    """DuckDuckGo's HTML endpoint is not JS-rendered and is far less
    aggressive about blocking automated queries than Google, making it a
    reliable third source."""
    all_urls = []
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
            links = []
            for a in soup.select("a.result__a")[:num_results]:
                href = a.get("href")
                if not href:
                    continue
                if "uddg=" in href:
                    qs = parse_qs(urlparse(href).query)
                    real = qs.get("uddg", [None])[0]
                    if real:
                        links.append(unquote(real))
                elif href.startswith("http"):
                    links.append(href)
            all_urls.extend(links)
            if progress_callback:
                progress_callback(f"DuckDuckGo [{i + 1}/{len(queries)}]: '{query[:60]}' → {len(links)} sonuç")
        except Exception:
            if progress_callback:
                progress_callback(f"DuckDuckGo [{i + 1}/{len(queries)}]: '{query[:60]}' → hata, devam ediliyor")
        time.sleep(random.uniform(0.6, 1.4))
    return dedupe_urls(all_urls)


def run_all_dorks(queries: list, progress_callback=None) -> list:
    """Runs Google, Bing, and DuckDuckGo concurrently (they're independent
    services, so one being rate-limited doesn't slow down the others)."""
    engines = [run_google_dorks, run_bing_dorks, run_duckduckgo_dorks]
    all_urls = []
    with ThreadPoolExecutor(max_workers=len(engines)) as executor:
        futures = [executor.submit(engine, queries, 8, progress_callback) for engine in engines]
        for future in as_completed(futures):
            try:
                all_urls.extend(future.result())
            except Exception:
                pass
    return dedupe_urls(all_urls)


def verify_urls_parallel(
    urls: list, model, target_name: str = None, city: str = None, keywords: list = None,
    progress_callback=None, max_workers: int = 5, min_confidence: int = 55,
) -> list:
    verified = []
    total = len(urls)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(verify_profile_existence, url, model, target_name, city, keywords): url
            for url in urls
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
                    verified.append({
                        "url": url,
                        "verification_status": "Confirmed_Profile",
                        "confidence": result.get("confidence", 0),
                        "matched_on": result.get("matched_on", []),
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
) -> str:
    LANG_MAP = {
        "en": "English",
        "tr": "Turkish (Türkçe)",
        "ru": "Russian (Русский)",
    }
    language_name = LANG_MAP.get(language_code, "English")

    prompt = f"""
        [REPORT LANGUAGE]
        You MUST produce the entire report in: **{language_name}**.
        All headers, analyses, and summaries must be written strictly in {language_name}.

        [PERSONA]
        You are a senior intelligence analyst and investigative journalist. Your guiding principle is
        "Evidence First." Back every claim with a verifiable source link. Goal: maximum detail and transparency.

        [PRIMARY TASK]
        Produce an exhaustive intelligence profile from all data below. Each item includes a confidence
        score (0-100) and the specific details it matched on — use these to calibrate how confidently you
        state each finding, and call out lower-confidence items as tentative / needing manual review.
        1. Synthesize ALL data points. Do not omit details.
        2. Correlate information. State connections between different accounts explicitly.
        3. Provide Direct Evidence. Include source links for every profile or document mentioned.
        4. Incorporate initial keywords into your analysis.
        5. Flag any items with confidence below 70 as "needs manual verification" rather than stating
           them as fact.

        [INITIAL CONTEXT]
        - Original User Request: "{user_input}"
        - Extracted Keywords: {keywords}

        [VERIFIED OSINT DATA] (sorted by confidence, highest first)
        {json.dumps(verified_data, indent=2, ensure_ascii=False)}

        [MANDATORY REPORT STRUCTURE]
        Use the following Markdown structure:

        # Intelligence Profile: [Target's Inferred Full Name]

        ## 1. Executive Summary
        One-paragraph overview of the target's digital identity, primary activities, and key characteristics.

        ## 2. Detailed Findings & Evidence

        ### 2.1. Verified Professional & Technical Profiles
        Analyze profiles from GitHub, LinkedIn, etc. Include confidence for each.
        - **[Platform]:** [URL] — Confidence: [X]% — [Detailed analysis]

        ### 2.2. Verified Social Media Presence
        Analyze confirmed accounts from Facebook, Instagram, Twitter/X, etc. Include confidence for each.
        - **[Platform]:** [URL] — Confidence: [X]% — [Detailed analysis]

        ### 2.3. Verified Public Documents & Footprints
        Documents, articles, and public posts found via search dorking.
        - **[URL]** — Type: [CV/Paper/Post] — Confidence: [X]% — [Analysis]

        ## 3. Analyst's Assessment & Conclusion
        - **Synthesis:** Coherent narrative about the target's digital persona.
        - **Inconsistencies:** Note any contradictions in the data.
        - **Low-Confidence Items:** List anything under 70% confidence and why it needs manual review.
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

    candidate_urls = []
    preconfirmed = []  # deterministic hits that skip AI verification (e.g. GitHub API)

    if target_username and social_analyzer_available:
        if progress_callback:
            progress_callback(f"Running social-analyzer for username: {target_username}...")
        social_results = run_social_analyzer(target_username)
        if social_results and social_results.get("detected"):
            for item in social_results["detected"]:
                if item.get("link"):
                    candidate_urls.append(item["link"])
    elif target_username and not social_analyzer_available and progress_callback:
        progress_callback("'social-analyzer' kurulu değil, bu adım atlanıyor...")

    if target_name:
        # Deterministic username-guessing pass (works even with zero username given)
        guess_pool = [target_username] if target_username else []
        guess_pool += generate_username_candidates(target_name)
        guess_pool = list(dict.fromkeys(filter(None, guess_pool)))

        if progress_callback:
            progress_callback(f"Olası kullanıcı adları deneniyor: {', '.join(guess_pool[:8])}...")
        preconfirmed = probe_username_candidates(guess_pool, progress_callback=progress_callback)

        dork_queries = build_dork_queries(target_name, target_city, target_keywords)
        if progress_callback:
            progress_callback(
                f"Built {len(dork_queries)} search dorks for '{target_name}'"
                + (f" in '{target_city}'" if target_city else "") + " (Google + Bing + DuckDuckGo)..."
            )
        candidate_urls.extend(run_all_dorks(dork_queries, progress_callback=progress_callback))

    unique_urls = dedupe_urls(candidate_urls)
    # Don't re-verify URLs we already deterministically confirmed
    preconfirmed_urls = {normalize_url(p["url"]) for p in preconfirmed}
    unique_urls = [u for u in unique_urls if normalize_url(u) not in preconfirmed_urls]

    if not unique_urls and not preconfirmed:
        return (
            "**Info:** No potential profiles or links found for the target. "
            "Try adding more details (city, profession, school) to the request."
        )

    verified_data = list(preconfirmed)
    if unique_urls:
        if progress_callback:
            progress_callback(f"Starting verification of {len(unique_urls)} URLs (parallel)...")
        verified_data.extend(
            verify_urls_parallel(
                unique_urls, model,
                target_name=target_name, city=target_city, keywords=target_keywords,
                progress_callback=progress_callback,
            )
        )

    if not verified_data:
        return (
            f"**Info:** {len(unique_urls)} potansiyel bağlantı bulundu ancak hiçbiri yeterli güvenle "
            "doğrulanamadı. Kişi bilgilerini biraz daha detaylandırmayı (meslek, okul, ilgi alanı) "
            "deneyebilirsin."
        )

    verified_data.sort(key=lambda v: v.get("confidence", 0), reverse=True)

    if progress_callback:
        progress_callback(f"Generating final intelligence report ({len(verified_data)} confirmed profiles)...")

    final_report = analyze_fused_data_with_ai(
        user_input, verified_data, target_keywords, model, language_code
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
