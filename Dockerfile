FROM python:3.12-slim

# Install Chromium and dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY image_scraper_selenium.py ./
COPY image_scraper_mcp_server.py ./

# Install uv for faster dependency management
RUN pip install --no-cache-dir uv

# Install project dependencies
RUN uv pip install --system requests beautifulsoup4 selenium lxml mcp

# Create a non-root user for security
RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

# Set environment variables for Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:99

# Run the MCP server
CMD ["python", "image_scraper_mcp_server.py"]
