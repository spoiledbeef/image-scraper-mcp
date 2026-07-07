# Image Scraper MCP Tool Setup

This guide explains how to use the DuckDuckGo image scraper as an MCP (Model Context Protocol) tool using Docker.

## What is MCP?

MCP (Model Context Protocol) allows you to expose tools that AI assistants like Claude can use directly. This means Claude can search for images using your scraper!

## Installation

### Prerequisites

- Docker installed on your system
- Docker daemon running

### Build the Docker Image

```bash
docker build -t image-scraper-mcp:latest .
```

Or use the helper script (which auto-builds on first run):
```bash
chmod +x run_mcp_docker.sh
./run_mcp_docker.sh --build
```

### Test the MCP Server

Run the server manually to test:
```bash
./run_mcp_docker.sh
```

Or with docker directly:
```bash
docker run -i --rm --shm-size=2gb image-scraper-mcp:latest
```

## Configuration

### For Claude Desktop

Add this to your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "image-scraper": {
      "command": "./run_mcp_docker.sh",
      "args": []
    }
  }
}
```

**Note**: Update the path to match your actual installation directory.

### For Other MCP Clients

Use the configuration from `mcp_config_example.json` and adapt it to your client's format.

## Using the Tool

Once configured, you can ask Claude to search for images:

- "Search for 5 images of cute cats"
- "Find 10 images of mountain sunsets"
- "Look for images of vintage cars"
- "Find 8 photos of the Eiffel Tower on Google Maps"
- "Show me 5 photos of Joe's Pizza in NYC from Google Maps"

The `search_images` tool returns formatted text with each image's source attribution — including the publisher domain, source page URL, article title, and image dimensions — so you can credit the image instead of just getting a proxied redirect.
The `search_maps_images` tool returns a JSON payload with each photo's URL, the contributor's name, and the contributor's profile URL — so you can credit the photographer if you reuse the image.

### `search_images` output

```
Found 2 images for 'cute kittens':

1. https://tse3.mm.bing.net/th/id/OIP.6ytt01A4fK8ToB7he6XJegHaFD?pid=Api
   Credit: publicdomainpictures.net (https://www.publicdomainpictures.net/en/view-image.php?image=588007&picture=cute-kittens-playing-with-yarn)
   Title: Cute Kittens Playing With Yarn Free Stock Photo - Public Domain Pictures
   Dimensions: 1920 × 1309
   Alt: Cute Kittens Playing With Yarn Free Stock Photo - Public Domain Pictures
```

The `url` returned is the real image URL with DuckDuckGo's `iu/?u=` redirector unwrapped. Suggested credit format: `Image: {title or alt} — {source_domain} ({source_url})`.

### `search_maps_images` JSON shape

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

By default, the scraper prefers photos with visible author attribution and falls back to the place's official photo strip when fewer attributed photos are available — so you always get `num_images` results if any exist. Attributed photos are returned first, then official ones fill the remaining slots. Pass `require_attribution: true` to disable the fallback and only get attributed photos. Suggested credit format with an author: `Photo by {author} ({author_profile_url})`. For official photos with no author: `Image: {Place Name} via Google Maps`.

## Tool Parameters

### `search_images`

- `query` (required): Search query for images
- `num_images` (optional): Number of images to retrieve (1-50, default: 5)
- `headless` (optional): Run browser in headless mode (default: true)

Each result includes `url`, `alt`, `title`, `source_url`, `source_domain`, `source_favicon_url`, `width`, `height`, and the original `ddg_proxied_url` for reference.

### `search_maps_images`

- `query` (required): Place to search for on Google Maps (e.g. "Eiffel Tower", "Joe's Pizza NYC")
- `num_images` (optional): Number of photos to retrieve (1-50, default: 5)
- `headless` (optional): Run browser in headless mode (default: true)
- `require_attribution` (optional, default: false): If true, only return photos with visible author attribution. If false (default), prefer attributed photos but fall back to the place's official photo strip when fewer attributed photos are available.

Each result includes `url`, `author` (contributor name), and `author_profile_url` (the contributor's Google Maps profile URL).

## Testing the MCP Server

You can test the server using the MCP inspector:

```bash
npx @modelcontextprotocol/inspector docker run --rm -i image-scraper-mcp:latest
```

Or simply run the helper script:
```bash
./run_mcp_docker.sh
```

## Docker Advantages

- **Isolated Environment**: All dependencies (Chrome, ChromeDriver, Python packages) are contained
- **Consistent Behavior**: Works the same on any system with Docker
- **No Local Dependencies**: No need to install Chrome or Python packages on your host system
- **Easy Updates**: Rebuild the image to update dependencies

## Troubleshooting

1. **Docker not running**: Make sure Docker daemon is running
   ```bash
   docker ps
   ```

2. **Permission errors**: Ensure the script has execute permissions:
   ```bash
   chmod +x run_mcp_docker.sh
   ```

3. **Server not appearing in Claude**: 
   - Restart Claude Desktop after updating the config file
   - Check that the path in the config points to the correct location
   - Test the script manually: `./run_mcp_docker.sh`

4. **Image build fails**: Try cleaning Docker cache:
   ```bash
   docker system prune -a
   docker build --no-cache -t image-scraper-mcp:latest .
   ```

5. **Chrome crashes in container**: The `--shm-size=2gb` flag is required for Chrome to work properly in Docker

## Alternative: Docker Compose

You can also use docker-compose:

```bash
docker-compose build
docker-compose run --rm image-scraper-mcp
```
