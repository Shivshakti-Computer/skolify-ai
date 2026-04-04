# api/routes/admin.py

from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ..dependencies import reset_collection, get_conv_store
from ..config import settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


def verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


_update_status = {
    "status": "idle",
    "step": None,
    "progress": 0,
    "started_at": None,
    "completed_at": None,
    "error": None,
}


async def run_update():
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

        _update_status["step"] = "Scraping website"
        _update_status["progress"] = 20
        scraper = SkolifyWebsiteScraper()
        scraper.scrape_all()

        _update_status["step"] = "Processing data"
        _update_status["progress"] = 50
        processor = DataProcessor()
        raw_files = list(Path("data/raw").glob("scraped_data_*.json"))
        latest = max(raw_files, key=lambda p: p.stat().st_mtime)
        processor.process_scraped_data(latest)

        _update_status["step"] = "Building vector DB"
        _update_status["progress"] = 80
        builder = VectorDBBuilder()
        chunks = list(Path("data/processed").glob("chunks_*.json"))
        latest_chunks = max(chunks, key=lambda p: p.stat().st_mtime)
        builder.build_database(latest_chunks)
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


@router.post("/update-knowledge")
async def update_knowledge(
    bg: BackgroundTasks,
    _: bool = Header(verify_key),
):
    if _update_status["status"] == "running":
        return {"message": "Already running", **_update_status}
    bg.add_task(run_update)
    return {"message": "Started", "status": "running"}


@router.get("/update-status")
async def update_status(_: bool = Header(verify_key)):
    return _update_status


@router.get("/stats")
async def stats(_: bool = Header(verify_key)):
    """Conversation statistics"""
    return get_conv_store().get_stats()