"""Unit tests for image_scraper_maps.

These tests use unittest.mock to stub out the Selenium WebDriver, so they
run in milliseconds without needing Chrome or network access.
"""

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make the project importable when running tests from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import image_scraper_mcp_server  # noqa: E402
from image_scraper_maps import (  # noqa: E402
    AUTHOR_BUTTON_SELECTOR,
    AUTHOR_LABEL_RE,
    AVATAR_SIZE_RE,
    BACKGROUND_IMAGE_RE,
    GOOGLE_PHOTO_HOST_RE,
    RESULT_SELECTORS,
    _accept_consent_if_present,
    _extract_background_image_url,
    _extract_fallback_photos,
    _extract_review_photos,
    _parse_author_from_aria_label,
    scrape_google_maps_images,
    CONSENT_ACCEPT_PATTERNS,
)


def _img_element(src):
    """Build a fake Selenium <img> WebElement that returns the given src."""
    el = MagicMock()
    el.get_attribute.return_value = src
    return el


def _review_button(aria_label, background_url=None, profile_url=""):
    """Build a fake review-photo button WebElement.

    - `background_url`: when set, the button's style will contain
      `background-image: url('<url>')` so the AUTHOR_BUTTON_SELECTOR
      (`button[style*="background-image"]`) matches it.
    - `profile_url`: when set, the button's find_elements(By.XPATH, ...)
      returns a fake link element whose href is this URL. This simulates
      Google's review layout where the contributor link is a sibling of the
      photo button.
    """
    el = MagicMock()

    def get_attribute(name):
        if name == "aria-label":
            return aria_label
        if name == "style":
            if background_url is None:
                return ""
            return f"background-image: url('{background_url}');"
        if name == "href":
            return profile_url
        return None

    el.get_attribute.side_effect = get_attribute

    if profile_url:
        # Make btn.find_elements(By.XPATH, ...) return a fake <a> with the
        # profile href. Used by _find_associated_contrib_link.
        fake_link = MagicMock()
        fake_link.get_attribute.return_value = profile_url
        el.find_elements.return_value = [fake_link]
    else:
        el.find_elements.return_value = []

    return el


def _result_element():
    """Build a fake clickable search-result element."""
    return MagicMock()


def _make_mock_driver(review_buttons=None, fallback_imgs=None):
    """Build a mock WebDriver.

    - AUTHOR_BUTTON_SELECTOR (`button[style*="background-image"]`) returns
      review_buttons.
    - img[src*="googleusercontent"] returns fallback_imgs.
    - Anything else returns [].
    """
    driver = MagicMock()

    def find_elements(by, selector):
        if AUTHOR_BUTTON_SELECTOR in (selector or ""):
            return review_buttons or []
        if "googleusercontent" in (selector or ""):
            return fallback_imgs or []
        return []

    driver.find_elements.side_effect = find_elements
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

    # ---- URL construction --------------------------------------------------

    def test_builds_search_url(self):
        driver = _make_mock_driver()
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

    # ---- Review photo extraction ------------------------------------------

    def test_extracts_attributed_photos(self):
        buttons = [
            _review_button(
                "Foto 1 na crítica de Mary van Lutsenburg Maas",
                background_url="https://lh3.googleusercontent.com/grass-cs/photo1=w600",
                profile_url="https://www.google.com/maps/contrib/111/reviews",
            ),
            _review_button(
                "Foto 1 na crítica de Halina Lotyczewski",
                background_url="https://lh3.googleusercontent.com/grass-cs/photo2=w600",
                profile_url="https://www.google.com/maps/contrib/222/reviews",
            ),
        ]
        driver = _make_mock_driver(review_buttons=buttons)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=5)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["author"], "Mary van Lutsenburg Maas")
        self.assertEqual(result[0]["url"], "https://lh3.googleusercontent.com/grass-cs/photo1=w600")
        self.assertEqual(
            result[0]["author_profile_url"],
            "https://www.google.com/maps/contrib/111/reviews",
        )

    def test_skips_buttons_without_author_label(self):
        """Buttons that don't match an author pattern (e.g. nav arrows) are
        ignored."""
        buttons = [
            _review_button("Foto seguinte"),  # "Next photo" — not an author
            _review_button(
                "Foto 1 na crítica de Real Author",
                background_url="https://lh3.googleusercontent.com/grass-cs/real=w600",
            ),
        ]
        driver = _make_mock_driver(review_buttons=buttons)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["author"], "Real Author")

    def test_dedupes_duplicate_review_photos(self):
        buttons = [
            _review_button(
                "Foto 1 na crítica de Same Author",
                background_url="https://lh3.googleusercontent.com/grass-cs/same=w600",
            ),
            _review_button(
                "Foto 2 na crítica de Same Author",
                background_url="https://lh3.googleusercontent.com/grass-cs/same=w600",
            ),
        ]
        driver = _make_mock_driver(review_buttons=buttons)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=5)

        self.assertEqual(len(result), 1)

    def test_respects_num_images_limit(self):
        buttons = [
            _review_button(
                f"Foto {i} na crítica de Author {i}",
                background_url=f"https://lh3.googleusercontent.com/grass-cs/photo{i}=w600",
            )
            for i in range(1, 6)
        ]
        driver = _make_mock_driver(review_buttons=buttons)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=3)

        self.assertEqual(len(result), 3)
        self.assertEqual([r["author"] for r in result], ["Author 1", "Author 2", "Author 3"])

    def test_require_attribution_false_falls_back_to_unattributed(self):
        """When require_attribution is False, fill remaining slots with
        unattributed photos from the place panel."""
        review = _review_button(
            "Foto 1 na crítica de Author",
            background_url="https://lh3.googleusercontent.com/grass-cs/r=w600",
        )
        fallback = [
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/fallback1=w800"),
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/fallback2=w800"),
        ]
        driver = _make_mock_driver(review_buttons=[review], fallback_imgs=fallback)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images(
                "Place", num_images=3, require_attribution=False
            )

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["author"], "Author")
        self.assertEqual(result[1]["author"], "")
        self.assertEqual(result[2]["author"], "")

    def test_require_attribution_true_does_not_use_fallback(self):
        """When require_attribution is True, do not fill from unattributed
        photos even if there are fewer attributed photos than requested."""
        review = _review_button(
            "Foto 1 na crítica de Author",
            background_url="https://lh3.googleusercontent.com/grass-cs/r=w600",
        )
        fallback = [
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/fallback1=w800"),
        ]
        driver = _make_mock_driver(review_buttons=[review], fallback_imgs=fallback)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images(
                "Place", num_images=3, require_attribution=True
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["author"], "Author")

    def test_default_falls_back_when_no_attributed_photos(self):
        """Default behavior (require_attribution=False) prefers attributed
        photos but falls back to official photos when none are available."""
        fallback = [
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/official1=w800"),
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/official2=w800"),
        ]
        driver = _make_mock_driver(review_buttons=[], fallback_imgs=fallback)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            # No require_attribution kwarg — should use new default
            result = scrape_google_maps_images("Place", num_images=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["author"], "")
        self.assertEqual(result[1]["author"], "")
        self.assertIn("official1", result[0]["url"])
        self.assertIn("official2", result[1]["url"])

    def test_default_prefers_attributed_over_official(self):
        """Default behavior returns attributed photos first, then fills
        remaining slots with official ones."""
        review = _review_button(
            "Foto 1 na crítica de Real Person",
            background_url="https://lh3.googleusercontent.com/grass-cs/r=w600",
        )
        fallback = [
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/official=w800"),
        ]
        driver = _make_mock_driver(review_buttons=[review], fallback_imgs=fallback)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Place", num_images=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["author"], "Real Person")
        self.assertEqual(result[1]["author"], "")
        self.assertIn("official", result[1]["url"])

    def test_excludes_reviewer_avatars_from_fallback(self):
        fallback = [
            # Avatar (round-profile size hint) — should be filtered out
            _img_element("https://lh3.googleusercontent.com/a-/photo=w36-h36-p-rp-mo-br100"),
            # Real place photo — should be kept
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/real=w800-h600"),
        ]
        driver = _make_mock_driver(review_buttons=[], fallback_imgs=fallback)
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images(
                "Place", num_images=5, require_attribution=False
            )

        self.assertEqual(len(result), 1)
        self.assertIn("gps-cs-s", result[0]["url"])

    # ---- Error path --------------------------------------------------------

    def test_returns_empty_list_on_driver_error(self):
        with patch(
            "image_scraper_maps.webdriver.Chrome",
            side_effect=RuntimeError("chrome not installed"),
        ):
            result = scrape_google_maps_images("Anywhere", num_images=5)

        self.assertEqual(result, [])

    def test_returns_empty_list_on_runtime_error(self):
        driver = MagicMock()
        driver.get.side_effect = RuntimeError("network down")
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            result = scrape_google_maps_images("Anywhere", num_images=5)

        self.assertEqual(result, [])

    # ---- Cleanup -----------------------------------------------------------

    def test_quits_driver_on_success(self):
        review = _review_button(
            "Foto 1 na crítica de Author",
            background_url="https://lh3.googleusercontent.com/grass-cs/x=w600",
        )
        driver = _make_mock_driver(review_buttons=[review])
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            scrape_google_maps_images("Place", num_images=1)

        driver.quit.assert_called_once()

    def test_quits_driver_even_when_get_fails(self):
        driver = MagicMock()
        driver.get.side_effect = RuntimeError("boom")
        with patch("image_scraper_maps.webdriver.Chrome", return_value=driver):
            scrape_google_maps_images("Place", num_images=1)

        driver.quit.assert_called_once()


class TestParseAuthorFromAriaLabel(unittest.TestCase):
    """Tests for the aria-label parser."""

    def test_parses_pt_aria_label(self):
        self.assertEqual(
            _parse_author_from_aria_label("Foto 1 na crítica de Mary van Lutsenburg Maas"),
            "Mary van Lutsenburg Maas",
        )

    def test_parses_en_aria_label(self):
        self.assertEqual(
            _parse_author_from_aria_label("Photo 2 in the review by John Doe"),
            "John Doe",
        )

    def test_parses_es_aria_label(self):
        self.assertEqual(
            _parse_author_from_aria_label("Foto 3 en la reseña de Carlos García"),
            "Carlos García",
        )

    def test_parses_fr_aria_label(self):
        self.assertEqual(
            _parse_author_from_aria_label("Photo 1 dans la critique par Marie Dupont"),
            "Marie Dupont",
        )

    def test_rejects_non_author_label(self):
        # Navigation arrows and other UI labels should not match.
        for label in [
            "Foto seguinte",  # PT: "Next photo"
            "Next photo",
            "Photo suivante",
            "Close",
            "",
        ]:
            self.assertIsNone(
                _parse_author_from_aria_label(label),
                f"Should reject: {label!r}",
            )

    def test_rejects_none(self):
        self.assertIsNone(_parse_author_from_aria_label(None))

    def test_preserves_name_with_spaces(self):
        # Names can have multiple words and accents.
        self.assertEqual(
            _parse_author_from_aria_label("Foto 1 na crítica de João da Silva Júnior"),
            "João da Silva Júnior",
        )


class TestExtractBackgroundImageUrl(unittest.TestCase):
    """Tests for parsing the URL out of inline background-image styles."""

    def test_extracts_single_quoted_url(self):
        btn = _review_button("ignored", background_url=None)
        btn.get_attribute.side_effect = lambda name: (
            "background-image: url('https://lh3.googleusercontent.com/x=w600');"
            if name == "style" else None
        )
        self.assertEqual(
            _extract_background_image_url(btn),
            "https://lh3.googleusercontent.com/x=w600",
        )

    def test_extracts_double_quoted_url(self):
        btn = _review_button("ignored", background_url=None)
        btn.get_attribute.side_effect = lambda name: (
            'background-image: url("https://lh3.googleusercontent.com/x=w600");'
            if name == "style" else None
        )
        self.assertEqual(
            _extract_background_image_url(btn),
            "https://lh3.googleusercontent.com/x=w600",
        )

    def test_extracts_unquoted_url(self):
        btn = _review_button("ignored", background_url=None)
        btn.get_attribute.side_effect = lambda name: (
            "background-image: url(https://lh3.googleusercontent.com/x=w600);"
            if name == "style" else None
        )
        self.assertEqual(
            _extract_background_image_url(btn),
            "https://lh3.googleusercontent.com/x=w600",
        )

    def test_returns_none_when_no_url(self):
        btn = _review_button("ignored", background_url=None)
        btn.get_attribute.side_effect = lambda name: "" if name == "style" else None
        self.assertIsNone(_extract_background_image_url(btn))


class TestExtractReviewPhotos(unittest.TestCase):
    """Direct tests for _extract_review_photos (no full scrape)."""

    def test_returns_dict_with_all_fields(self):
        btn = _review_button(
            "Foto 1 na crítica de Mary van Lutsenburg Maas",
            background_url="https://lh3.googleusercontent.com/grass-cs/photo=w600",
            profile_url="https://www.google.com/maps/contrib/111/reviews",
        )
        driver = MagicMock()
        driver.find_elements.return_value = [btn]
        result = _extract_review_photos(driver, num_images=5)
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["author"], "Mary van Lutsenburg Maas")
        self.assertEqual(entry["url"], "https://lh3.googleusercontent.com/grass-cs/photo=w600")
        self.assertEqual(
            entry["author_profile_url"],
            "https://www.google.com/maps/contrib/111/reviews",
        )

    def test_skips_buttons_without_background_image(self):
        # A button that matches the aria-label selector but has no inline style.
        btn = _review_button("Foto 1 na crítica de Author", background_url=None)
        driver = MagicMock()
        driver.find_elements.return_value = [btn]
        result = _extract_review_photos(driver, num_images=5)
        self.assertEqual(result, [])


class TestExtractFallbackPhotos(unittest.TestCase):
    """Direct tests for _extract_fallback_photos."""

    def test_filters_to_googleusercontent_only(self):
        imgs = [
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/keep=w800"),
            _img_element("https://example.com/foo.jpg"),
        ]
        driver = MagicMock()
        driver.find_elements.return_value = imgs
        result = _extract_fallback_photos(driver, num_images=5)
        self.assertEqual(len(result), 1)
        self.assertIn("gps-cs-s", result[0]["url"])

    def test_excludes_avatar_size_hints(self):
        imgs = [
            _img_element("https://lh3.googleusercontent.com/a-/photo=w36-h36-p-rp-mo-br100"),
            _img_element("https://lh3.googleusercontent.com/gps-cs-s/real=w800"),
        ]
        driver = MagicMock()
        driver.find_elements.return_value = imgs
        result = _extract_fallback_photos(driver, num_images=5)
        self.assertEqual(len(result), 1)
        self.assertIn("gps-cs-s", result[0]["url"])

    def test_returns_empty_when_find_elements_raises(self):
        driver = MagicMock()
        driver.find_elements.side_effect = RuntimeError("boom")
        self.assertEqual(_extract_fallback_photos(driver, num_images=5), [])


class TestConstants(unittest.TestCase):
    """Sanity checks on the module-level constants — cheap regression guards
    if Google rotates class names and we need to update selectors."""

    def test_result_selectors_non_empty(self):
        self.assertGreater(len(RESULT_SELECTORS), 0)
        self.assertTrue(any("/maps/place/" in s for s in RESULT_SELECTORS))

    def test_author_button_selector_targets_photo_buttons(self):
        # The selector narrows on the structural signal: review photos are
        # served via inline background-image (not <img>), so the selector
        # matches the photo button and excludes unrelated UI buttons that
        # happen to contain "review"/"crítica" in their aria-label.
        self.assertIn("button", AUTHOR_BUTTON_SELECTOR)
        self.assertIn("background-image", AUTHOR_BUTTON_SELECTOR)

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
            "https://lh99.googleusercontent.com/x",
            "https://maps.googleapis.com/photo",
        ]:
            self.assertIsNone(
                GOOGLE_PHOTO_HOST_RE.search(url),
                f"regex should not match {url}",
            )

    def test_avatar_size_regex_matches_avatar_patterns(self):
        for url in [
            "https://lh3.googleusercontent.com/a-/photo=w36-h36-p-rp-mo-br100",
            "https://lh3.googleusercontent.com/a/abc=w80-h80-p-rp",
        ]:
            self.assertIsNotNone(
                AVATAR_SIZE_RE.search(url),
                f"avatar regex should match {url}",
            )

    def test_avatar_size_regex_skips_normal_photos(self):
        for url in [
            "https://lh3.googleusercontent.com/gps-cs-s/photo=w408-h306-k-no",
            "https://lh3.googleusercontent.com/grass-cs/photo=w600-h450-p-k-no",
        ]:
            self.assertIsNone(
                AVATAR_SIZE_RE.search(url),
                f"avatar regex should not match {url}",
            )


class TestAcceptConsent(unittest.TestCase):
    """Tests for the Google consent-page handler."""

    def _make_consent_driver(self, button_labels):
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
        driver, buttons = self._make_consent_driver([("Accept all", "")])
        buttons[0].click.side_effect = RuntimeError("not clickable")
        self.assertFalse(_accept_consent_if_present(driver))

    def test_accept_patterns_cover_multiple_locales(self):
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


class TestMcpServer(unittest.TestCase):
    """Tests for the MCP server's tool dispatch."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_search_maps_images_returns_json(self):
        fake_images = [
            {
                "url": "https://lh3.googleusercontent.com/photo1=w600",
                "author": "Mary",
                "author_profile_url": "https://www.google.com/maps/contrib/111",
            },
            {
                "url": "https://lh3.googleusercontent.com/photo2=w600",
                "author": "John",
                "author_profile_url": "",
            },
        ]
        with patch(
            "image_scraper_mcp_server.scrape_google_maps_images",
            return_value=fake_images,
        ):
            result = self._run(
                image_scraper_mcp_server.call_tool(
                    "search_maps_images",
                    {"query": "Joe's Pizza NYC", "num_images": 2},
                )
            )

        self.assertEqual(len(result), 1)
        payload = json.loads(result[0].text)
        self.assertEqual(payload["query"], "Joe's Pizza NYC")
        self.assertEqual(payload["source"], "google_maps")
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["images"][0]["author"], "Mary")
        self.assertEqual(
            payload["images"][0]["author_profile_url"],
            "https://www.google.com/maps/contrib/111",
        )
        self.assertEqual(payload["images"][1]["author"], "John")

    def test_search_maps_images_json_when_empty(self):
        with patch(
            "image_scraper_mcp_server.scrape_google_maps_images",
            return_value=[],
        ):
            result = self._run(
                image_scraper_mcp_server.call_tool(
                    "search_maps_images",
                    {"query": "Nowhere", "num_images": 5},
                )
            )
        payload = json.loads(result[0].text)
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["images"], [])

    def test_search_images_returns_text_not_json(self):
        """Regression: changing search_maps_images to JSON must not affect
        search_images's text-formatted output."""
        fake = [{"url": "https://example.com/x.jpg", "alt": "alt-x", "title": ""}]
        with patch(
            "image_scraper_mcp_server.scrape_duckduckgo_images_selenium",
            return_value=fake,
        ):
            result = self._run(
                image_scraper_mcp_server.call_tool(
                    "search_images",
                    {"query": "cats", "num_images": 1},
                )
            )
        # Should NOT be valid JSON; should be human-readable text.
        text = result[0].text
        self.assertIn("Found 1 images", text)
        self.assertIn("https://example.com/x.jpg", text)
        # Sanity: it should not start with `{` (which would indicate JSON).
        self.assertFalse(text.lstrip().startswith("{"))

    def test_unknown_tool_raises(self):
        with self.assertRaises(ValueError):
            self._run(
                image_scraper_mcp_server.call_tool(
                    "bogus_tool", {"query": "x", "num_images": 1}
                )
            )

    def test_missing_query_raises(self):
        with self.assertRaises(ValueError):
            self._run(
                image_scraper_mcp_server.call_tool(
                    "search_maps_images", {"num_images": 1}
                )
            )


if __name__ == "__main__":
    unittest.main()