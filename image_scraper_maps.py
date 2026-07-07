#!/usr/bin/env python3
"""
Google Maps Images Scraper
Uses Selenium to fetch photos shown on a Google Maps place page for a given
query (e.g. "Eiffel Tower" or "Joe's Pizza NYC"). No API key required.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import quote
import os
import re
import sys
import time


# CSS selectors that target a clickable place result on the Maps search page.
# Several are listed because Google rotates class names periodically; the first
# one that matches is used.
RESULT_SELECTORS = [
    'a[href*="/maps/place/"]',
    'div[role="article"] a',
    '.section-result',
    'div[class*="section-result"]',
]

# CSS selectors that target place photos. Google serves them from
# googleusercontent.com; we accept several lh3/lh5 variants.
IMAGE_SELECTORS = [
    'img[src*="googleusercontent"]',
    'img[src*="lh3.googleusercontent.com"]',
    'img[src*="lh5.googleusercontent.com"]',
    'img[src*="maps.googleapis.com"]',
]

# Pattern used as a final safety net when iterating img elements: keep any src
# pointing at a known Google photo CDN.
GOOGLE_PHOTO_HOST_RE = re.compile(
    r"https?://(?:lh3|lh4|lh5|lh6)\.googleusercontent\.com/", re.IGNORECASE
)

# Phrases that appear on the "accept all" / "I agree" button of Google's
# consent page across locales. Lowercased substrings; we click the first
# consent-form button whose aria-label or text matches any of these.
CONSENT_ACCEPT_PATTERNS = [
    "accept all", "i agree", "agree", "yes, i agree",
    "aceitar tudo", "aceitar", "concordo",
    "aceptar todo", "aceptar", "acepto",
    "alle akzeptieren", "akzeptieren", "zustimmen",
    "tout accepter", "accepter", "j'accepte",
    "accetta tutto", "accetta", "accetto",
    "alles accepteren", "akkoord",
    "принять", "согласен",
    "同意", "すべて接受", "接受", "すべて同意",
]


def _build_options(headless: bool) -> Options:
    """Construct the Chrome options used for every run."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument(
        'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    if os.getenv('CHROME_BIN'):
        chrome_options.binary_location = os.getenv('CHROME_BIN')
    return chrome_options


def _build_driver(headless: bool):
    """Construct a Chrome WebDriver, honoring CHROMEDRIVER_PATH if set."""
    options = _build_options(headless)
    service_kwargs = {}
    if os.getenv('CHROMEDRIVER_PATH'):
        service_kwargs['executable_path'] = os.getenv('CHROMEDRIVER_PATH')
    return webdriver.Chrome(service=Service(**service_kwargs), options=options)


def _find_first(driver, selectors):
    """Return the first non-empty result across a list of CSS selectors."""
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        if elements:
            return elements
    return []


def _try_click_first_result(driver):
    """Click the first Maps search result to open the place panel.

    Best-effort: returns True on success, False if no result was found or the
    click raised. Callers should keep going either way — photos sometimes
    render directly on the search page.
    """
    results = _find_first(driver, RESULT_SELECTORS)
    if not results:
        return False
    try:
        results[0].click()
        return True
    except Exception as e:
        print(f"Could not click first result: {e}", file=sys.stderr)
        return False


def _accept_consent_if_present(driver):
    """If Google is showing its consent page, click the accept-all button.

    Google's consent dialog is served at consent.google.com and varies by
    locale ("Accept all", "Aceitar tudo", "Alle akzeptieren", ...). The
    button is always inside a <form action="...consent.google.com/save">.
    Best-effort: returns True if a button was clicked, False otherwise.
    """
    if "consent.google.com" not in (driver.current_url or ""):
        return False
    try:
        buttons = driver.find_elements(
            By.CSS_SELECTOR, 'form[action*="consent.google.com/save"] button'
        )
    except Exception:
        return False
    for btn in buttons:
        try:
            label = (
                (btn.get_attribute("aria-label") or "")
                + " "
                + (btn.text or "")
            ).lower()
        except Exception:
            continue
        if any(phrase in label for phrase in CONSENT_ACCEPT_PATTERNS):
            try:
                btn.click()
                return True
            except Exception as e:
                print(f"Could not click consent button: {e}", file=sys.stderr)
                return False
    return False


def _collect_image_urls(driver, num_images: int):
    """Collect up to num_images googleusercontent photo URLs from the page."""
    # Try the prioritized CSS selectors first.
    candidates = _find_first(driver, IMAGE_SELECTORS)

    # Fallback: any <img> whose src matches a Google photo CDN. This catches
    # the case where Google has rotated the class names again.
    if not candidates:
        all_imgs = driver.find_elements(By.TAG_NAME, 'img')
        candidates = [
            img for img in all_imgs
            if (img.get_attribute('src') or '').startswith(
                ('http://', 'https://')
            )
            and GOOGLE_PHOTO_HOST_RE.search(img.get_attribute('src') or '')
        ]

    images = []
    seen = set()
    for img in candidates:
        if len(images) >= num_images:
            break
        try:
            src = img.get_attribute('src')
        except Exception:
            continue
        if not src or src in seen:
            continue
        if not GOOGLE_PHOTO_HOST_RE.search(src):
            continue
        seen.add(src)
        images.append({'url': src, 'alt': '', 'title': ''})
    return images


def scrape_google_maps_images(query, num_images=5, headless=True):
    """
    Scrape Google Maps for place photos matching the given query.

    Args:
        query (str): Place to search for (e.g. "Eiffel Tower", "Joe's Pizza NYC")
        num_images (int): Maximum number of photos to return (default: 5)
        headless (bool): Run Chrome in headless mode (default: True)

    Returns:
        list: List of dicts with keys "url", "alt", "title". Empty on failure.
    """
    driver = None
    try:
        driver = _build_driver(headless)
    except Exception as e:
        print(f"Could not start Chrome: {e}", file=sys.stderr)
        return []

    try:
        encoded_query = quote(query)
        url = f"https://www.google.com/maps/search/{encoded_query}/"
        print(f"Loading: {url}")
        driver.get(url)

        # Handle Google's EU-style consent page if it appears.
        if _accept_consent_if_present(driver):
            print("Accepted Google consent page.")
            time.sleep(3)

        # Give the SPA time to mount the results list.
        time.sleep(3)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/maps/place/"]'))
            )
        except Exception:
            print("Results list did not appear within timeout; continuing anyway.", file=sys.stderr)

        clicked = _try_click_first_result(driver)
        if clicked:
            # Let the place panel render and load the photo strip.
            time.sleep(3)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'img[src*="googleusercontent"]'))
                )
            except Exception:
                print("Photo strip did not appear within timeout; continuing anyway.", file=sys.stderr)

        # Scroll the photo strip to encourage lazy loading.
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1)

        images = _collect_image_urls(driver, num_images)
        return images[:num_images]

    except Exception as e:
        print(f"Error during scraping: {e}", file=sys.stderr)
        return []
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def main():
    """Command-line entry point."""
    if len(sys.argv) < 2:
        print("Usage: python image_scraper_maps.py <search_query> [num_images]")
        print("Example: python image_scraper_maps.py 'Eiffel Tower' 5")
        sys.exit(1)

    query = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"Searching Google Maps for: {query}")
    print(f"Number of images: {num_images}\n")

    images = scrape_google_maps_images(query, num_images)

    if images:
        print(f"\n{'=' * 80}")
        print(f"Found {len(images)} images:\n")
        for idx, img in enumerate(images, 1):
            print(f"{idx}. {img['url']}")
    else:
        print("No images found. Google Maps may be blocking the request.")
        print("Try running with headless=False to debug.")


if __name__ == "__main__":
    main()
