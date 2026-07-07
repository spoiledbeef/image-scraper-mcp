#!/usr/bin/env python3
"""
Debug DuckDuckGo page structure
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from urllib.parse import quote
import time

query = "cute cats"
encoded_query = quote(query)
url = f"https://duckduckgo.com/?q={encoded_query}&iar=images&iax=images&ia=images"

chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

service = Service()
driver = webdriver.Chrome(service=service, options=chrome_options)

print(f"Loading: {url}\n")
driver.get(url)
time.sleep(5)

# Save page source and screenshot
with open("page_source.html", "w", encoding="utf-8") as f:
    f.write(driver.page_source)
print("Page source saved to page_source.html")

driver.save_screenshot("ddg_screenshot.png")
print("Screenshot saved to ddg_screenshot.png\n")

# Try different selectors
selectors = [
    'img',
    'img[class*="tile"]',
    'img.tile--img__img',
    'div.tile',
    'div[class*="tile"]',
    'img[data-id]',
    'img[src*="http"]',
    'div.js-images-link',
    'a.tile--img',
    'div.js-lazyload',
]

print("Testing selectors:")
for selector in selectors:
    elements = driver.find_elements(By.CSS_SELECTOR, selector)
    print(f"  {selector}: {len(elements)} elements")

# Show first 10 images
all_imgs = driver.find_elements(By.TAG_NAME, 'img')
print(f"\nFirst 10 images found ({len(all_imgs)} total):")
for idx, img in enumerate(all_imgs[:10], 1):
    src = img.get_attribute('src')
    classes = img.get_attribute('class')
    print(f"  {idx}. class='{classes}'")
    print(f"      src={src[:100] if src else 'None'}\n")

print("\nKeeping browser open for 10 seconds...")
time.sleep(10)

driver.quit()
