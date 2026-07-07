#!/usr/bin/env python3
"""
DuckDuckGo Images Scraper (Selenium version)
Uses Selenium WebDriver for browser automation to scrape image results and
their full source attribution (source page URL, publisher domain, article
title, image dimensions).
"""

import os
import re
import sys
import time
from urllib.parse import quote, unquote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


# DuckDuckGo serves result images through a redirector so it can strip
# referrers and attach a Content-Security-Policy nonce. The real source URL
# is URL-encoded in the `u` query param, e.g.
#     //external-content.duckduckgo.com/iu/?u=https%3A%2F%2Ftse1.mm.bing.net%2F...&f=1&...&ipo=images
# DDG uses both protocol-relative and absolute https:// forms depending on
# the page; accept both.
DDG_IMAGE_PROXY_RE = re.compile(
    r"^(?:https?:)?//external-content\.duckduckgo\.com/iu/\?u=(.+?)(?:&|$)",
    re.IGNORECASE,
)

# Same proxy but for favicons, which DDG serves at
# //external-content.duckduckgo.com/ip3/<domain>.ico. Filtering by /iu/
# (vs /ip3/) keeps us from mistaking a favicon for the result image.
DDG_FAVICON_PROXY_RE = re.compile(
    r"^(?:https?:)?//external-content\.duckduckgo\.com/ip3/(.+?)(?:&|$)",
    re.IGNORECASE,
)

# "2560 × 1707" / "2560 x 1707" / "2560*1707". DDG uses × (U+00D7) with spaces.
DIMENSIONS_RE = re.compile(r"(\d{1,5})\s*[×x\*]\s*(\d{1,5})")


def _build_options(headless: bool) -> Options:
    """Chrome options for every run. Kept consistent so DDG doesn't flag us
    as a different browser between scrapes."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    chrome_options.add_argument("--lang=en-US")
    if os.getenv("CHROME_BIN"):
        chrome_options.binary_location = os.getenv("CHROME_BIN")
    return chrome_options


def _build_driver(headless: bool):
    """Construct a Chrome WebDriver, honoring CHROMEDRIVER_PATH if set."""
    options = _build_options(headless)
    service_kwargs = {}
    if os.getenv("CHROMEDRIVER_PATH"):
        service_kwargs["executable_path"] = os.getenv("CHROMEDRIVER_PATH")
    return webdriver.Chrome(service=Service(**service_kwargs), options=options)


def _normalize_url(url: str) -> str:
    """DDG uses protocol-relative URLs (//foo.com/...). Convert to https://."""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://duckduckgo.com" + url
    return url


def _decode_proxied_image_url(src: str):
    """Unwrap DuckDuckGo's `external-content.duckduckgo.com/iu/?u=<encoded>`
    redirector to return the real source image URL.

    Returns None when `src` isn't a DDG proxied image URL.
    """
    if not src:
        return None
    m = DDG_IMAGE_PROXY_RE.search(src)
    if not m:
        return None
    try:
        return unquote(m.group(1))
    except Exception:
        return None


def _decode_proxied_favicon_url(src: str) -> str:
    """Extract the publisher domain out of a DDG favicon URL like
    `//external-content.duckduckgo.com/ip3/www.rd.com.ico`. Returns '' if
    the URL doesn't match the expected shape; the underlying favicon URL is
    kept in `favicon_url` separately and is usually what callers want."""
    if not src:
        return ""
    m = DDG_FAVICON_PROXY_RE.search(src)
    if not m:
        return ""
    try:
        return unquote(m.group(1).rstrip(".ico"))
    except Exception:
        return ""


def _parse_dimensions(text: str):
    """Parse a "2560 × 1707" string into (width, height) ints. Returns
    (None, None) when the string doesn't match."""
    if not text:
        return None, None
    m = DIMENSIONS_RE.search(text)
    if not m:
        return None, None
    try:
        return int(m.group(1)), int(m.group(2))
    except (ValueError, TypeError):
        return None, None


def _first_or_none(elements, getter):
    """Return getter(el) for the first element in `elements`, or '' if empty."""
    if not elements:
        return ""
    return getter(elements[0]) or ""


def _extract_tile_data(figure):
    """Given a Selenium <figure> element, return attribution data for that
    result, or None if the figure doesn't look like a DDG image tile.

    Returned dict keys: url, alt, title, source_url, source_domain,
    source_favicon_url, width, height, ddg_proxied_url.
    """
    try:
        img_elements = figure.find_elements(By.CSS_SELECTOR, "img")
    except Exception:
        return None

    # Pick the result image (not the favicon). DDG image results are served
    # through /iu/, favicons through /ip3/.
    result_img = None
    for el in img_elements:
        try:
            src = el.get_attribute("src") or ""
        except Exception:
            continue
        if "external-content.duckduckgo.com/iu/" in src:
            result_img = el
            break
    if result_img is None:
        return None

    try:
        proxied_src = result_img.get_attribute("src") or ""
        alt = result_img.get_attribute("alt") or ""
    except Exception:
        return None

    real_url = _decode_proxied_image_url(proxied_src)
    if not real_url:
        return None

    # Source-page URL: the first <a href> inside the <figcaption>. DDG
    # wraps the article title, favicon and domain name in that one anchor.
    source_url = ""
    page_title = ""
    source_domain = ""
    favicon_url = ""
    try:
        figcaption = figure.find_element(By.CSS_SELECTOR, "figcaption")
    except Exception:
        figcaption = None

    if figcaption is not None:
        # Source page href — the <a> wraps the title h3, but there can be
        # other anchors (menu, share, etc.) after it. The first one is
        # almost always the source page link.
        try:
            anchors = figcaption.find_elements(By.CSS_SELECTOR, "a[href]")
        except Exception:
            anchors = []
        for anchor in anchors:
            try:
                href = anchor.get_attribute("href") or ""
            except Exception:
                continue
            # Skip javascript:/mailto:/empty hrefs; skip DuckDuckGo-internal
            # links. Source-page links go to a real third-party domain.
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue
            if "duckduckgo.com" in href:
                continue
            source_url = _normalize_url(href)
            break

        # Article title: <h3 title="...">...</h3>
        try:
            h3_elements = figcaption.find_elements(By.CSS_SELECTOR, "h3[title]")
            page_title = _first_or_none(h3_elements, lambda e: e.get_attribute("title"))
            if not page_title:
                page_title = _first_or_none(h3_elements, lambda e: e.text)
        except Exception:
            pass

        # Source domain: <p title="rd.com">rd.com</p>
        try:
            domain_ps = figcaption.find_elements(By.CSS_SELECTOR, "p[title]")
            source_domain = _first_or_none(domain_ps, lambda e: e.get_attribute("title"))
            if not source_domain:
                source_domain = _first_or_none(domain_ps, lambda e: e.text)
        except Exception:
            pass

        # Favicon: <img src="...ip3/<domain>.ico">
        try:
            favicon_imgs = figcaption.find_elements(
                By.CSS_SELECTOR, 'img[src*="external-content.duckduckgo.com/ip3/"]'
            )
            favicon_raw = _first_or_none(favicon_imgs, lambda e: e.get_attribute("src"))
            if favicon_raw:
                favicon_url = _normalize_url(favicon_raw)
        except Exception:
            pass

    # Dimensions text sits in a <p> sibling of the image inside the same
    # wrapping <div>. Look anywhere in the figure; class names are obfuscated
    # and unreliable, but the × separator is stable. We use `.` (the string
    # value of the element) rather than `text()` because Selenium's XPath
    # implementation drops hidden elements when filtering by `text()`,
    # returning zero matches for DDG's lazy-rendered dimensions <p>.
    dimensions_text = ""
    try:
        candidates = figure.find_elements(
            By.XPATH, './/p[contains(., "×")]'
        )
    except Exception:
        candidates = []
    for c in candidates:
        try:
            text = (c.text or "").strip()
        except Exception:
            continue
        if DIMENSIONS_RE.search(text):
            dimensions_text = text
            break

    width, height = _parse_dimensions(dimensions_text)

    # If we didn't get a domain from the figcaption (some tiles render it
    # slightly differently), fall back to the favicon URL's hostname.
    if not source_domain and favicon_url:
        source_domain = _decode_proxied_favicon_url(favicon_url)

    # And as a last resort, derive a domain from the source URL.
    if not source_domain and source_url:
        from urllib.parse import urlparse
        try:
            host = urlparse(source_url).hostname or ""
            if host:
                # strip leading "www." for a cleaner display
                source_domain = host[4:] if host.startswith("www.") else host
        except Exception:
            pass

    return {
        "url": real_url,
        "alt": alt.strip(),
        "title": page_title.strip(),
        "source_url": source_url,
        "source_domain": source_domain.strip(),
        "source_favicon_url": favicon_url,
        "width": width,
        "height": height,
        "ddg_proxied_url": _normalize_url(proxied_src),
    }


def _extract_tiles(driver, num_images: int):
    """Walk all <figure> tiles on the page and return attribution dicts,
    deduped by real image URL. Stops early once num_images is reached."""
    images = []
    seen_urls = set()
    try:
        figures = driver.find_elements(By.CSS_SELECTOR, "figure")
    except Exception:
        return images

    for figure in figures:
        if len(images) >= num_images:
            break
        try:
            data = _extract_tile_data(figure)
        except Exception:
            continue
        if not data:
            continue
        if data["url"] in seen_urls:
            continue
        seen_urls.add(data["url"])
        images.append(data)
    return images


def scrape_duckduckgo_images_selenium(query, num_images=5, headless=True):
    """Scrape DuckDuckGo Images with full source attribution.

    Args:
        query (str): Search query for DuckDuckGo Images
        num_images (int): Number of images to retrieve (default: 5)
        headless (bool): Run browser in headless mode (default: True)

    Returns:
        list: List of dicts, each with keys: url, alt, title, source_url,
              source_domain, source_favicon_url, width, height,
              ddg_proxied_url. Empty list on failure.
    """
    try:
        driver = _build_driver(headless)
    except Exception as e:
        print(f"Could not start Chrome: {e}", file=sys.stderr)
        return []

    try:
        encoded_query = quote(query)
        url = f"https://duckduckgo.com/?q={encoded_query}&iar=images"
        print(f"Loading: {url}")
        driver.get(url)

        time.sleep(3)
        try:
            driver.find_element(By.CSS_SELECTOR, "figure")
        except Exception:
            print("Waiting for image tiles to load...")
            time.sleep(3)

        # Scroll to lazy-load more tiles. The top of the page only renders
        # ~10-15 figures; scrolling pulls in the next batch.
        print("Scrolling to load more images...")
        for _ in range(6):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        # And scroll back to the top so attribution elements (which the
        # browser may have lazy-rendered) are fully populated.
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        print("Reading figure tiles...")
        images = _extract_tiles(driver, num_images)
        return images[:num_images]

    except Exception as e:
        print(f"Error during scraping: {e}", file=sys.stderr)
        return []
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    """Command-line entry point. Prints results as JSON."""
    if len(sys.argv) < 2:
        print("Usage: python image_scraper_selenium.py <search_query> [num_images]")
        print("Example: python image_scraper_selenium.py 'cute cats' 5")
        sys.exit(1)

    import json

    query = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"Searching for: {query}")
    print(f"Number of images: {num_images}\n")

    images = scrape_duckduckgo_images_selenium(query, num_images)

    payload = {
        "query": query,
        "source": "duckduckgo",
        "count": len(images),
        "images": images,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
