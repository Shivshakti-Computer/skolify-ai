# api/routes/admin.py

from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..dependencies import reset_collection
from ..config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ══════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════

class UpdateKnowledgeResponse(BaseModel):
    success: bool
    message: str
    started_at: str
    status: str

class UpdateStatus(BaseModel):
    status: str
    current_step: Optional[str] = None
    progress: Optional[int] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

# ══════════════════════════════════════════════════════════
# Global Status
# ══════════════════════════════════════════════════════════

update_status = {
    "status": "idle",
    "current_step": None,
    "progress": 0,
    "started_at": None,
    "completed_at": None,
    "error": None
}

# ══════════════════════════════════════════════════════════
# Helper Functions
# ══════════════════════════════════════════════════════════

def verify_admin_key(x_api_key: str = Header(...)):
    """Verify admin API key"""
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


async def run_knowledge_update():
    """Background task to update knowledge base"""
    global update_status
    
    try:
        update_status["status"] = "running"
        update_status["started_at"] = datetime.now().isoformat()
        update_status["error"] = None
        
        # Import here to avoid circular imports
        from scripts.scrape_website import SkolifyWebsiteScraper
        from scripts.process_data import DataProcessor
        from scripts.build_vector_db import VectorDBBuilder
        
        # Step 1: Scrape
        update_status["current_step"] = "Scraping website"
        update_status["progress"] = 20
        print("📡 Starting website scrape...")
        
        scraper = SkolifyWebsiteScraper()
        scraped_data = scraper.scrape_all()
        
        if not scraped_data:
            raise Exception("No data scraped")
        
        print(f"✅ Scraped {len(scraped_data)} pages")
        
        # Step 2: Process
        update_status["current_step"] = "Processing data"
        update_status["progress"] = 50
        print("🔄 Processing data...")
        
        processor = DataProcessor()
        raw_files = list(Path('data/raw').glob('scraped_data_*.json'))
        latest_file = max(raw_files, key=lambda p: p.stat().st_mtime)
        chunks = processor.process_scraped_data(latest_file)
        
        print(f"✅ Created {len(chunks)} chunks")
        
        # Step 3: Build vector DB
        update_status["current_step"] = "Building vector database"
        update_status["progress"] = 80
        print("💾 Building vector database...")
        
        builder = VectorDBBuilder()
        chunks_files = list(Path('data/processed').glob('chunks_*.json'))
        latest_chunks = max(chunks_files, key=lambda p: p.stat().st_mtime)
        collection = builder.build_database(latest_chunks)
        
        # Reset in-memory collection
        reset_collection()
        
        print("✅ Vector database updated")
        
        # Complete
        update_status["status"] = "completed"
        update_status["current_step"] = "Done"
        update_status["progress"] = 100
        update_status["completed_at"] = datetime.now().isoformat()
        
        print("🎉 Knowledge base update complete!")
        
    except Exception as e:
        update_status["status"] = "failed"
        update_status["error"] = str(e)
        update_status["completed_at"] = datetime.now().isoformat()
        print(f"❌ Update failed: {e}")


# ══════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════

@router.post("/update-knowledge", response_model=UpdateKnowledgeResponse)
async def update_knowledge(
    background_tasks: BackgroundTasks,
    _: bool = Header(verify_admin_key)
):
    """
    Trigger knowledge base update
    """
    global update_status
    
    if update_status["status"] == "running":
        return UpdateKnowledgeResponse(
            success=False,
            message="Update already in progress",
            started_at=update_status["started_at"],
            status=update_status["status"]
        )
    
    # Start background task
    background_tasks.add_task(run_knowledge_update)
    
    return UpdateKnowledgeResponse(
        success=True,
        message="Knowledge update started",
        started_at=datetime.now().isoformat(),
        status="running"
    )


@router.get("/update-status", response_model=UpdateStatus)
async def get_update_status(_: bool = Header(verify_admin_key)):
    """Get current update status"""
    return UpdateStatus(**update_status)