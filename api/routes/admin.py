# api/routes/admin.py

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..dependencies import (
    reset_collection,
    get_conv_store,
    get_collection,
    get_llm_manager,
)
from ..config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ════════════════════════════════════════════════
# AUTHENTICATION
# ════════════════════════════════════════════════

def verify_key(x_api_key: str = Header(...)):
    """Verify admin API key"""
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ════════════════════════════════════════════════
# UPDATE STATUS TRACKING
# ════════════════════════════════════════════════

_update_status = {
    "status": "idle",
    "step": None,
    "progress": 0,
    "started_at": None,
    "completed_at": None,
    "error": None,
}


async def run_update():
    """Background task to update knowledge base"""
    global _update_status
    try:
        _update_status.update({
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "error": None,
        })

        from scripts.scrape_website import SkolifyWebsiteScraper
        from scripts.process_data import DataProcessor
        from scripts.build_vector_db import VectorDBBuilder

        # Step 1: Scrape website
        _update_status["step"] = "Scraping website"
        _update_status["progress"] = 20
        scraper = SkolifyWebsiteScraper()
        scraper.scrape_all()

        # Step 2: Process data
        _update_status["step"] = "Processing data"
        _update_status["progress"] = 50
        processor = DataProcessor()
        raw_files = list(Path("data/raw").glob("scraped_data_*.json"))
        if not raw_files:
            raise Exception("No raw data files found")
        latest = max(raw_files, key=lambda p: p.stat().st_mtime)
        processor.process_scraped_data(latest)

        # Step 3: Build vector DB
        _update_status["step"] = "Building vector DB"
        _update_status["progress"] = 80
        builder = VectorDBBuilder()
        chunks = list(Path("data/processed").glob("chunks_*.json"))
        if not chunks:
            raise Exception("No processed chunks found")
        latest_chunks = max(chunks, key=lambda p: p.stat().st_mtime)
        builder.build_database(latest_chunks)
        
        # Reset collection in memory
        reset_collection()

        _update_status.update({
            "status": "completed",
            "step": "Done",
            "progress": 100,
            "completed_at": datetime.now().isoformat(),
        })

    except Exception as e:
        _update_status.update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now().isoformat(),
        })


# ════════════════════════════════════════════════
# ENDPOINTS
# ════════════════════════════════════════════════

@router.post("/update-knowledge")
async def update_knowledge(
    bg: BackgroundTasks,
    _: bool = Header(verify_key),
):
    """
    Trigger knowledge base update
    
    Scrapes website → Processes data → Rebuilds vector DB
    Runs in background
    """
    if _update_status["status"] == "running":
        return {
            "message": "Update already in progress",
            **_update_status
        }
    
    bg.add_task(run_update)
    return {
        "message": "Knowledge base update started",
        "status": "running"
    }


@router.get("/update-status")
async def update_status(_: bool = Header(verify_key)):
    """Check knowledge base update status"""
    return _update_status


@router.get("/stats")
async def stats(_: bool = Header(verify_key)):
    """
    Get comprehensive system statistics
    
    Returns:
    - Conversation stats
    - Vector DB stats
    - LLM provider status
    """
    stats_data: Dict[str, Any] = {}
    
    # Conversation storage stats
    try:
        conv_stats = get_conv_store().get_stats()
        stats_data["conversations"] = conv_stats
    except Exception as e:
        stats_data["conversations"] = {"error": str(e)}
    
    # Vector DB stats
    try:
        collection = get_collection()
        if collection:
            stats_data["vector_db"] = {
                "status": "healthy",
                "documents": collection.count(),
                "collection": settings.VECTOR_COLLECTION_NAME,
            }
        else:
            stats_data["vector_db"] = {
                "status": "unavailable",
                "documents": 0,
            }
    except Exception as e:
        stats_data["vector_db"] = {"error": str(e)}
    
    # ✅ LLM Provider stats (2025)
    try:
        llm = get_llm_manager()
        stats_data["llm_providers"] = {
            "configured": [
                name for name in llm.provider_order 
                if llm.providers[name].is_configured()
            ],
            "order": llm.provider_order,
            "all_providers": {
                name: llm.providers[name].is_configured()
                for name in llm.providers
            }
        }
    except Exception as e:
        stats_data["llm_providers"] = {"error": str(e)}
    
    # System info
    stats_data["system"] = {
        "environment": settings.APP_ENV,
        "storage_backend": settings.CONV_STORAGE,
        "embedding_model": settings.EMBEDDING_MODEL,
    }
    
    return stats_data


@router.post("/rebuild-vector-db")
async def rebuild_vector_db(
    bg: BackgroundTasks,
    _: bool = Header(verify_key),
):
    """
    Force rebuild vector database from existing processed data
    
    Useful when:
    - ChromaDB corrupted
    - Need to change embedding model
    - Testing vector search
    """
    async def rebuild():
        try:
            from scripts.build_vector_db import VectorDBBuilder
            
            chunks = list(Path("data/processed").glob("chunks_*.json"))
            if not chunks:
                raise Exception("No processed chunks found. Run update-knowledge first.")
            
            latest_chunks = max(chunks, key=lambda p: p.stat().st_mtime)
            
            builder = VectorDBBuilder()
            builder.build_database(latest_chunks)
            reset_collection()
            
        except Exception as e:
            print(f"❌ Vector DB rebuild error: {e}")
    
    bg.add_task(rebuild)
    return {"message": "Vector DB rebuild started"}


@router.get("/health")
async def health(_: bool = Header(verify_key)):
    """
    Detailed health check
    
    Returns component-level status
    """
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # Check vector DB
    try:
        col = get_collection()
        health_data["components"]["vector_db"] = {
            "status": "healthy" if col else "unavailable",
            "documents": col.count() if col else 0,
        }
    except Exception as e:
        health_data["components"]["vector_db"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check LLM providers
    try:
        llm = get_llm_manager()
        configured = [
            name for name in llm.provider_order 
            if llm.providers[name].is_configured()
        ]
        health_data["components"]["llm"] = {
            "status": "healthy" if configured else "degraded",
            "configured_providers": configured,
        }
    except Exception as e:
        health_data["components"]["llm"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check conversation storage
    try:
        store = get_conv_store()
        stats = store.get_stats()
        health_data["components"]["storage"] = {
            "status": "healthy",
            "backend": settings.CONV_STORAGE,
            "total_conversations": stats.get("total", 0),
        }
    except Exception as e:
        health_data["components"]["storage"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Overall status
    if any(
        c.get("status") == "error" 
        for c in health_data["components"].values()
    ):
        health_data["status"] = "degraded"
    
    return health_data


@router.delete("/clear-conversations")
async def clear_conversations(
    _: bool = Header(verify_key),
    confirm: bool = False,
):
    """
    ⚠️ DANGER: Clear all conversations
    
    Requires confirm=true query parameter
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Add ?confirm=true to confirm deletion"
        )
    
    try:
        store = get_conv_store()
        
        # SQLite
        if settings.CONV_STORAGE == "sqlite":
            import sqlite3
            conn = sqlite3.connect(settings.CONVERSATIONS_DB)
            deleted = conn.execute("DELETE FROM conversations").rowcount
            conn.commit()
            conn.close()
        
        # Turso (if implemented)
        elif settings.CONV_STORAGE == "turso":
            # Implement Turso deletion
            deleted = 0
        
        return {
            "message": "Conversations cleared",
            "deleted": deleted
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))