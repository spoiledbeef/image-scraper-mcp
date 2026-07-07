#!/bin/bash
# Script to run the MCP server in Docker with proper stdio handling

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Build the image if it doesn't exist or if --build flag is passed
if [[ "$1" == "--build" ]] || ! docker image inspect image-scraper-mcp:latest &> /dev/null; then
    echo "Building Docker image..." >&2
    docker build -t image-scraper-mcp:latest "$SCRIPT_DIR"
fi

# Run the container with stdio
docker run -i --rm \
    --shm-size=2gb \
    image-scraper-mcp:latest
