"""Unit tests for image_scraper_maps.

These tests use unittest.mock to stub out the Selenium WebDriver, so they
run in milliseconds without needing Chrome or network access.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make the project importable when running tests from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from image_scraper_maps import (  # noqa: E402
    GOOGLE_PHOTO_HOST_RE,
    RESULT_SELECTORS,
    IMAGE_SELECTORS,
    scrape_google_maps_images,
    _accept_consent_if_present,
    CONSENT_ACCEPT_PATTERNS,
)


def _img_element(src):
    """Build a fake Selenium <img> WebElement that returns the given src."""
    el = MagicMock()
    el.get_attribute.return_value = src
    return el


def _result_element():
    """Build a fake clickable search-result element."""
    return MagicMock()


def _make_mock_driver(result_elements=None, image_elements=None, all_imgs=None):
    """Build a mock WebDriver whose find_elements responds by CSS selector.

    - Selectors containing "/maps/place/" return the result elements.
    - Selectors containing "googleusercontent" return the image elements.
    - Any other selector returns [].
    - The By.TAG_NAME call returns ``all_imgs`` (used by the fallback path).
    """
    driver = MagicMock()

    def find_elements(by, selector):
        if result_elements is not None and "/maps/place/" in (selector or ""):
            return result_elements
        if image_elements is not None and "googleusercontent" in (selector or ""):
            return image_elements
        return []

    # By.TAG_NAME is the fallback path that walks all <img> tags.
    def find_elements_by_tag(by, selector):
        if by == "tag name" and selector == "img":
            return all_imgs or []
        return find_elements(by, selector)

    driver.find_elements.side_effect = find_elements_by_tag
    return driver


class TestScrapeGoogleMapsImages(unittest.TestCase):
    """Behavioural tests for scrape_google_maps_images."""

    def setUp(self):
        # Patch the parts of the module that would otherwise touch the
        # network, sleep, or require a real browser.
        self._sleep_patcher = patch("image_scraper_maps.time.sleep")
        self._wait_patcher = patch("image_scraper_maps.WebDriverWait")
        self._sleep_patcher.start()
        self._wait_patcher.start()

    def tearDown(self):
        self._sleep_patcher.stop()
        self._wait_patcher.stop()

    # ---- 1. URL construction -------------------------------------------------

    def test_builds_search_url(self):
        driver = _make_mock_driver(result_elements=[], image_elements=[])
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            scrape_google_maps_images("Eiffel Tower", num_images=3)

        self.assertTrue(driver.get.called, "driver.get was never called")
        called_url = driver.get.call_args[0][0]
        self.assertIn("https://www.google.com/maps/search/", called_url)
        # "Eiffel Tower" -> Eiffel%20Tower
        self.assertIn("Eiffel%20Tower", called_url)

    def test_url_encodes_special_characters(self):
        driver = _make_mock_driver()
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            scrape_google_maps_images("Joe's Pizza & Pasta", num_images=1)

        called_url = driver.get.call_args[0][0]
        self.assertIn("Joe%27s%20Pizza%20%26%20Pasta", called_url)

    # ---- 2. Image extraction -------------------------------------------------

    def test_extracts_images_from_googleusercontent_src(self):
        image_elements = [
            _img_element("https://lh3.googleusercontent.com/places/photo1=w800"),
            _img_element("https://lh5.googleusercontent.com/places/photo2=w800"),
        ]
        driver = _make_mock_driver(
            result_elements=[_result_element()],
            image_elements=image_elements,
        )
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Eiffel Tower", num_images=5)

        self.assertEqual(len(result), 2)
        self.assertEqual(
            result[0]["url"], "https://lh3.googleusercontent.com/places/photo1=w800"
        )
        for entry in result:
            self.assertIn("url", entry)
            self.assertIn("alt", entry)
            self.assertIn("title", entry)

    # ---- 3. Dedup ----------------------------------------------------------

    def test_dedupes_duplicate_urls(self):
        image_elements = [
            _img_element("https://lh3.googleusercontent.com/places/same"),
            _img_element("https://lh3.googleusercontent.com/places/same"),
            _img_element("https://lh3.googleusercontent.com/places/same"),
        ]
        driver = _make_mock_driver(
            result_elements=[_result_element()],
            image_elements=image_elements,
        )
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=10)

        self.assertEqual(len(result), 1)

    # ---- 4. num_images cap --------------------------------------------------

    def test_respects_num_images_limit(self):
        image_elements = [
            _img_element(f"https://lh3.googleusercontent.com/places/photo{i}")
            for i in range(10)
        ]
        driver = _make_mock_driver(
            result_elements=[_result_element()],
            image_elements=image_elements,
        )
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=3)

        self.assertEqual(len(result), 3)
        self.assertEqual(
            [r["url"] for r in result],
            [f"https://lh3.googleusercontent.com/places/photo{i}" for i in range(3)],
        )

    # ---- 5. Filtering -------------------------------------------------------

    def test_ignores_non_googleusercontent_srcs(self):
        image_elements = [
            _img_element("https://example.com/photo.jpg"),
            _img_element("https://lh3.googleusercontent.com/places/keep-me"),
            _img_element("https://random-cdn.test/img.png"),
        ]
        driver = _make_mock_driver(
            result_elements=[_result_element()],
            image_elements=image_elements,
        )
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=10)

        urls = [r["url"] for r in result]
        self.assertEqual(urls, ["https://lh3.googleusercontent.com/places/keep-me"])

    def test_uses_fallback_when_no_image_selector_matches(self):
        """If googleusercontent CSS selectors return nothing, the fallback
        walks every <img> tag and keeps the ones whose src is a Google photo
        CDN URL."""
        all_imgs = [
            _img_element("https://example.com/photo.jpg"),
            _img_element("https://lh3.googleusercontent.com/places/fallback-1"),
            _img_element("https://lh4.googleusercontent.com/places/fallback-2"),
        ]
        # No matches via the prioritized selectors; fallback handles it.
        driver = _make_mock_driver(
            result_elements=[],
            image_elements=[],
            all_imgs=all_imgs,
        )
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=5)

        urls = sorted(r["url"] for r in result)
        self.assertEqual(
            urls,
            sorted([
                "https://lh3.googleusercontent.com/places/fallback-1",
                "https://lh4.googleusercontent.com/places/fallback-2",
            ]),
        )

    # ---- 6. Driver error path ----------------------------------------------

    def test_returns_empty_list_on_driver_error(self):
        with patch(
            "image_scraper_maps.webdriver.Chrome",
            side_effect=RuntimeError("chrome not installed"),
        ):
            result = scrape_google_maps_images("Anywhere", num_images=5)

        self.assertEqual(result, [])

    def test_returns_empty_list_on_runtime_error(self):
        """Errors during the scrape itself (after the driver is up) should
        be caught and surfaced as an empty list rather than propagating."""
        driver = MagicMock()
        driver.get.side_effect = RuntimeError("network down")
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Anywhere", num_images=5)

        self.assertEqual(result, [])

    # ---- 7. Cleanup ---------------------------------------------------------

    def test_quits_driver_on_success(self):
        driver = _make_mock_driver(
            result_elements=[_result_element()],
            image_elements=[_img_element("https://lh3.googleusercontent.com/p/1")],
        )
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            scrape_google_maps_images("Place", num_images=1)

        driver.quit.assert_called_once()

    def test_quits_driver_even_when_get_fails(self):
        driver = MagicMock()
        driver.get.side_effect = RuntimeError("boom")
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            scrape_google_maps_images("Place", num_images=1)

        driver.quit.assert_called_once()


class TestConstants(unittest.TestCase):
    """Sanity checks on the module-level constants — cheap regression guards
    if Google rotates class names and we need to update selectors."""

    def test_result_selectors_non_empty(self):
        self.assertGreater(len(RESULT_SELECTORS), 0)
        # At least one selector should target a Maps place link.
        self.assertTrue(any("/maps/place/" in s for s in RESULT_SELECTORS))

    def test_image_selectors_non_empty(self):
        self.assertGreater(len(IMAGE_SELECTORS), 0)
        self.assertTrue(any("googleusercontent" in s for s in IMAGE_SELECTORS))

    def test_google_photo_host_regex_matches_known_cdns(self):
        for url in [
            "https://lh3.googleusercontent.com/places/abc",
            "https://lh4.googleusercontent.com/places/xyz",
            "https://lh5.googleusercontent.com/places/123",
            "https://lh6.googleusercontent.com/places/456",
        ]:
            self.assertIsNotNone(
                GOOGLE_PHOTO_HOST_RE.search(url),
                f"regex should match {url}",
            )

    def test_google_photo_host_regex_rejects_unknown_hosts(self):
        for url in [
            "https://example.com/foo.jpg",
            "https://lh99.googleusercontent.com/x",  # not in lh3..lh6
            "https://maps.googleapis.com/photo",  # not a googleusercontent host
        ]:
            self.assertIsNone(
                GOOGLE_PHOTO_HOST_RE.search(url),
                f"regex should not match {url}",
            )


class TestAcceptConsent(unittest.TestCase):
    """Tests for the Google consent-page handler."""

    def _make_consent_driver(self, button_labels):
        """Build a mock driver that simulates consent.google.com with the
        given list of (aria_label, text) tuples — one button per tuple."""
        driver = MagicMock()
        driver.current_url = "https://consent.google.com/m?continue=..."

        buttons = []
        for aria_label, text in button_labels:
            btn = MagicMock()
            btn.get_attribute.return_value = aria_label
            btn.text = text
            buttons.append(btn)

        def find_elements(by, selector):
            if "consent.google.com/save" in (selector or ""):
                return buttons
            return []

        driver.find_elements.side_effect = find_elements
        return driver, buttons

    def test_noop_when_not_on_consent_page(self):
        driver = MagicMock()
        driver.current_url = "https://www.google.com/maps/search/x/"
        self.assertFalse(_accept_consent_if_present(driver))
        driver.find_elements.assert_not_called()

    def test_clicks_accept_button_portuguese(self):
        driver, buttons = self._make_consent_driver(
            [("Rejeitar tudo", ""), ("Aceitar tudo", "")]
        )
        self.assertTrue(_accept_consent_if_present(driver))
        # The "Aceitar tudo" button (index 1) should be the one clicked.
        buttons[1].click.assert_called_once()
        buttons[0].click.assert_not_called()

    def test_clicks_accept_button_english(self):
        driver, buttons = self._make_consent_driver(
            [("Reject all", ""), ("Accept all", "")]
        )
        self.assertTrue(_accept_consent_if_present(driver))
        buttons[1].click.assert_called_once()

    def test_returns_false_when_no_matching_button(self):
        driver, buttons = self._make_consent_driver(
            [("Idioma: Português", ""), ("Rejeitar tudo", "")]
        )
        # "Rejeitar tudo" contains "tudo" not "aceitar"; no accept phrase.
        self.assertFalse(_accept_consent_if_present(driver))
        for b in buttons:
            b.click.assert_not_called()

    def test_returns_false_when_no_buttons_present(self):
        driver, _ = self._make_consent_driver([])
        self.assertFalse(_accept_consent_if_present(driver))

    def test_returns_false_on_find_elements_exception(self):
        driver = MagicMock()
        driver.current_url = "https://consent.google.com/m?..."
        driver.find_elements.side_effect = RuntimeError("boom")
        self.assertFalse(_accept_consent_if_present(driver))

    def test_returns_false_when_click_raises(self):
        driver, buttons = self._make_consent_driver(
            [("Accept all", "")]
        )
        buttons[0].click.side_effect = RuntimeError("not clickable")
        self.assertFalse(_accept_consent_if_present(driver))

    def test_accept_patterns_cover_multiple_locales(self):
        # Smoke test: the patterns list should at least cover English,
        # Portuguese, Spanish, German, French, Italian.
        labels = [
            "Accept all", "Aceitar tudo", "Aceptar todo",
            "Alle akzeptieren", "Tout accepter", "Accetta tutto",
        ]
        for label in labels:
            label_lower = label.lower()
            self.assertTrue(
                any(p in label_lower for p in CONSENT_ACCEPT_PATTERNS),
                f"No consent pattern matches {label!r}",
            )


if __name__ == "__main__":
    unittest.main()
