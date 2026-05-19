import os
import json
import time
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from googlesearch import search
from utils import initialize_gemini, check_tool_installed, get_base_dir

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException


def get_webdriver():
    try:
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
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


def extract_entities_with_ai(user_input: str, model) -> dict:
    prompt = f"""
        [TASK]
        You are an information extraction system. From the user's request, extract the following entities:
        a probable username, the person's full name, and any other descriptive keywords (like profession, city, hobbies).

        [OUTPUT FORMAT]
        Your response MUST be a single, valid JSON object with the keys "username", "full_name",
        and "keywords" (which should be a list of strings).

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


def verify_profile_existence_with_selenium(url: str, model) -> str:
    driver = get_webdriver()
    if not driver:
        return "NO_BROWSER_FOUND"

    try:
        driver.get(url)
        time.sleep(4)

        for text in ["Accept", "Allow all", "Agree", "Kabul Et", "Onayla"]:
            try:
                xpath = (
                    f"//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                    f"'abcdefghijklmnopqrstuvwxyz'), '{text.lower()}')]"
                )
                btn = driver.find_element(By.XPATH, xpath)
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    time.sleep(2)
                    break
            except NoSuchElementException:
                pass

        page_source = driver.page_source
    except Exception:
        return "SELENIUM_ERROR"
    finally:
        driver.quit()

    try:
        soup = BeautifulSoup(page_source, "html.parser")
        page_text = soup.get_text(separator=" ", strip=True)
        if not page_text:
            return "NO_TEXT_FOUND"

        truncated = page_text[:4000]
        verification_prompt = f"""
            [TASK]
            Analyze the webpage text below and classify it as one of three categories.

            [RULES]
            - VALID_PROFILE: contains personal details — name, bio, projects, follower counts, join date.
            - NOT_FOUND: contains explicit error messages like 'page not found', 'user does not exist',
              'This account doesn't exist', 'profile is private'.
            - GENERIC_ERROR: valid page but NOT a user profile — login screens, cookie walls,
              main homepages, 'search for other users' pages.

            [PAGE TEXT]
            "{truncated}"

            [YOUR RESPONSE]
            Respond with ONLY one keyword: VALID_PROFILE, NOT_FOUND, or GENERIC_ERROR
        """
        ai_response = model.generate_content(verification_prompt)
        return ai_response.text.strip().upper()
    except Exception:
        return "UNKNOWN_ERROR"


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


def run_google_dorks(full_name: str, keywords: list, num_results: int = 10) -> list:
    if not full_name:
        return None
    queries = [f'"{full_name}"']
    if keywords:
        queries.append(f'"{full_name}" {" ".join(keywords)}')
        queries.append(f'"{full_name}" filetype:pdf OR filetype:doc OR filetype:docx')

    all_urls = []
    try:
        for query in queries:
            results = search(query, num_results=num_results, lang="en")
            all_urls.extend(list(results))
        return list(set(all_urls))
    except Exception:
        return None


def verify_urls_parallel(urls: list, model, progress_callback=None, max_workers: int = 3) -> list:
    verified = []
    total = len(urls)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(verify_profile_existence_with_selenium, url, model): url
            for url in urls
        }
        for future in as_completed(futures):
            url = futures[future]
            completed += 1
            if progress_callback:
                short_url = url[:65] + "..." if len(url) > 65 else url
                progress_callback(f"[{completed}/{total}] Checking: {short_url}")
            try:
                status = future.result()
                if status == "VALID_PROFILE":
                    verified.append({"url": url, "verification_status": "Confirmed_Profile"})
            except Exception:
                pass

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
        Produce an exhaustive intelligence profile from all data below.
        1. Synthesize ALL data points. Do not omit details.
        2. Correlate information. State connections between different accounts explicitly.
        3. Provide Direct Evidence. Include source links for every profile or document mentioned.
        4. Incorporate initial keywords into your analysis.

        [INITIAL CONTEXT]
        - Original User Request: "{user_input}"
        - Extracted Keywords: {keywords}

        [VERIFIED OSINT DATA]
        {json.dumps(verified_data, indent=2, ensure_ascii=False)}

        [MANDATORY REPORT STRUCTURE]
        Use the following Markdown structure:

        # Intelligence Profile: [Target's Inferred Full Name]

        ## 1. Executive Summary
        One-paragraph overview of the target's digital identity, primary activities, and key characteristics.

        ## 2. Detailed Findings & Evidence

        ### 2.1. Verified Professional & Technical Profiles
        Analyze profiles from GitHub, Freelancer, LinkedIn, etc.
        - **[Platform]:** [URL] — [Detailed analysis]

        ### 2.2. Verified Social Media Presence
        Analyze confirmed accounts from Facebook, Instagram, Twitter, VK, Reddit, etc.
        - **[Platform]:** [URL] — [Detailed analysis]

        ### 2.3. Verified Public Documents & Footprints
        Documents, articles, and public posts found via Google Dorking.
        - **[URL]** — Type: [CV/Paper/Post] — [Analysis]

        ## 3. Analyst's Assessment & Conclusion
        - **Synthesis:** Coherent narrative about the target's digital persona.
        - **Inconsistencies:** Note any contradictions in the data.
        - **Actionable Intelligence:** Key takeaways.
        - **Next Steps:** Specific suggestions for deeper investigation.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Final AI analysis failed: {e}"


def osint(user_input: str, language_code: str = "en", progress_callback=None) -> str:
    if progress_callback:
        progress_callback("Initializing AI model...")

    try:
        model = initialize_gemini()
        if not check_tool_installed("social-analyzer"):
            raise RuntimeError(
                "'social-analyzer' is not installed. Run: pip3 install social-analyzer"
            )
    except Exception as e:
        raise RuntimeError(str(e))

    if progress_callback:
        progress_callback("Extracting target entities with AI...")

    entities = extract_entities_with_ai(user_input, model)
    if not entities:
        raise RuntimeError("Could not understand the initial request. Please be more specific.")

    target_username = entities.get("username")
    target_name = entities.get("full_name")
    target_keywords = entities.get("keywords", [])

    if progress_callback:
        progress_callback(f"Running social-analyzer for username: {target_username}...")

    social_results = run_social_analyzer(target_username)

    if progress_callback:
        progress_callback(f"Running Google Dorks for: {target_name}...")

    google_results = run_google_dorks(target_name, target_keywords)

    candidate_urls = []
    if social_results and social_results.get("detected"):
        for item in social_results["detected"]:
            if item.get("link"):
                candidate_urls.append(item["link"])
    if google_results:
        candidate_urls.extend(google_results)

    unique_urls = list(set(filter(None, candidate_urls)))

    if not unique_urls:
        return "**Info:** No potential profiles or links found for the target."

    if progress_callback:
        progress_callback(f"Starting verification of {len(unique_urls)} URLs (parallel)...")

    verified_data = verify_urls_parallel(unique_urls, model, progress_callback=progress_callback)

    if not verified_data:
        return "**Info:** All potential links were checked, but no confirmed profiles were found."

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
            c for c in (target_username or "report") if c.isalnum() or c in ("_", "-")
        ).rstrip()
        filename = os.path.join(out_dir, f"OSINT_Report_{safe_name}_{timestamp}.md")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_report)
        if progress_callback:
            progress_callback(f"Report saved → {os.path.basename(filename)}")
    except Exception:
        pass

    return final_report
