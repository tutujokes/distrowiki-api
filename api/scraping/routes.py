"""
Rotas para scraping manual do DistroWatch.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraping", tags=["Scraping"])


class ScrapeRequest(BaseModel):
    limit: int = 230
    force: bool = False


@router.get("/status")
async def get_scraping_status():
    """Retorna status do último scraping."""
    cache_file = Path("data/cache/distros_scraped.json")
    
    if not cache_file.exists():
        return {
            "status": "no_data",
            "message": "Nenhum scraping foi realizado ainda"
        }
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return {
        "status": "available",
        "scraped_at": data.get('scraped_at'),
        "total": data.get('total', 0)
    }


@router.get("/data")
async def get_scraped_data(skip: int = 0, limit: int = 100):
    """Retorna dados do scraping com paginação."""
    cache_file = Path("data/cache/distros_scraped.json")
    
    if not cache_file.exists():
        raise HTTPException(status_code=404, detail="Nenhum dado disponível")
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    distros = data.get('distros', [])
    
    return {
        "total": len(distros),
        "scraped_at": data.get('scraped_at'),
        "distros": distros[skip:skip + limit]
    }


@router.post("/trigger")
async def trigger_scraping(background_tasks: BackgroundTasks, request: ScrapeRequest = ScrapeRequest()):
    """Dispara scraping manual."""
    background_tasks.add_task(execute_scraping, request.limit)
    
    return {
        "status": "started",
        "message": f"Scraping de {request.limit} distros iniciado",
        "started_at": datetime.utcnow().isoformat() + 'Z'
    }


async def execute_scraping(limit: int):
    """Executa scraping (TODO: implementar lógica)."""
    logger.info(f"Scraping de {limit} distros...")
    
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    result = {
        "scraped_at": datetime.utcnow().isoformat() + 'Z',
        "total": 0,
        "distros": [],
        "metadata": {"version": "2.0.0", "source": "vercel"}
    }
    
    with open(cache_dir / "distros_scraped.json", 'w') as f:
        json.dump(result, f, indent=2)


@router.delete("/cache")
async def clear_cache():
    """Limpa cache de scraping."""
    cache_file = Path("data/cache/distros_scraped.json")
    
    if cache_file.exists():
        cache_file.unlink()
        return {"status": "cleared"}
    
    return {"status": "already_empty"}
