#!/usr/bin/env python3
"""
Debug version to inspect Google Images page structure
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from urllib.parse import quote
import time

def debug_google_images(query):
    """Debug function to see what's on the page."""
    chrome_options = Options()
    # Run in non-headless mode to see what's happening
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        encoded_query = quote(query)
        url = f"https://www.google.com/search?q={encoded_query}&tbm=isch"
        
        print(f"Loading: {url}")
        driver.get(url)
        time.sleep(5)  # Wait for page to fully load
        
        # Save screenshot
        driver.save_screenshot("debug_screenshot.png")
        print("Screenshot saved as debug_screenshot.png")
        
        # Find all images
        all_imgs = driver.find_elements(By.TAG_NAME, 'img')
        print(f"\nTotal img tags found: {len(all_imgs)}")
        
        # Check different selectors
        selectors = [
            'div[data-id]',
            'img[data-tbnid]',
            'img[class*="rg_i"]',
            'div[role="listitem"]',
            'img[jsname]',
            'a[jsname="sTFXNd"]',
        ]
        
        print("\nTrying different selectors:")
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            print(f"  {selector}: {len(elements)} elements")
        
        # Get first few image srcs
        print("\nFirst 5 image sources:")
        for idx, img in enumerate(all_imgs[:5], 1):
            src = img.get_attribute('src')
            alt = img.get_attribute('alt')
            classes = img.get_attribute('class')
            print(f"  {idx}. src={src[:100] if src else 'None'}")
            print(f"      alt={alt}")
            print(f"      class={classes}")
            print()
        
        # Try clicking first image
        print("Attempting to click first clickable image...")
        clickable = driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"] img, img[class*="rg_i"]')
        if clickable:
            print(f"Found {len(clickable)} clickable images")
            clickable[0].click()
            time.sleep(2)
            driver.save_screenshot("debug_after_click.png")
            print("After-click screenshot saved as debug_after_click.png")
            
            # Look for large image
            large_selectors = ['img.sFlh5c', 'img.n3VNCb', 'img[jsname]']
            for sel in large_selectors:
                imgs = driver.find_elements(By.CSS_SELECTOR, sel)
                print(f"\n{sel}: {len(imgs)} found")
                for img in imgs[:3]:
                    src = img.get_attribute('src')
                    if src and 'http' in src:
                        print(f"  -> {src[:100]}")
        
        print("\nKeeping browser open for 10 seconds so you can inspect...")
        time.sleep(10)
        
    finally:
        driver.quit()

if __name__ == "__main__":
    debug_google_images("cute cats")
