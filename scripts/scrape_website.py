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
    
    def clean_text(self, soup, page_type='general'):
        """Remove unwanted elements"""
        
        # ✅ Fix: Pricing page pe nav/footer remove karo
        # but pricing table mat hatao
        if page_type == 'pricing':
            # Sirf script aur style hatao
            for tag in soup(['script', 'style']):
                tag.decompose()
        else:
            for tag in soup(['script', 'style', 'nav', 'footer']):
                tag.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        text = ' '.join(text.split())
        return text
    
    def get_meta_description(self, soup):
        meta = soup.find('meta', attrs={'name': 'description'})
        return meta['content'] if meta and meta.get('content') else ''
    
    def get_page_type(self, url):
        """URL se page type detect karo"""
        if '/pricing' in url:
            return 'pricing'
        elif '/features' in url:
            return 'features'
        elif '/modules' in url:
            return 'modules'
        elif '/about' in url:
            return 'about'
        elif '/contact' in url:
            return 'contact'
        elif '/security' in url:
            return 'security'
        elif '/reviews' in url:
            return 'reviews'
        elif '/blog' in url:
            return 'blog'
        elif '/privacy' in url.lower():
            return 'legal'
        elif '/terms' in url.lower():
            return 'legal'
        elif '/refund' in url.lower():
            return 'legal'
        elif '/updates' in url:
            return 'updates'
        else:
            return 'general'
    
    def scrape_page(self, url):
        page_type = self.get_page_type(url)
        print(f"📄 [{page_type.upper()}] Scraping: {url}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                pg = browser.new_page()
                
                # ✅ Longer timeout pricing ke liye
                pg.goto(
                    url,
                    wait_until='networkidle',
                    timeout=45000
                )
                
                # ✅ Pricing page ke liye extra wait
                if page_type == 'pricing':
                    pg.wait_for_timeout(2000)
                
                content = pg.content()
                browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            
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
                'text_content': self.clean_text(soup, page_type),
                'scraped_at': datetime.now().isoformat(),
            }
            
            print(f"  ✅ {len(data['text_content'])} chars | "
                  f"H1: {len(data['headings']['h1'])} | "
                  f"H2: {len(data['headings']['h2'])}")
            
            return data
            
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            return None
    
    def scrape_all(self, urls_file='data/urls_to_scrape.txt'):
        print("🚀 Starting scrape...\n")
        
        with open(urls_file, 'r') as f:
            urls = [
                line.strip() for line in f
                if line.strip() and not line.startswith('#')
            ]
        
        print(f"📋 URLs to scrape: {len(urls)}\n")
        
        results = []
        failed = []
        
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] ", end='')
            result = self.scrape_page(url)
            
            if result:
                results.append(result)
            else:
                failed.append(url)
            
            time.sleep(2)
        
        # Save results
        output_file = (
            self.output_dir /
            f'scraped_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*50}")
        print(f"✅ Success: {len(results)}/{len(urls)}")
        if failed:
            print(f"❌ Failed: {len(failed)}")
            for url in failed:
                print(f"   - {url}")
        print(f"💾 Saved: {output_file}")
        
        return results


if __name__ == '__main__':
    scraper = SkolifyWebsiteScraper()
    scraper.scrape_all()