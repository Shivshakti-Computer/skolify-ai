# scripts/build_on_startup.py
# Render deploy pe ChromaDB automatically rebuild karta hai

import os
from pathlib import Path

def should_rebuild() -> bool:
    """Check karo rebuild zaroori hai ya nahi"""
    chroma_path = Path("data/chroma_db")
    
    # Agar chroma_db exist nahi karta ya empty hai
    if not chroma_path.exists():
        return True
    
    # sqlite file check karo
    sqlite_file = chroma_path / "chroma.sqlite3"
    if not sqlite_file.exists():
        return True
    
    # File 1KB se chhoti hai matlab empty hai
    if sqlite_file.stat().st_size < 1024:
        return True
    
    return False

def rebuild_knowledge_base():
    """Full rebuild pipeline"""
    print("🔄 ChromaDB not found — rebuilding from website...")
    
    # ── Step 1: Scrape ──
    print("\n📡 Step 1: Scraping website...")
    from scripts.scrape_website import SkolifyWebsiteScraper
    scraper = SkolifyWebsiteScraper()
    results = scraper.scrape_all()
    
    if not results:
        print("❌ Scraping failed!")
        return False
    
    print(f"✅ Scraped {len(results)} pages")
    
    # ── Step 2: Process ──
    print("\n⚙️  Step 2: Processing data...")
    from scripts.process_data import DataProcessor
    processor = DataProcessor()
    
    raw_files = list(Path("data/raw").glob("scraped_data_*.json"))
    if not raw_files:
        print("❌ No raw data found!")
        return False
    
    latest = max(raw_files, key=lambda p: p.stat().st_mtime)
    chunks = processor.process_scraped_data(latest)
    print(f"✅ Created {len(chunks)} chunks")
    
    # ── Step 3: Build Vector DB ──
    print("\n💾 Step 3: Building ChromaDB...")
    from scripts.build_vector_db import VectorDBBuilder
    builder = VectorDBBuilder()
    
    chunks_files = list(Path("data/processed").glob("chunks_*.json"))
    latest_chunks = max(chunks_files, key=lambda p: p.stat().st_mtime)
    collection = builder.build_database(latest_chunks)
    
    print(f"✅ ChromaDB built: {collection.count()} documents")
    return True

def run():
    """Main entry point"""
    if should_rebuild():
        success = rebuild_knowledge_base()
        if not success:
            print("⚠️  Rebuild failed — API will use fallback responses")
    else:
        # Count documents
        try:
            import chromadb
            from chromadb.config import Settings as CS
            client = chromadb.PersistentClient(
                path="data/chroma_db",
                settings=CS(anonymized_telemetry=False)
            )
            col = client.get_collection("skolify_public_kb")
            print(f"✅ ChromaDB exists: {col.count()} documents — skip rebuild")
        except Exception:
            print("⚠️  ChromaDB check failed — will rebuild")
            rebuild_knowledge_base()

if __name__ == "__main__":
    run()