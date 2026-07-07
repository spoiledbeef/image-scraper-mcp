# DuckDuckGo Images Scraper

A Python web scraper that retrieves the first five (or more) DuckDuckGo Image results for a given search query.

## Features

- Two scraping methods:
  - **BeautifulSoup version** (`image_scraper.py`): Lightweight and fast
  - **Selenium version** (`image_scraper_selenium.py`): More reliable with better results
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

## Examples

```bash
# Get 5 images of mountains
uv run python image_scraper.py "mountains"

# Get 10 images of sports cars using Selenium
uv run python image_scraper_selenium.py "sports cars" 10

# Search for multiple words
uv run python image_scraper.py "golden retriever puppy" 5
```

## Output

The scraper will display:
- Search query
- Number of images requested
- List of image URLs with metadata
- Option to download images (BeautifulSoup version)

## Notes

- DuckDuckGo is generally more scraper-friendly than Google
- The Selenium version is more reliable and gets better quality images
- Some images may be low resolution or thumbnails
- Downloads are saved to the `downloads/` directory
- Respect robots.txt and DuckDuckGo's terms of service

## License

MIT License - feel free to use and modify as needed.
