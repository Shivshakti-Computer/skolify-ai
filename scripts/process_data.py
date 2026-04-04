# scripts/process_data.py

import json
from pathlib import Path
from datetime import datetime

class DataProcessor:
    def __init__(self, chunk_size=500, chunk_overlap=50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text, metadata):
        """Split text into overlapping chunks"""
        words = text.split()
        chunks = []
        
        i = 0
        chunk_num = 0
        
        while i < len(words):
            # Get chunk
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            # Add metadata
            chunks.append({
                'text': chunk_text,
                'metadata': {
                    **metadata,
                    'chunk_id': chunk_num,
                    'chunk_size': len(chunk_words),
                }
            })
            
            # Move forward (with overlap)
            i += self.chunk_size - self.chunk_overlap
            chunk_num += 1
        
        return chunks
    
    def process_scraped_data(self, input_file):
        """Process scraped data into chunks"""
        print(f"📂 Loading: {input_file}")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        
        print(f"📄 Found {len(pages)} pages")
        
        all_chunks = []
        
        for page in pages:
            # Base metadata
            metadata = {
                'url': page['url'],
                'page_type': page['page_type'],
                'title': page['title'],
                'source': 'website',
            }
            
            # Chunk the main text
            chunks = self.chunk_text(page['text_content'], metadata)
            all_chunks.extend(chunks)
            
            print(f"  ✅ {page['url']}: {len(chunks)} chunks")
        
        print(f"\n✅ Total chunks created: {len(all_chunks)}")
        
        # Save processed data
        output_file = Path('data/processed') / f'chunks_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Saved to: {output_file}")
        
        return all_chunks

if __name__ == '__main__':
    processor = DataProcessor(chunk_size=500, chunk_overlap=50)
    
    # Find latest scraped file
    raw_files = list(Path('data/raw').glob('scraped_data_*.json'))
    latest_file = max(raw_files, key=lambda p: p.stat().st_mtime)
    
    chunks = processor.process_scraped_data(latest_file)