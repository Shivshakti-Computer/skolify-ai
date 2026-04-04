# scripts/build_vector_db.py

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import json
from pathlib import Path

class VectorDBBuilder:
    def __init__(self):
        print("🤖 Loading embedding model...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Model loaded (384 dimensions)")
        
        print("💾 Initializing ChromaDB...")
        self.client = chromadb.PersistentClient(
            path="data/chroma_db",
            settings=Settings(anonymized_telemetry=False)
        )
        print("✅ ChromaDB ready")
    
    def build_database(self, chunks_file):
        """Build vector database from chunks"""
        print(f"\n📂 Loading chunks from: {chunks_file}")
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        print(f"📊 Found {len(chunks)} chunks")
        
        # Create/reset collection
        try:
            self.client.delete_collection("skolify_public_kb")
        except:
            pass
        
        collection = self.client.create_collection(
            name="skolify_public_kb",
            metadata={"description": "Skolify public website knowledge"}
        )
        
        print("\n🔄 Generating embeddings...")
        
        # Prepare data
        texts = [chunk['text'] for chunk in chunks]
        metadatas = [chunk['metadata'] for chunk in chunks]
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        
        # Generate embeddings (batched for efficiency)
        batch_size = 32
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        for i in range(0, len(texts), batch_size):
            batch_end = min(i + batch_size, len(texts))
            batch_num = (i // batch_size) + 1
            
            print(f"  Batch {batch_num}/{total_batches}...", end=' ')
            
            batch_texts = texts[i:batch_end]
            batch_embeddings = self.model.encode(batch_texts, show_progress_bar=False)
            batch_ids = ids[i:batch_end]
            batch_metadatas = metadatas[i:batch_end]
            
            collection.add(
                embeddings=batch_embeddings.tolist(),
                documents=batch_texts,
                ids=batch_ids,
                metadatas=batch_metadatas
            )
            
            print("✓")
        
        print(f"\n✅ Vector database built successfully!")
        print(f"📊 Total documents: {collection.count()}")
        
        return collection
    
    def test_search(self, collection, query="What is Skolify?"):
        """Test the vector database"""
        print(f"\n🔍 Test search: '{query}'")
        
        query_embedding = self.model.encode([query])[0]
        
        results = collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=3
        )
        
        print("\n📋 Top 3 results:")
        for i, doc in enumerate(results['documents'][0], 1):
            print(f"\n--- Result {i} ---")
            print(doc[:300] + "...")
        
        return results

if __name__ == '__main__':
    builder = VectorDBBuilder()
    
    # Find latest chunks file
    chunks_files = list(Path('data/processed').glob('chunks_*.json'))
    latest_chunks = max(chunks_files, key=lambda p: p.stat().st_mtime)
    
    # Build database
    collection = builder.build_database(latest_chunks)
    
    # Test searches
    builder.test_search(collection, "What is Skolify?")
    builder.test_search(collection, "How much does it cost?")
    builder.test_search(collection, "What features are available?")