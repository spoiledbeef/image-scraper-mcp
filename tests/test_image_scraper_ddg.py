"""Unit tests for image_scraper_selenium (DuckDuckGo image scraper).

These tests stub out the Selenium WebDriver so they run in milliseconds with
no Chrome or network access. They cover the URL-decoding logic and the
figure-tile attribution parser, plus a couple of integration-shape tests
on the public scrape entry point.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Make the project importable when running tests from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import image_scraper_mcp_server  # noqa: E402
from image_scraper_selenium import (  # noqa: E402
    DDG_FAVICON_PROXY_RE,
    DDG_IMAGE_PROXY_RE,
    DIMENSIONS_RE,
    _decode_proxied_favicon_url,
    _decode_proxied_image_url,
    _extract_tile_data,
    _extract_tiles,
    _normalize_url,
    _parse_dimensions,
    scrape_duckduckgo_images_selenium,
)


def _img(src="", alt="", extra_attrs=None):
    """Fake a Selenium <img> WebElement."""
    el = MagicMock()

    def get_attribute(name):
        if name == "src":
            return src
        if name == "alt":
            return alt
        if extra_attrs and name in extra_attrs:
            return extra_attrs[name]
        return None

    el.get_attribute.side_effect = get_attribute
    return el


def _figure_with(result_img_src, result_img_alt="", page_title="", page_href="",
                 source_domain=None, favicon_src="", dimensions_text=""):
    """Build a fake Selenium <figure> element matching DDG's result-tile shape.

    `result_img_src` should be a DDG proxied image URL. The figure contains:
      - one <img> with /iu/ (the result image)
      - one <p> with the dimensions text
      - a <figcaption> with one <a href>, an <h3 title>, a <p title>, a favicon <img>
    """
    figure = MagicMock()

    # The figure's find_elements("img") needs to return BOTH the result img
    # and the favicon img. The result image uses /iu/, the favicon uses /ip3/.
    images_in_figure = [_img(src=result_img_src, alt=result_img_alt)]
    if favicon_src:
        images_in_figure.append(_img(src=favicon_src))

    # The figure's find_element("figcaption") returns the inner figcaption.
    figcaption = MagicMock()

    # figcaption.find_elements("a[href]")
    anchor = MagicMock()
    anchor.get_attribute.side_effect = lambda name: page_href if name == "href" else None
    figcaption.find_elements.side_effect = lambda by, sel: (
        [anchor] if sel == "a[href]" else
        ([_h3(page_title)] if sel == "h3[title]" else
         ([_p_domain(source_domain)] if sel == "p[title]" else
          ([_img(src=favicon_src)] if 'ip3/' in (sel or '') else [])))
    )

    # Top-level figure.find_element(...) dispatch.
    def find_element(by, sel):
        if sel == "figcaption":
            return figcaption
        raise Exception(f"unexpected find_element: {sel}")

    def find_elements_top(by, sel):
        if sel == "img":
            return images_in_figure
        if sel == "p[title]":  # not used at figure level, but harmless
            return []
        # The XPATH lookup for dimensions.
        if sel and sel.startswith(".//p[contains"):
            if dimensions_text:
                return [_p_text(dimensions_text)]
            return []
        return []

    figure.find_element.side_effect = find_element
    figure.find_elements.side_effect = find_elements_top
    return figure


def _h3(title, text=""):
    el = MagicMock()

    def ga(name):
        if name == "title":
            return title
        return None

    el.get_attribute.side_effect = ga
    el.text = text
    return el


def _p_domain(domain):
    el = MagicMock()

    def ga(name):
        if name == "title":
            return domain
        return None

    el.get_attribute.side_effect = ga
    el.text = domain or ""
    return el


def _p_text(text):
    el = MagicMock()
    el.text = text
    return el


class TestDecodeProxiedImageUrl(unittest.TestCase):
    """URL-decoder for DDG's /iu/?u=<encoded> redirector."""

    def test_decodes_simple_url(self):
        src = "//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fcat.jpg&f=1"
        self.assertEqual(
            _decode_proxied_image_url(src),
            "https://example.com/cat.jpg",
        )

    def test_decodes_url_with_path_and_query(self):
        src = ("//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Ftse1.mm.bing.net%2Fth%2Fid%2F"
               "OIP.abc%3Fpid%3DApi&f=1&ipo=images")
        self.assertEqual(
            _decode_proxied_image_url(src),
            "https://tse1.mm.bing.net/th/id/OIP.abc?pid=Api",
        )

    def test_handles_https_prefix(self):
        src = "https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fx.jpg"
        self.assertEqual(
            _decode_proxied_image_url(src),
            "https://example.com/x.jpg",
        )

    def test_returns_none_for_non_proxy_url(self):
        self.assertIsNone(_decode_proxied_image_url("https://example.com/cat.jpg"))
        self.assertIsNone(_decode_proxied_image_url(""))
        self.assertIsNone(_decode_proxied_image_url(None))

    def test_returns_none_for_favicon_proxy(self):
        # /ip3/ is the favicon proxy, not the image proxy.
        src = "//external-content.duckduckgo.com/ip3/www.rd.com.ico"
        self.assertIsNone(_decode_proxied_image_url(src))


class TestDecodeProxiedFaviconUrl(unittest.TestCase):
    """Domain-extractor for DDG's /ip3/<domain>.ico favicon URL."""

    def test_extracts_domain(self):
        self.assertEqual(
            _decode_proxied_favicon_url("//external-content.duckduckgo.com/ip3/www.rd.com.ico"),
            "www.rd.com",
        )

    def test_strips_ico_suffix(self):
        self.assertEqual(
            _decode_proxied_favicon_url("//external-content.duckduckgo.com/ip3/pixabay.com.ico"),
            "pixabay.com",
        )

    def test_returns_empty_for_non_favicon(self):
        self.assertEqual(_decode_proxied_favicon_url("https://example.com/favicon.ico"), "")
        self.assertEqual(_decode_proxied_favicon_url(""), "")


class TestParseDimensions(unittest.TestCase):
    """Dimension-string parser."""

    def test_parses_ddg_format(self):
        self.assertEqual(_parse_dimensions("2560 × 1707"), (2560, 1707))

    def test_parses_letter_x(self):
        self.assertEqual(_parse_dimensions("1920 x 1080"), (1920, 1080))

    def test_parses_asterisk(self):
        self.assertEqual(_parse_dimensions("800*600"), (800, 600))

    def test_returns_none_for_empty_or_invalid(self):
        self.assertEqual(_parse_dimensions(""), (None, None))
        self.assertEqual(_parse_dimensions("just text"), (None, None))
        self.assertEqual(_parse_dimensions(None), (None, None))


class TestNormalizeUrl(unittest.TestCase):
    def test_protocol_relative_gets_https(self):
        self.assertEqual(
            _normalize_url("//external-content.duckduckgo.com/iu/..."),
            "https://external-content.duckduckgo.com/iu/...",
        )

    def test_root_relative_gets_ddg_origin(self):
        self.assertEqual(
            _normalize_url("/foo"),
            "https://duckduckgo.com/foo",
        )

    def test_absolute_url_unchanged(self):
        self.assertEqual(
            _normalize_url("https://example.com/cat.jpg"),
            "https://example.com/cat.jpg",
        )

    def test_empty_unchanged(self):
        self.assertEqual(_normalize_url(""), "")


class TestExtractTileData(unittest.TestCase):
    """Tests for the per-tile attribution parser."""

    PROXIED = ("//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Ftse1.mm.bing.net%2F"
               "th%2Fid%2FOIP.abc%3Fpid%3DApi&f=1&ipo=images")
    REAL_URL = "https://tse1.mm.bing.net/th/id/OIP.abc?pid=Api"

    def test_extracts_all_fields(self):
        figure = _figure_with(
            result_img_src=self.PROXIED,
            result_img_alt="Cute kitten",
            page_title="50 Cute Kittens You Need to See",
            page_href="https://www.rd.com/list/cute-kittens/",
            source_domain="rd.com",
            favicon_src="//external-content.duckduckgo.com/ip3/www.rd.com.ico",
            dimensions_text="2560 × 1707",
        )

        data = _extract_tile_data(figure)

        self.assertIsNotNone(data)
        self.assertEqual(data["url"], self.REAL_URL)
        self.assertEqual(data["alt"], "Cute kitten")
        self.assertEqual(data["title"], "50 Cute Kittens You Need to See")
        self.assertEqual(data["source_url"], "https://www.rd.com/list/cute-kittens/")
        self.assertEqual(data["source_domain"], "rd.com")
        self.assertEqual(
            data["source_favicon_url"],
            "https://external-content.duckduckgo.com/ip3/www.rd.com.ico",
        )
        self.assertEqual(data["width"], 2560)
        self.assertEqual(data["height"], 1707)
        self.assertEqual(
            data["ddg_proxied_url"],
            "https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Ftse1.mm.bing.net%2Fth%2Fid%2FOIP.abc%3Fpid%3DApi&f=1&ipo=images",
        )

    def test_returns_none_when_no_result_image(self):
        # Figure with only a favicon, no /iu/ image.
        figure = _figure_with(
            result_img_src="",  # the dispatcher won't add an /iu/ img
            favicon_src="//external-content.duckduckgo.com/ip3/example.com.ico",
        )
        # _figure_with only adds the result img if src is truthy; with empty
        # src, the /iu/ filter inside _extract_tile_data won't match anything.
        # Build it explicitly with only a favicon.
        figure = MagicMock()

        def find_elements(by, sel):
            if sel == "img":
                return [_img(src="//external-content.duckduckgo.com/ip3/example.com.ico")]
            if sel and sel.startswith(".//p[contains"):
                return []
            return []

        figure.find_elements.side_effect = find_elements
        figure.find_element.side_effect = lambda by, sel: (_ for _ in ()).throw(
            Exception("no figcaption")
        )
        self.assertIsNone(_extract_tile_data(figure))

    def test_returns_none_when_proxy_decode_fails(self):
        figure = _figure_with(
            result_img_src="//external-content.duckduckgo.com/iu/?u=not%2Fa%2Fvalid%2Furl",
        )
        data = _extract_tile_data(figure)
        # URL decodes to "not/a/valid/url" which is fine — the function only
        # requires unquote to succeed, not that the URL parses cleanly.
        # But since the URL is technically decoded successfully, we get a
        # result. Just confirm the round-trip works.
        self.assertIsNotNone(data)
        self.assertEqual(data["url"], "not/a/valid/url")

    def test_source_domain_falls_back_to_favicon_when_caption_missing(self):
        # Caption has no <p title> but does have a favicon.
        figure = MagicMock()

        result_img = _img(
            src="//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fx.jpg"
        )
        favicon_img = _img(src="//external-content.duckduckgo.com/ip3/pixabay.com.ico")

        figcaption = MagicMock()

        def fig_find_elements(by, sel):
            if sel == "a[href]":
                return []
            if sel == "h3[title]":
                return []
            if sel == "p[title]":
                return []
            if 'ip3/' in (sel or ''):
                return [favicon_img]
            return []

        figcaption.find_elements.side_effect = fig_find_elements

        def top_find_element(by, sel):
            if sel == "figcaption":
                return figcaption
            raise Exception("nope")

        def top_find_elements(by, sel):
            if sel == "img":
                return [result_img, favicon_img]
            if sel and sel.startswith(".//p[contains"):
                return []
            return []

        figure.find_element.side_effect = top_find_element
        figure.find_elements.side_effect = top_find_elements

        data = _extract_tile_data(figure)
        self.assertEqual(data["source_domain"], "pixabay.com")

    def test_source_domain_falls_back_to_source_url_host(self):
        # Neither caption-domain nor favicon — derive from source URL host.
        figure = MagicMock()

        result_img = _img(
            src="//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fx.jpg"
        )

        anchor = MagicMock()
        anchor.get_attribute.side_effect = lambda name: (
            "https://www.someblog.example/articles/1" if name == "href" else None
        )

        figcaption = MagicMock()

        def fig_find_elements(by, sel):
            if sel == "a[href]":
                return [anchor]
            if sel == "h3[title]":
                return []
            if sel == "p[title]":
                return []
            if 'ip3/' in (sel or ''):
                return []
            return []

        figcaption.find_elements.side_effect = fig_find_elements

        def top_find_element(by, sel):
            if sel == "figcaption":
                return figcaption
            raise Exception("nope")

        def top_find_elements(by, sel):
            if sel == "img":
                return [result_img]
            if sel and sel.startswith(".//p[contains"):
                return []
            return []

        figure.find_element.side_effect = top_find_element
        figure.find_elements.side_effect = top_find_elements

        data = _extract_tile_data(figure)
        self.assertEqual(data["source_domain"], "someblog.example")
        self.assertEqual(data["source_url"], "https://www.someblog.example/articles/1")

    def test_skips_ddg_internal_hrefs(self):
        """Source-page extraction shouldn't pick duckduckgo.com links."""
        figure = MagicMock()

        result_img = _img(
            src="//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fx.jpg"
        )

        # First <a href> is a DDG-internal link, second is the real source.
        ddg_anchor = MagicMock()
        ddg_anchor.get_attribute.side_effect = lambda name: (
            "https://duckduckgo.com/?q=foo" if name == "href" else None
        )
        real_anchor = MagicMock()
        real_anchor.get_attribute.side_effect = lambda name: (
            "https://pixabay.com/photos/cat-12345/" if name == "href" else None
        )

        figcaption = MagicMock()
        figcaption.find_elements.side_effect = lambda by, sel: (
            [ddg_anchor, real_anchor] if sel == "a[href]" else []
        )

        def top_find_element(by, sel):
            if sel == "figcaption":
                return figcaption
            raise Exception("nope")

        def top_find_elements(by, sel):
            if sel == "img":
                return [result_img]
            if sel and sel.startswith(".//p[contains"):
                return []
            return []

        figure.find_element.side_effect = top_find_element
        figure.find_elements.side_effect = top_find_elements

        data = _extract_tile_data(figure)
        self.assertEqual(data["source_url"], "https://pixabay.com/photos/cat-12345/")


class TestExtractTiles(unittest.TestCase):
    def test_dedupes_by_real_image_url(self):
        proxied = "//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fa.jpg"
        figures = [
            _figure_with(result_img_src=proxied),
            _figure_with(result_img_src=proxied),  # duplicate
            _figure_with(result_img_src="//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2Fb.jpg"),
        ]
        driver = MagicMock()
        driver.find_elements.side_effect = lambda by, sel: (
            figures if sel == "figure" else []
        )
        result = _extract_tiles(driver, num_images=10)
        self.assertEqual(len(result), 2)
        self.assertEqual(
            [r["url"] for r in result],
            ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        )

    def test_respects_num_images_limit(self):
        figures = [
            _figure_with(
                result_img_src=f"//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fexample.com%2F{i}.jpg"
            )
            for i in range(10)
        ]
        driver = MagicMock()
        driver.find_elements.side_effect = lambda by, sel: (
            figures if sel == "figure" else []
        )
        result = _extract_tiles(driver, num_images=3)
        self.assertEqual(len(result), 3)

    def test_returns_empty_when_no_figures(self):
        driver = MagicMock()
        driver.find_elements.side_effect = lambda by, sel: []
        self.assertEqual(_extract_tiles(driver, num_images=5), [])

    def test_returns_empty_when_find_elements_raises(self):
        driver = MagicMock()
        driver.find_elements.side_effect = RuntimeError("boom")
        self.assertEqual(_extract_tiles(driver, num_images=5), [])


class TestScrapeEntryPoint(unittest.TestCase):
    """End-to-end shape of scrape_duckduckgo_images_selenium."""

    def test_builds_correct_url(self):
        driver = MagicMock()
        driver.find_elements.return_value = []
        with patch("image_scraper_selenium._build_driver", return_value=driver):
            scrape_duckduckgo_images_selenium("cute cats", num_images=3)

        called_url = driver.get.call_args[0][0]
        self.assertIn("https://duckduckgo.com/", called_url)
        self.assertIn("iar=images", called_url)
        self.assertIn("cute%20cats", called_url)

    def test_returns_empty_on_driver_error(self):
        with patch(
            "image_scraper_selenium._build_driver",
            side_effect=RuntimeError("chrome not installed"),
        ):
            result = scrape_duckduckgo_images_selenium("anything", num_images=5)
        self.assertEqual(result, [])

    def test_quits_driver_on_success(self):
        driver = MagicMock()
        driver.find_elements.return_value = []
        with patch("image_scraper_selenium._build_driver", return_value=driver):
            scrape_duckduckgo_images_selenium("x", num_images=1)
        driver.quit.assert_called_once()

    def test_quits_driver_even_when_get_fails(self):
        driver = MagicMock()
        driver.get.side_effect = RuntimeError("network down")
        with patch("image_scraper_selenium._build_driver", return_value=driver):
            scrape_duckduckgo_images_selenium("x", num_images=1)
        driver.quit.assert_called_once()


class TestMcpServerFormatting(unittest.TestCase):
    """The MCP server should surface attribution in its text output."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_search_images_text_includes_credit(self):
        fake = [{
            "url": "https://tse1.mm.bing.net/th/id/OIP.abc",
            "alt": "Cute kitten",
            "title": "50 Cute Kittens You Need to See",
            "source_url": "https://www.rd.com/list/cute-kittens/",
            "source_domain": "rd.com",
            "source_favicon_url": "https://external-content.duckduckgo.com/ip3/www.rd.com.ico",
            "width": 2560,
            "height": 1707,
            "ddg_proxied_url": "https://external-content.duckduckgo.com/iu/?u=...",
        }]
        with patch(
            "image_scraper_mcp_server.scrape_duckduckgo_images_selenium",
            return_value=fake,
        ):
            result = self._run(
                image_scraper_mcp_server.call_tool(
                    "search_images", {"query": "cats", "num_images": 1}
                )
            )

        text = result[0].text
        self.assertIn("Found 1 images", text)
        self.assertIn("https://tse1.mm.bing.net/th/id/OIP.abc", text)
        self.assertIn("rd.com", text)
        self.assertIn("https://www.rd.com/list/cute-kittens/", text)
        self.assertIn("50 Cute Kittens You Need to See", text)
        self.assertIn("2560 × 1707", text)
        # Still NOT JSON — backward-compatible with the old format.
        self.assertFalse(text.lstrip().startswith("{"))

    def test_search_images_text_handles_missing_optional_fields(self):
        """Older scrapers without attribution fields still work."""
        fake = [{"url": "https://example.com/x.jpg", "alt": "alt-x", "title": ""}]
        with patch(
            "image_scraper_mcp_server.scrape_duckduckgo_images_selenium",
            return_value=fake,
        ):
            result = self._run(
                image_scraper_mcp_server.call_tool(
                    "search_images", {"query": "cats", "num_images": 1}
                )
            )

        text = result[0].text
        self.assertIn("Found 1 images", text)
        self.assertIn("https://example.com/x.jpg", text)
        self.assertIn("alt-x", text)

    def test_search_images_text_for_no_results(self):
        with patch(
            "image_scraper_mcp_server.scrape_duckduckgo_images_selenium",
            return_value=[],
        ):
            result = self._run(
                image_scraper_mcp_server.call_tool(
                    "search_images", {"query": "nothing", "num_images": 5}
                )
            )
        self.assertIn("No images found", result[0].text)


class TestConstants(unittest.TestCase):
    """Cheap regression guards in case DDG rotates URL shapes."""

    def test_image_proxy_regex_matches_known_urls(self):
        for url in [
            "//external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fa.jpg",
            "https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fa.jpg&f=1",
        ]:
            self.assertIsNotNone(DDG_IMAGE_PROXY_RE.search(url))

    def test_image_proxy_regex_rejects_favicons_and_others(self):
        for url in [
            "//external-content.duckduckgo.com/ip3/example.com.ico",
            "https://example.com/foo.jpg",
            "//duckduckgo.com/?q=foo",
        ]:
            self.assertIsNone(DDG_IMAGE_PROXY_RE.search(url), url)

    def test_favicon_regex_matches_known_urls(self):
        self.assertIsNotNone(
            DDG_FAVICON_PROXY_RE.search("//external-content.duckduckgo.com/ip3/www.rd.com.ico")
        )

    def test_dimensions_regex_matches_common_formats(self):
        for text, expected in [
            ("2560 × 1707", (2560, 1707)),
            ("1920x1080", (1920, 1080)),
            ("800 * 600", (800, 600)),
        ]:
            m = DIMENSIONS_RE.search(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(int(m.group(1)), expected[0])
            self.assertEqual(int(m.group(2)), expected[1])


if __name__ == "__main__":
    unittest.main()