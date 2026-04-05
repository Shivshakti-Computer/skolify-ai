# scripts/build_on_startup.py
# Render pe sirf pre-scraped data se rebuild karta hai
# Playwright scraping nahi hoti production mein

from pathlib import Path


def should_rebuild() -> bool:
    """Check karo ChromaDB rebuild zaroori hai ya nahi"""
    chroma_path = Path("data/chroma_db")

    if not chroma_path.exists():
        return True

    sqlite_file = chroma_path / "chroma.sqlite3"
    if not sqlite_file.exists():
        return True

    # 1KB se chhota = empty
    if sqlite_file.stat().st_size < 1024:
        return True

    return False


def rebuild_from_existing_data() -> bool:
    print("🔄 Rebuilding ChromaDB from pre-scraped data...")

    chunks_files = list(Path("data/processed").glob("chunks_*.json"))

    if not chunks_files:
        print("❌ No processed chunks found!")
        return False

    # ✅ FIX: Filename se sort karo (YYYYMMDD_HHMMSS format)
    latest_chunks = max(chunks_files, key=lambda p: p.name)
    print(f"📂 Using: {latest_chunks.name}")

    try:
        from scripts.build_vector_db import VectorDBBuilder
        builder = VectorDBBuilder()
        collection = builder.build_database(latest_chunks)
        print(f"✅ ChromaDB rebuilt: {collection.count()} documents")
        return True
    except Exception as e:
        print(f"❌ ChromaDB build failed: {e}")
        return False

def run():
    """Main entry — startup pe call hota hai"""
    if should_rebuild():
        print("⚠️  ChromaDB missing — rebuilding...")
        success = rebuild_from_existing_data()
        if not success:
            print("⚠️  Rebuild failed — fallback responses only")
    else:
        try:
            import chromadb
            from chromadb.config import Settings as CS
            client = chromadb.PersistentClient(
                path="data/chroma_db",
                settings=CS(anonymized_telemetry=False)
            )
            col = client.get_collection("skolify_public_kb")
            print(f"✅ ChromaDB OK: {col.count()} documents")
        except Exception:
            print("⚠️  ChromaDB check failed — rebuilding...")
            rebuild_from_existing_data()


if __name__ == "__main__":
    run()