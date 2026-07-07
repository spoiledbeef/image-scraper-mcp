# Image Scraper

A Python web scraper that retrieves images for a given search query. Supports **DuckDuckGo Images** and **Google Maps place photos** — no API key required, and every result carries the credit/attribution you need to safely reuse the image.

## Features

- **Three scraping scripts**:
  - **`image_scraper_selenium.py`** (Selenium DuckDuckGo) — recommended; returns the real image URL plus full source attribution
  - **`image_scraper_maps.py`** (Selenium Google Maps) — place photo scraper with photographer attribution
  - **`image_scraper.py`** (BeautifulSoup DuckDuckGo) — fast fallback that only returns URL + alt text
- **MCP server** (`image_scraper_mcp_server.py`) exposing both `search_images` and `search_maps_images` tools
- **Credit & attribution built-in** — every result includes the publisher domain, source page URL, article title, and image dimensions so you can credit the image instead of just receiving a proxied redirect
- Configurable number of images, headless mode, and error handling

## Credit & Attribution

Reusing images from search results requires credit. Both scrapers are built to give you what you need:

| Tool | What you get for credit |
| --- | --- |
| `search_images` (DDG) | `source_domain`, `source_url`, `title`, `source_favicon_url`, `width`, `height` — the real image URL, with DDG's `iu/?u=` redirector unwrapped |
| `search_maps_images` (Google Maps) | `author` (the Google Maps contributor's name) and `author_profile_url` — the photographer's profile URL |

Suggested credit format:

- **DuckDuckGo results**: `Image: {title or alt} — {source_domain} ({source_url})`. If `source_domain` or `source_url` is missing for a result, treat that entry as low-attribution and prefer a different one.
- **Google Maps results with an author**: `Photo by {author} ({author_profile_url})`.
- **Google Maps results with no author** (official place photos): `Image: {Place Name} via Google Maps` or `Source: Google Maps`.

## Installation

1. Install Python dependencies:
```bash
uv sync
```

2. Make sure you have Google Chrome installed (required for Selenium).
   Selenium 4+ automatically manages ChromeDriver, no manual installation needed.

## Usage

### Selenium DuckDuckGo (recommended)

```bash
uv run python image_scraper_selenium.py "cute cats" 5
```

Prints a JSON payload with attribution per image:

```json
{
  "query": "cute kittens",
  "source": "duckduckgo",
  "count": 2,
  "images": [
    {
      "url": "https://tse3.mm.bing.net/th/id/OIP.6ytt01A4fK8ToB7he6XJegHaFD?pid=Api",
      "alt": "Cute Kittens Playing With Yarn Free Stock Photo - Public Domain Pictures",
      "title": "Cute Kittens Playing With Yarn Free Stock Photo - Public Domain Pictures",
      "source_url": "https://www.publicdomainpictures.net/en/view-image.php?image=588007&picture=cute-kittens-playing-with-yarn",
      "source_domain": "publicdomainpictures.net",
      "source_favicon_url": "https://external-content.duckduckgo.com/ip3/www.publicdomainpictures.net.ico",
      "width": 1920,
      "height": 1309,
      "ddg_proxied_url": "https://external-content.duckduckgo.com/iu/?u=..."
    }
  ]
}
```

The `url` is the **real** image URL (DDG's `external-content.duckduckgo.com/iu/?u=` redirector is unwrapped). `ddg_proxied_url` is kept for reference. Width and height are read from the dimensions overlay on the result tile.

When called through the MCP server, the same data is rendered as human-readable text that includes a `Credit:` line per result, plus the source page title and dimensions:

```
Found 2 images for 'cute kittens':

1. https://tse3.mm.bing.net/th/id/OIP.6ytt01A4fK8ToB7he6XJegHaFD?pid=Api
   Credit: publicdomainpictures.net (https://www.publicdomainpictures.net/en/view-image.php?image=588007&picture=cute-kittens-playing-with-yarn)
   Title: Cute Kittens Playing With Yarn Free Stock Photo - Public Domain Pictures
   Dimensions: 1920 × 1309
   Alt: Cute Kittens Playing With Yarn Free Stock Photo - Public Domain Pictures

2. https://tse1.mm.bing.net/th/id/OIP.So-qlqEv3QwuZpL4cOY-PwHaHa?pid=Api
   Credit: wallpaperaccess.com (https://wallpaperaccess.com/cute-cats-and-kittens)
   Title: Cute Cats and Kittens Wallpapers - Top Free Cute Cats and Kittens ...
   Dimensions: 2560 × 1600
   Alt: Cute Cats and Kittens Wallpapers - Top Free Cute Cats and Kittens ...
```

### Google Maps place photos

```bash
uv run python image_scraper_maps.py "Eiffel Tower" 5
```

```json
{
  "query": "Joe's Pizza NYC",
  "source": "google_maps",
  "count": 3,
  "images": [
    {
      "url": "https://lh3.googleusercontent.com/...",
      "author": "Mary van Lutsenburg Maas",
      "author_profile_url": "https://www.google.com/maps/contrib/118270766331517021243"
    }
  ]
}
```

By default, the scraper prefers photos with visible author attribution and falls back to the place's official photo strip when fewer attributed photos are available — so you always get `num_images` results if any exist. Attributed photos are returned first, then official ones fill the remaining slots. Pass `require_attribution: true` to disable the fallback and only get attributed photos.

### BeautifulSoup DuckDuckGo (no Selenium, fast)

```bash
uv run python image_scraper.py "cute cats" 5
```

Lightweight fallback. Only returns the proxied image URL and the `alt` text — no source attribution. Use this only when you need a fast scrape and don't need to credit the result.

### Specifying the number of images

All scrapers accept an optional second argument for the result count (1–50, default 5):

```bash
uv run python image_scraper_selenium.py "sports cars" 10
uv run python image_scraper_maps.py "Eiffel Tower" 8
uv run python image_scraper.py "golden retriever puppy" 5
```

## MCP Server

`image_scraper_mcp_server.py` exposes two tools:

| Tool | Use for | Returns |
| --- | --- | --- |
| `search_images` | General image search (DDG) | Text output with `Credit:`, `Title:`, `Dimensions:`, `Alt:` per result |
| `search_maps_images` | Place photos (Google Maps) | JSON output with `author` and `author_profile_url` per photo |

### `search_images` parameters

- `query` (required): Search query
- `num_images` (optional, default 5, range 1–50): Number of results
- `headless` (optional, default true): Run Chrome headless

### `search_maps_images` parameters

- `query` (required): Place name (e.g. `"Eiffel Tower"`, `"Joe's Pizza NYC"`)
- `num_images` (optional, default 5, range 1–50): Number of photos
- `headless` (optional, default true): Run Chrome headless
- `require_attribution` (optional, default false): If `true`, only return photos with visible author attribution. If `false` (default), prefer attributed photos but fall back to the place's official photo strip when fewer attributed photos are available.

See [MCP_SETUP.md](MCP_SETUP.md) for installing the server as a Docker-based MCP tool for Claude Desktop or other MCP clients.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
```

87 tests cover both scrapers and the MCP server, with all browser interactions stubbed so they run in seconds without Chrome or network access:

- `tests/test_image_scraper_ddg.py` — DDG URL decoding, dimensions parser, tile attribution, MCP text formatting
- `tests/test_image_scraper_maps.py` — Google Maps review-photo extraction, fallback, MCP JSON formatting

## Notes

- DuckDuckGo is generally more scraper-friendly than Google.
- The Selenium DuckDuckGo scraper is more reliable than the BeautifulSoup version and returns proper attribution.
- Some images may be low resolution or thumbnails; check `width` and `height` before reuse.
- Respect robots.txt and the terms of service of DuckDuckGo and Google Maps.
- Reuse of copyrighted images may require permission from the publisher; the attribution fields tell you who to ask.

## License

MIT License — feel free to use and modify as needed.
