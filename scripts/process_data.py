import json
from pathlib import Path
from datetime import datetime


class DataProcessor:
    def __init__(self, chunk_size=400, chunk_overlap=80):
        # ✅ Fix: Smaller chunks = better precision
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text, metadata):
        words = text.split()
        chunks = []
        i = 0
        chunk_num = 0
        
        while i < len(words):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append({
                'text': chunk_text,
                'metadata': {
                    **metadata,
                    'chunk_id': chunk_num,
                    'chunk_size': len(chunk_words),
                }
            })
            
            i += self.chunk_size - self.chunk_overlap
            chunk_num += 1
        
        return chunks
    
    def process_scraped_data(self, input_file):
        print(f"📂 Loading: {input_file}")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        
        print(f"📄 Found {len(pages)} pages\n")
        
        all_chunks = []
        
        for page in pages:
            url = page['url']
            page_type = page['page_type']
            
            print(f"Processing: {url}")
            
            metadata = {
                'url': url,
                'page_type': page_type,
                'title': page['title'],
                'source': 'website',
            }
            
            # ✅ Fix 1: Headings ko text ke saath combine karo
            headings_text = ""
            if page.get('headings'):
                h1 = ' | '.join(page['headings'].get('h1', []))
                h2 = ' | '.join(page['headings'].get('h2', []))
                h3 = ' | '.join(page['headings'].get('h3', []))
                headings_text = f"Page Headings: {h1} {h2} {h3}. "
            
            # ✅ Fix 2: Pricing page special handling
            if page_type == 'pricing':
                full_text = (
                    f"PRICING INFORMATION for Skolify. "
                    f"{headings_text}"
                    f"{page['text_content']}"
                )
            else:
                full_text = f"{headings_text}{page['text_content']}"
            
            # Chunk karo
            chunks = self.chunk_text(full_text, metadata)
            all_chunks.extend(chunks)
            
            print(f"  ✅ {len(chunks)} chunks created")
        
        print(f"\n✅ Total chunks: {len(all_chunks)}")
        
        # Save
        output_dir = Path('data/processed')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f'chunks_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved: {output_file}")
        return all_chunks


if __name__ == '__main__':
    processor = DataProcessor(chunk_size=400, chunk_overlap=80)
    
    raw_files = list(Path('data/raw').glob('scraped_data_*.json'))
    if not raw_files:
        print("❌ No scraped data! Run scrape_website.py first")
        exit(1)
    
    latest_file = max(raw_files, key=lambda p: p.stat().st_mtime)
    chunks = processor.process_scraped_data(latest_file)