#!/usr/bin/env python3
"""
DuckDuckGo Images Scraper (Selenium version)
Uses Selenium WebDriver for browser automation to scrape image results.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from urllib.parse import quote
import time
import sys


def scrape_duckduckgo_images_selenium(query, num_images=5, headless=True):
    """
    Scrape DuckDuckGo Images using Selenium for better reliability.
    
    Args:
        query (str): Search query for DuckDuckGo Images
        num_images (int): Number of images to retrieve (default: 5)
        headless (bool): Run browser in headless mode (default: True)
    
    Returns:
        list: List of dictionaries containing image URLs and metadata
    """
    # Set up Chrome options
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Support both Chrome and Chromium
    import os
    if os.getenv('CHROME_BIN'):
        chrome_options.binary_location = os.getenv('CHROME_BIN')
    
    driver = None
    images = []
    
    try:
        # Initialize the driver with automatic driver management
        # Selenium 4.6+ includes automatic driver management
        service_kwargs = {}
        if os.getenv('CHROMEDRIVER_PATH'):
            service_kwargs['executable_path'] = os.getenv('CHROMEDRIVER_PATH')
        
        service = Service(**service_kwargs)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Build the DuckDuckGo Images URL
        encoded_query = quote(query)
        url = f"https://duckduckgo.com/?q={encoded_query}&iar=images"
        
        print(f"Loading: {url}")
        driver.get(url)
        
        # Wait for images to load
        time.sleep(3)
        
        wait = WebDriverWait(driver, 15)
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, 'img')))
        except:
            print("Waiting for images to load...")
            time.sleep(2)
        
        # Scroll to load more images
        print("Scrolling to load images...")
        for _ in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
        
        # DuckDuckGo uses external-content.duckduckgo.com for image results
        print("Looking for image results...")
        all_images = driver.find_elements(By.CSS_SELECTOR, 'img[src*="http"]')
        
        print(f"Found {len(all_images)} images with http sources")
        
        # Track seen URLs to avoid duplicates
        seen_urls = set()
        
        # Filter for actual image results (external-content URLs)
        for img in all_images:
            if len(images) >= num_images:
                break
            
            try:
                src = img.get_attribute('src')
                
                # DuckDuckGo image results are served via external-content.duckduckgo.com
                if src and 'external-content.duckduckgo.com/iu/' in src:
                    if src not in seen_urls:
                        seen_urls.add(src)
                        
                        alt_text = img.get_attribute('alt') or query
                        
                        images.append({
                            'url': src,
                            'alt': alt_text,
                            'title': query
                        })
                        
                        print(f"  ✓ Found image {len(images)}: {src[:80]}...")
            
            except Exception as e:
                continue
        
        return images[:num_images]
    
    except Exception as e:
        print(f"Error during scraping: {e}", file=sys.stderr)
        return images
    
    finally:
        if driver:
            driver.quit()


def main():
    """Main function to run the Selenium scraper from command line."""
    if len(sys.argv) < 2:
        print("Usage: python image_scraper_selenium.py <search_query> [num_images]")
        print("Example: python image_scraper_selenium.py 'cute cats' 5")
        sys.exit(1)
    
    query = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"Searching for: {query}")
    print(f"Number of images: {num_images}\n")
    
    # Scrape images
    images = scrape_duckduckgo_images_selenium(query, num_images)
    
    if images:
        print(f"\n{'='*80}")
        print(f"Found {len(images)} images:\n")
        for idx, img in enumerate(images, 1):
            print(f"{idx}. {img['url']}")
            if img['alt']:
                print(f"   Alt: {img['alt']}")
            print()
    else:
        print("No images found.")


if __name__ == "__main__":
    main()
