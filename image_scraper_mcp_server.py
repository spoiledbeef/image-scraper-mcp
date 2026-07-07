#!/usr/bin/env python3
"""
MCP Server for DuckDuckGo Image Search
Exposes image scraping functionality as an MCP tool.
"""

import asyncio
from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import AnyUrl
import mcp.server.stdio

from image_scraper_selenium import scrape_duckduckgo_images_selenium


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
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if name != "search_images":
        raise ValueError(f"Unknown tool: {name}")
    
    # Extract arguments
    query = arguments.get("query")
    num_images = arguments.get("num_images", 5)
    headless = arguments.get("headless", True)
    
    if not query:
        raise ValueError("Query parameter is required")
    
    # Run the scraper in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    images = await loop.run_in_executor(
        None,
        scrape_duckduckgo_images_selenium,
        query,
        num_images,
        headless
    )
    
    # Format results
    if images:
        result_text = f"Found {len(images)} images for '{query}':\n\n"
        for idx, img in enumerate(images, 1):
            result_text += f"{idx}. {img['url']}\n"
            if img.get('alt'):
                result_text += f"   Alt: {img['alt']}\n"
            result_text += "\n"
    else:
        result_text = f"No images found for '{query}'."
    
    return [TextContent(type="text", text=result_text)]


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
