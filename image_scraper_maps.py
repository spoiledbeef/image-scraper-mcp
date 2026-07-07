#!/usr/bin/env python3
"""
Google Maps Images Scraper
Uses Selenium to fetch photos shown on a Google Maps place page for a given
query (e.g. "Eiffel Tower" or "Joe's Pizza NYC"). No API key required.

Each returned photo carries the contributor's name and profile URL so callers
can credit the photographer if they reuse the image.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import quote
import json
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

# Match a CSS background-image value, e.g.
#   background-image: url('https://...'); or url("https://...")
BACKGROUND_IMAGE_RE = re.compile(r"""url\((['"]?)(.+?)\1\)""")

# Match an aria-label of the form "Photo N in the review by NAME" / "Foto N na
# crítica de NAME" / "Photographie N dans la critique par NAME", etc. Group 1
# captures the contributor's name.
AUTHOR_LABEL_RE = re.compile(
    r"^(?:Photo|Foto|Fotograf[ií]a|Photographie)\s+\d+\s+"
    r"(?:in the |of the |na |no |en la |en el |dans la |dans le |im |nella |nel )?"
    r"(?:review|cr[ií]tica|critica|reseña|resena|critique|rezension|recensione)\s+"
    r"(?:by|de|del|do|da|por|from|par|von|di|della)\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# CSS selector that finds review-photo buttons. Review photos are served via
# inline background-image (not <img src>), so anchoring on `background-image`
# avoids matching generic tooltip/info buttons that just happen to contain
# "crítica"/"review" in their aria-label.
AUTHOR_BUTTON_SELECTOR = (
    'button[style*="background-image"]'
)

# Heuristic to exclude reviewer avatars from the fallback image sweep.
# Avatars use small sizes with the `rp` (round-profile) flag, and the URL
# typically either ends after `-p-rp` or continues into `-mo-br100` etc.
AVATAR_SIZE_RE = re.compile(r"=w\d{1,3}-h\d{1,3}-p-rp(?:[-?&=]|$)", re.IGNORECASE)

# Match any photo hosted on Google's photo CDN.
GOOGLE_PHOTO_HOST_RE = re.compile(
    r"https?://(?:lh3|lh4|lh5|lh6)\.googleusercontent\.com/", re.IGNORECASE
)


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


def _parse_author_from_aria_label(aria_label):
    """Extract the author name from a review-photo aria-label.

    Accepts labels like "Photo 1 in the review by NAME" (English) or
    "Foto 1 na crítica de NAME" (Portuguese), among other locales.
    Returns the name string, or None if the label doesn't match a known
    review-photo pattern.
    """
    if not aria_label:
        return None
    m = AUTHOR_LABEL_RE.match(aria_label.strip())
    if m:
        return m.group(1).strip() or None
    return None


def _extract_background_image_url(button):
    """Pull the photo URL out of a button's inline background-image style.

    Returns the URL string or None. The button is a Selenium WebElement.
    """
    try:
        style = button.get_attribute("style") or ""
    except Exception:
        return None
    m = BACKGROUND_IMAGE_RE.search(style)
    if not m:
        return None
    return m.group(2).strip().strip("'\"")


def _find_associated_contrib_link(button):
    """Find the contributor profile link associated with a review photo button.

    Google's review layout puts the contributor avatar/link as a sibling of
    the photo button within the same review container. The link is rendered
    as a `<button data-href=".../maps/contrib/<id>/...">` (not an <a>), so
    we look for both anchor and button variants. We try several XPath
    positions to locate it; first match wins. Returns the href string or "".
    """
    # Each entry: (xpath, attribute_to_read)
    candidates = (
        (".//preceding-sibling::*[1]//*[@data-href]", "data-href"),
        (".//preceding-sibling::*[1]//a[@href]", "href"),
        (".//preceding-sibling::*[2]//*[@data-href]", "data-href"),
        (".//preceding-sibling::*[2]//a[@href]", "href"),
        (".//parent::*//*[@data-href]", "data-href"),
        (".//parent::*//a[@href]", "href"),
        (".//ancestor::*[2]//*[@data-href]", "data-href"),
        (".//ancestor::*[2]//a[@href]", "href"),
        (".//ancestor::*[3]//*[@data-href]", "data-href"),
        (".//ancestor::*[3]//a[@href]", "href"),
    )
    for xp, attr in candidates:
        try:
            elements = button.find_elements(By.XPATH, xp)
        except Exception:
            continue
        for el in elements:
            try:
                href = el.get_attribute(attr) or ""
            except Exception:
                continue
            if "/maps/contrib/" in href:
                return href
    return ""


def _extract_review_photos(driver, num_images):
    """Find up to num_images review-attributed photos on the place panel.

    Each entry has shape {"url", "author", "author_profile_url"}. Empty list
    if no review photos are present.
    """
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, AUTHOR_BUTTON_SELECTOR)
    except Exception:
        return []

    images = []
    seen = set()
    for btn in buttons:
        if len(images) >= num_images:
            break
        try:
            aria = btn.get_attribute("aria-label") or ""
        except Exception:
            continue
        author = _parse_author_from_aria_label(aria)
        if not author:
            continue
        url = _extract_background_image_url(btn)
        if not url or url in seen:
            continue
        seen.add(url)
        profile_url = _find_associated_contrib_link(btn)
        images.append({
            "url": url,
            "author": author,
            "author_profile_url": profile_url,
        })
    return images


def _extract_fallback_photos(driver, num_images):
    """Pull photo URLs from <img> tags as a non-attributed fallback.

    Reviewer avatars are filtered out by size-hint heuristic. Each entry has
    shape {"url", "author": "", "author_profile_url": ""}.
    """
    images = []
    seen = set()
    try:
        imgs = driver.find_elements(
            By.CSS_SELECTOR, 'img[src*="googleusercontent"]'
        )
    except Exception:
        return images
    for img in imgs:
        if len(images) >= num_images:
            break
        try:
            src = img.get_attribute("src") or ""
        except Exception:
            continue
        if not src or src in seen:
            continue
        if not GOOGLE_PHOTO_HOST_RE.search(src):
            continue
        if AVATAR_SIZE_RE.search(src):
            continue
        seen.add(src)
        images.append({
            "url": src,
            "author": "",
            "author_profile_url": "",
        })
    return images


def scrape_google_maps_images(query, num_images=5, headless=True, require_attribution=False):
    """Scrape Google Maps for place photos matching the given query.

    Args:
        query (str): Place to search for (e.g. "Eiffel Tower", "Joe's Pizza NYC")
        num_images (int): Maximum number of photos to return (default: 5)
        headless (bool): Run Chrome in headless mode (default: True)
        require_attribution (bool): If True, return only photos with visible
            author attribution. If False (default), prefer attributed photos
            but fall back to the place's official photo strip when fewer
            attributed photos are available. Attributed photos are always
            returned first.

    Returns:
        list: List of dicts with keys "url", "author", "author_profile_url".
              Empty on failure.
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
            time.sleep(3)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'button[aria-label*="review"], button[aria-label*="crítica"]'))
                )
            except Exception:
                print("Photo strip did not appear within timeout; continuing anyway.", file=sys.stderr)

        # Scroll the panel to encourage lazy loading of additional reviews.
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1)

        images = _extract_review_photos(driver, num_images)

        # Optionally top up with unattributed photos.
        if not require_attribution and len(images) < num_images:
            existing = {i["url"] for i in images}
            for img in _extract_fallback_photos(driver, num_images - len(images)):
                if img["url"] in existing:
                    continue
                images.append(img)
                if len(images) >= num_images:
                    break

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
    """Command-line entry point. Prints the result as JSON."""
    if len(sys.argv) < 2:
        print("Usage: python image_scraper_maps.py <search_query> [num_images]")
        print("Example: python image_scraper_maps.py 'Eiffel Tower' 5")
        sys.exit(1)

    query = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"Searching Google Maps for: {query}")
    print(f"Number of images: {num_images}\n")

    images = scrape_google_maps_images(query, num_images)

    payload = {
        "query": query,
        "source": "google_maps",
        "count": len(images),
        "images": images,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()