# scripts/scrape_website.py

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
from pathlib import Path
from datetime import datetime
import time

class SkolifyWebsiteScraper:
    def __init__(self):
        self.output_dir = Path('data/raw')
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def clean_text(self, soup):
        """Remove unwanted elements"""
        # Remove script, style tags
        for tag in soup(['script', 'style', 'nav', 'footer']):
            tag.decompose()
        
        # Get clean text
        text = soup.get_text(separator=' ', strip=True)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    def scrape_page(self, url, page_type='general'):
        """Scrape a single page with metadata"""
        print(f"📄 Scraping: {url}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle', timeout=30000)
                
                content = page.content()
                browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract structured data
            data = {
                'url': url,
                'page_type': page_type,
                'title': soup.title.string if soup.title else '',
                'meta_description': self.get_meta_description(soup),
                'headings': {
                    'h1': [h.get_text(strip=True) for h in soup.find_all('h1')],
                    'h2': [h.get_text(strip=True) for h in soup.find_all('h2')],
                    'h3': [h.get_text(strip=True) for h in soup.find_all('h3')],
                },
                'text_content': self.clean_text(soup),
                'scraped_at': datetime.now().isoformat(),
            }
            
            print(f"  ✅ Success - {len(data['text_content'])} chars")
            return data
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return None
    
    def get_meta_description(self, soup):
        """Extract meta description"""
        meta = soup.find('meta', attrs={'name': 'description'})
        return meta['content'] if meta else ''
    
    def scrape_all(self, urls_file='data/urls_to_scrape.txt'):
        """Scrape all URLs from file"""
        print("🚀 Starting bulk scrape...\n")
        
        # Read URLs
        urls = []
        with open(urls_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
        
        print(f"📋 Found {len(urls)} URLs to scrape\n")
        
        # Scrape each
        results = []
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] ", end='')
            
            # Determine page type from URL
            if '/pricing' in url:
                page_type = 'pricing'
            elif '/features' in url:
                page_type = 'features'
            elif '/blog' in url:
                page_type = 'blog'
            elif '/docs' in url:
                page_type = 'docs'
            else:
                page_type = 'general'
            
            result = self.scrape_page(url, page_type)
            
            if result:
                results.append(result)
            
            # Be nice to server
            time.sleep(2)
        
        # Save all results
        output_file = self.output_dir / f'scraped_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Scraping complete!")
        print(f"📊 Successfully scraped: {len(results)}/{len(urls)} pages")
        print(f"💾 Saved to: {output_file}")
        
        return results

if __name__ == '__main__':
    scraper = SkolifyWebsiteScraper()
    results = scraper.scrape_all()