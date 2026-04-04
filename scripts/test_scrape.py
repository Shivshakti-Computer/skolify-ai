# scripts/test_scrape.py

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json

def scrape_single_page(url):
    """Test scraping on a single page"""
    print(f"🔍 Scraping: {url}")
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Go to URL
        page.goto(url, wait_until='networkidle')
        
        # Get HTML content
        content = page.content()
        browser.close()
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # Extract data
        data = {
            'url': url,
            'title': soup.title.string if soup.title else '',
            'text': soup.get_text(separator=' ', strip=True),
            'headings': [h.get_text(strip=True) for h in soup.find_all(['h1', 'h2', 'h3'])],
        }
        
        return data

if __name__ == '__main__':
    # Test on homepage first
    result = scrape_single_page('https://skolify.in/')
    
    print(f"\n✅ Title: {result['title']}")
    print(f"✅ Headings found: {len(result['headings'])}")
    print(f"✅ Text length: {len(result['text'])} characters")
    print(f"\n📄 First 500 characters:\n{result['text'][:500]}")
    
    # Save to file
    with open('data/raw/homepage_test.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print("\n💾 Saved to data/raw/homepage_test.json")