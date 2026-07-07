# Image Scraper

A Python web scraper that retrieves images for a given search query. Supports DuckDuckGo Images and Google Maps place photos (no API key required).

## Features

- Three scraping scripts:
  - **BeautifulSoup DuckDuckGo** (`image_scraper.py`): Lightweight and fast
  - **Selenium DuckDuckGo** (`image_scraper_selenium.py`): More reliable with better results
  - **Selenium Google Maps** (`image_scraper_maps.py`): Place photo scraper (no API key)
- MCP server (`image_scraper_mcp_server.py`) exposing both `search_images` and `search_maps_images` tools
- Configurable number of images to retrieve
- Option to download images locally
- Error handling and user-friendly output

## Installation

1. Install Python dependencies:
```bash
uv sync
```

2. Make sure you have Google Chrome installed (required for Selenium version)
   - Selenium 4+ automatically manages ChromeDriver, no manual installation needed!

## Usage

### Basic Usage (BeautifulSoup version)

```bash
uv run python image_scraper.py "cute cats"
```

### Specify number of images

```bash
uv run python image_scraper.py "cute cats" 10
```

### Using Selenium version (recommended)

```bash
uv run python image_scraper_selenium.py "cute cats" 5
```

### Google Maps place photos

```bash
uv run python image_scraper_maps.py "Eiffel Tower" 5
```

The Google Maps scraper returns **JSON** with each photo's URL, contributor name, and contributor profile URL so you can credit the photographer if you reuse the image:

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

By default, the scraper prefers photos with visible author attribution and falls back to the place's official photo strip when fewer attributed photos are available — so you always get `num_images` results if any exist. Attributed photos are returned first, then official ones fill the remaining slots. Pass `require_attribution: true` (MCP) to disable the fallback and only get attributed photos.

Suggested credit format when an author is present: `Photo by {author} ({author_profile_url})`. For official photos with no author, use `Image: {Place Name} via Google Maps` or `Source: Google Maps`.

## Examples

```bash
# Get 5 images of mountains
uv run python image_scraper.py "mountains"

# Get 10 images of sports cars using Selenium
uv run python image_scraper_selenium.py "sports cars" 10

# Search for multiple words
uv run python image_scraper.py "golden retriever puppy" 5

# Get 8 photos of a restaurant from Google Maps (attributed only)
uv run python image_scraper_maps.py "Joe's Pizza NYC" 8
```

## Output

The DuckDuckGo scrapers display:
- Search query
- Number of images requested
- List of image URLs with metadata
- Option to download images (BeautifulSoup version)

The Google Maps scraper prints a JSON payload as shown above.

## Notes

- DuckDuckGo is generally more scraper-friendly than Google
- The Selenium version is more reliable and gets better quality images
- Some images may be low resolution or thumbnails
- Downloads are saved to the `downloads/` directory
- Respect robots.txt and DuckDuckGo's terms of service

## License

MIT License - feel free to use and modify as needed.
