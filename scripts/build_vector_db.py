from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import json
from pathlib import Path
import sys
import os

# ✅ Fix: Project root add karo
sys.path.insert(0, str(Path(__file__).parent.parent))

class VectorDBBuilder:
    def __init__(self):
        # ✅ Fix 1: Config se model lo
        from api.config import settings
        
        print(f"🤖 Loading embedding model: {settings.EMBEDDING_MODEL}")
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        self.collection_name = settings.VECTOR_COLLECTION_NAME
        print(f"✅ Model loaded")
        
        print("💾 Initializing ChromaDB...")
        self.client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DB_PATH),
            settings=Settings(anonymized_telemetry=False)
        )
        print("✅ ChromaDB ready")
    
    def build_database(self, chunks_file):
        print(f"\n📂 Loading: {chunks_file}")
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        print(f"📊 Total chunks: {len(chunks)}")
        
        # ✅ Fix 2: Collection reset
        try:
            self.client.delete_collection(self.collection_name)
            print("🗑️  Old collection deleted")
        except:
            pass
        
        collection = self.client.create_collection(
            name=self.collection_name,
            metadata={
                "description": "Skolify public website knowledge",
                "embedding_model": str(self.model.get_sentence_embedding_dimension()),
                "hnsw:space": "cosine",  # ✅ ADD THIS
            }
        )
        
        print("\n🔄 Generating embeddings...")
        
        texts = [chunk['text'] for chunk in chunks]
        metadatas = [chunk['metadata'] for chunk in chunks]
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        
        batch_size = 32
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        for i in range(0, len(texts), batch_size):
            batch_end = min(i + batch_size, len(texts))
            batch_num = (i // batch_size) + 1
            
            print(f"  Batch {batch_num}/{total_batches}...", end=' ')
            
            batch_texts = texts[i:batch_end]
            batch_embeddings = self.model.encode(
                batch_texts,
                show_progress_bar=False
            )
            
            collection.add(
                embeddings=batch_embeddings.tolist(),
                documents=batch_texts,
                ids=ids[i:batch_end],
                metadatas=metadatas[i:batch_end]
            )
            print("✓")
        
        print(f"\n✅ Vector DB built!")
        print(f"📊 Total documents: {collection.count()}")
        return collection
    
    def test_search(self, collection, query="What is Skolify?"):
        print(f"\n🔍 Testing: '{query}'")
        
        query_embedding = self.model.encode([query])[0]
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=3
        )
        
        print("📋 Top 3 results:")
        for i, (doc, meta) in enumerate(
            zip(results['documents'][0], results['metadatas'][0]), 1
        ):
            print(f"\n[{i}] Page: {meta.get('url', 'unknown')}")
            print(f"    Type: {meta.get('page_type', 'unknown')}")
            print(f"    Text: {doc[:200]}...")
        
        return results


if __name__ == '__main__':
    builder = VectorDBBuilder()
    
    chunks_files = list(Path('data/processed').glob('chunks_*.json'))
    if not chunks_files:
        print("❌ No chunks found! Run process_data.py first")
        exit(1)
    
    latest_chunks = max(chunks_files, key=lambda p: p.stat().st_mtime)
    collection = builder.build_database(latest_chunks)
    
    # ✅ Pricing specific tests
    print("\n" + "="*50)
    print("PRICING TESTS")
    print("="*50)
    builder.test_search(collection, "Skolify pricing plans")
    builder.test_search(collection, "How much does Skolify cost?")
    builder.test_search(collection, "₹499 starter plan features")
    builder.test_search(collection, "Free trial available?")