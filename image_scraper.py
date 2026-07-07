#!/usr/bin/env python3
"""
DuckDuckGo Images Scraper
Fetches the first 5 image results for a given search query.
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import quote
import sys


def scrape_duckduckgo_images(query, num_images=5):
    """
    Scrape DuckDuckGo Images for a given query.
    
    Args:
        query (str): Search query for DuckDuckGo Images
        num_images (int): Number of images to retrieve (default: 5)
    
    Returns:
        list: List of dictionaries containing image URLs and metadata
    """
    # URL encode the query
    encoded_query = quote(query)
    url = f"https://duckduckgo.com/?q={encoded_query}&iar=images&iax=images&ia=images"
    
    # Headers to mimic a browser request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        # Make the request
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find image data in the page
        images = []
        
        # DuckDuckGo stores image data in data-id attributes and noscript tags
        # Method 1: Look for image tiles
        img_tiles = soup.find_all('img', class_=re.compile('tile.*img'))
        for img in img_tiles:
            if len(images) >= num_images:
                break
            
            src = img.get('src') or img.get('data-src')
            if src and src.startswith('http'):
                images.append({
                    'url': src,
                    'alt': img.get('alt', query),
                    'title': query
                })
        
        # Method 2: Extract from script tags (DuckDuckGo stores image data in vqd)
        if len(images) < num_images:
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # Try to extract image URLs from the script content
                    try:
                        urls = re.findall(r'https?://[^"\'>\s]+\.(?:jpg|jpeg|png|gif|webp)[^"\'>\s]*', 
                                        script.string, re.IGNORECASE)
                        for url in urls:
                            if len(images) >= num_images:
                                break
                            if url not in [img['url'] for img in images]:
                                images.append({
                                    'url': url,
                                    'alt': query,
                                    'title': query
                                })
                    except Exception as e:
                        continue
        
        # Remove duplicates and limit to requested number
        unique_images = []
        seen_urls = set()
        for img in images:
            if img['url'] not in seen_urls:
                seen_urls.add(img['url'])
                unique_images.append(img)
                if len(unique_images) >= num_images:
                    break
        
        return unique_images
    
    except requests.RequestException as e:
        print(f"Error fetching images: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return []


def download_images(images, output_dir='downloads'):
    """
    Download images to a local directory.
    
    Args:
        images (list): List of image dictionaries with URLs
        output_dir (str): Directory to save images
    """
    import os
    
    os.makedirs(output_dir, exist_ok=True)
    
    for idx, img in enumerate(images, 1):
        try:
            response = requests.get(img['url'], timeout=10)
            response.raise_for_status()
            
            # Determine file extension from URL or content-type
            ext = img['url'].split('.')[-1].split('?')[0][:4]
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'
            
            filename = f"{output_dir}/image_{idx}.{ext}"
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"Downloaded: {filename}")
        except Exception as e:
            print(f"Failed to download image {idx}: {e}", file=sys.stderr)


def main():
    """Main function to run the scraper from command line."""
    if len(sys.argv) < 2:
        print("Usage: python image_scraper.py <search_query> [num_images]")
        print("Example: python image_scraper.py 'cute cats' 5")
        sys.exit(1)
    
    query = sys.argv[1]
    num_images = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"Searching for: {query}")
    print(f"Number of images: {num_images}\n")
    
    # Scrape images
    images = scrape_duckduckgo_images(query, num_images)
    
    if images:
        print(f"\nFound {len(images)} images:\n")
        for idx, img in enumerate(images, 1):
            print(f"{idx}. {img['url']}")
            if img['alt']:
                print(f"   Alt: {img['alt']}")
            print()
        
        # Ask if user wants to download
        download = input("Download these images? (y/n): ").lower()
        if download == 'y':
            download_images(images)
            print("\nDownload complete!")
    else:
        print("No images found. DuckDuckGo might be blocking the request.")
        print("Try using the Selenium version for better reliability.")


if __name__ == "__main__":
    main()
