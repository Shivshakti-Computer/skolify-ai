# api/dependencies.py

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings as ChromaSettings
from functools import lru_cache
from .config import settings

from typing import Dict, List
from datetime import datetime, timedelta
import json

# Global instances (loaded once)
_embedding_model = None
_chroma_client = None
_collection = None

@lru_cache()
def get_embedding_model():
    """Get or create embedding model (singleton)"""
    global _embedding_model
    
    if _embedding_model is None:
        print(f"🤖 Loading embedding model: {settings.EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        print("✅ Embedding model loaded")
    
    return _embedding_model

@lru_cache()
def get_chroma_client():
    """Get or create ChromaDB client (singleton)"""
    global _chroma_client
    
    if _chroma_client is None:
        print(f"💾 Connecting to ChromaDB at: {settings.CHROMA_DB_PATH}")
        _chroma_client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DB_PATH),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        print("✅ ChromaDB connected")
    
    return _chroma_client

def get_collection():
    """Get vector collection"""
    global _collection
    
    if _collection is None:
        client = get_chroma_client()
        try:
            _collection = client.get_collection(settings.VECTOR_COLLECTION_NAME)
            print(f"✅ Collection loaded: {_collection.count()} documents")
        except Exception as e:
            print(f"❌ Error loading collection: {e}")
            raise Exception(f"Vector database not found. Please run build_vector_db.py first.")
    
    return _collection

def reset_collection():
    """Reset collection (for updates)"""
    global _collection
    _collection = None


# In-memory conversation storage (for development)
# Production: Use Redis
_conversations: Dict[str, Dict] = {}

def get_conversation(conversation_id: str) -> Dict:
    """Get conversation history"""
    if conversation_id not in _conversations:
        _conversations[conversation_id] = {
            'messages': [],
            'context': {},
            'created_at': datetime.now().isoformat()
        }
    
    # Clean old conversations (older than 24 hours)
    cutoff = datetime.now() - timedelta(hours=24)
    for conv_id in list(_conversations.keys()):
        conv_time = datetime.fromisoformat(_conversations[conv_id]['created_at'])
        if conv_time < cutoff:
            del _conversations[conv_id]
    
    return _conversations[conversation_id]

def update_conversation(conversation_id: str, user_msg: str, ai_msg: str, context: Dict = None):
    """Update conversation history"""
    conv = get_conversation(conversation_id)
    
    conv['messages'].append({
        'user': user_msg,
        'ai': ai_msg,
        'timestamp': datetime.now().isoformat()
    })
    
    # Keep only last 10 messages
    if len(conv['messages']) > 10:
        conv['messages'] = conv['messages'][-10:]
    
    # Update context
    if context:
        conv['context'].update(context)