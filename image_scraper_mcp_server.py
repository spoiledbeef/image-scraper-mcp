#!/usr/bin/env python3
"""
MCP Server for Image Search
Exposes image scraping functionality as MCP tools.
"""

import asyncio
import json
from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import AnyUrl
import mcp.server.stdio

from image_scraper_selenium import scrape_duckduckgo_images_selenium
from image_scraper_maps import scrape_google_maps_images


# Create an MCP server instance
server = Server("image-scraper-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="search_images",
            description="Search for images on DuckDuckGo and return image URLs with metadata. "
                       "This tool uses Selenium to scrape image results from DuckDuckGo Images.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for images (e.g., 'cute cats', 'mountain sunset')",
                    },
                    "num_images": {
                        "type": "integer",
                        "description": "Number of images to retrieve (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Run browser in headless mode (default: true)",
                        "default": True,
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_maps_images",
            description="Search Google Maps for a place and return photo URLs from the place page. "
                       "Accepts a place name like 'Eiffel Tower' or 'Joe's Pizza NYC'. "
                       "Uses Selenium to scrape photos from the Google Maps place panel — no API key required. "
                       "Returns a JSON object with each photo's URL, author, and author profile URL so "
                       "callers can credit the photographer if they reuse the image.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Place to search for on Google Maps (e.g., 'Eiffel Tower', 'Joe's Pizza NYC')",
                    },
                    "num_images": {
                        "type": "integer",
                        "description": "Number of photos to retrieve (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "headless": {
                        "type": "boolean",
                        "description": "Run browser in headless mode (default: true)",
                        "default": True,
                    },
                    "require_attribution": {
                        "type": "boolean",
                        "description": "If true, return only photos with visible author attribution. "
                                       "If false (default), prefer attributed photos but fall back to the "
                                       "place's official photo strip when fewer attributed photos are available. "
                                       "Attributed photos are always returned first.",
                        "default": False,
                    }
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    query = arguments.get("query")
    num_images = arguments.get("num_images", 5)
    headless = arguments.get("headless", True)

    if not query:
        raise ValueError("Query parameter is required")

    if name == "search_images":
        scraper = scrape_duckduckgo_images_selenium
        images = await _run_scraper(scraper, query, num_images, headless)
        return [TextContent(type="text", text=_format_text(query, images))]
    elif name == "search_maps_images":
        require_attribution = arguments.get("require_attribution", False)
        images = await _run_scraper(
            scrape_google_maps_images, query, num_images, headless,
            require_attribution=require_attribution,
        )
        payload = {
            "query": query,
            "source": "google_maps",
            "count": len(images),
            "images": [
                {
                    "url": img["url"],
                    "author": img.get("author", ""),
                    "author_profile_url": img.get("author_profile_url", ""),
                }
                for img in images
            ],
        }
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _run_scraper(scraper, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: scraper(*args, **kwargs))


def _format_text(query: str, images: list) -> str:
    if images:
        result_text = f"Found {len(images)} images for '{query}':\n\n"
        for idx, img in enumerate(images, 1):
            result_text += f"{idx}. {img['url']}\n"
            if img.get('alt'):
                result_text += f"   Alt: {img['alt']}\n"
            result_text += "\n"
    else:
        result_text = f"No images found for '{query}'."
    return result_text


async def main():
    """Main entry point for the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
