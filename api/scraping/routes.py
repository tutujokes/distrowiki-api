"""
Rotas para scraping manual do DistroWatch.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import json
from pathlib import Path
import logging
import httpx
import re
from bs4 import BeautifulSoup

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
    """Executa scraping do DistroWatch."""
    logger.info(f"🚀 Iniciando scraping de {limit} distros...")
    
    try:
        # 1. Obter lista de distros da página de ranking
        ranking_list = await scrape_ranking_page(limit)
        logger.info(f"📋 {len(ranking_list)} distros na lista")
        
        # 2. Scrape detalhes de cada distro
        distros = []
        for i, item in enumerate(ranking_list, 1):
            try:
                details = await scrape_distro_details(item['slug'], item['url'])
                if details:
                    distros.append(details)
                    logger.info(f"[{i}/{len(ranking_list)}] ✅ {item['slug']}")
            except Exception as e:
                logger.error(f"[{i}/{len(ranking_list)}] ❌ {item['slug']}: {e}")
        
        # 3. Salvar resultados
        cache_dir = Path("data/cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        result = {
            "scraped_at": datetime.utcnow().isoformat() + 'Z',
            "total": len(distros),
            "distros": distros,
            "metadata": {
                "version": "2.0.0",
                "source": "vercel_api",
                "limit_requested": limit,
                "success_rate": f"{len(distros)/len(ranking_list)*100:.1f}%"
            }
        }
        
        with open(cache_dir / "distros_scraped.json", 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Scraping concluído: {len(distros)}/{len(ranking_list)} distros")
        
    except Exception as e:
        logger.error(f"❌ Erro no scraping: {e}")
        raise


async def scrape_ranking_page(limit: int) -> List[Dict]:
    """Scrape página de ranking do DistroWatch."""
    url = "https://distrowatch.com/dwres.php?resource=popularity"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        distros = []
        
        # Encontrar tabela "Last 1 month"
        for th in soup.find_all('th', class_='Invert'):
            if 'Last 1 month' in th.get_text():
                table = th.find_parent('table')
                
                for row in table.find_all('tr'):
                    rank_cell = row.find('th', class_='phr1')
                    name_cell = row.find('td', class_='phr2')
                    
                    if rank_cell and name_cell:
                        rank = int(rank_cell.get_text(strip=True))
                        link = name_cell.find('a')
                        
                        if link:
                            name = link.get_text(strip=True)
                            href = link.get('href', '')
                            
                            # Extrair slug da URL
                            match = re.search(r'distribution=([^&]+)', href)
                            if match:
                                slug = match.group(1)
                                distros.append({
                                    'rank': rank,
                                    'name': name,
                                    'slug': slug,
                                    'url': f"https://distrowatch.com/table.php?distribution={slug}"
                                })
                        
                        if len(distros) >= limit:
                            break
                break
        
        return distros
    
    except Exception as e:
        logger.error(f"Erro ao scrape ranking: {e}")
        # Fallback: retornar lista básica
        return [
            {'rank': i, 'name': s.capitalize(), 'slug': s, 
             'url': f"https://distrowatch.com/table.php?distribution={s}"}
            for i, s in enumerate([
                "cachyos", "mxlinux", "linuxmint", "popos", "endeavouros",
                "manjaro", "ubuntu", "debian", "fedora", "opensuse"
            ][:limit], 1)
        ]


async def scrape_distro_details(slug: str, url: str) -> Optional[Dict]:
    """Scrape detalhes de uma distro."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Nome
        name = None
        h1 = soup.find('h1')
        if h1:
            name = h1.get_text(strip=True)
        
        # Categoria
        category = None
        for li in soup.find_all('li'):
            b = li.find('b')
            if b and 'Categoria' in b.get_text():
                cats = [a.get_text(strip=True) for a in li.find_all('a')]
                category = ', '.join(cats)
                break
        
        # Data de lançamento
        release_date = None
        for th in soup.find_all('th'):
            if 'Data de Lançamento' in th.get_text():
                row = th.find_parent('tr')
                date_td = row.find('td', class_='Date')
                if date_td:
                    date_str = date_td.get_text(strip=True)
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        release_date = date_obj.strftime('%d/%m/%Y')
                    except:
                        release_date = date_str
                break
        
        # Popularidade (4 semanas)
        popularity_rank = None
        popularity_hits = None
        for text_node in soup.find_all(string=re.compile(r'4 semanas')):
            full_text = text_node.parent.get_text()
            match = re.search(r'4 semanas:\s*(\d+)\s*\(([0-9,]+)\)', full_text)
            if match:
                popularity_rank = int(match.group(1))
                popularity_hits = int(match.group(2).replace(',', ''))
                break
        
        # Rating
        rating = None
        for a_tag in soup.find_all('a', href=lambda x: x and 'ratings' in x):
            if 'Average visitor rating' in a_tag.get_text():
                parent_b = a_tag.parent
                if parent_b:
                    for sibling in parent_b.next_siblings:
                        if hasattr(sibling, 'name') and sibling.name == 'b':
                            try:
                                rating = float(sibling.get_text(strip=True))
                            except:
                                pass
                            break
                break
        
        return {
            'id': slug,
            'name': name,
            'category': category,
            'release_date': release_date,
            'popularity_rank': popularity_rank,
            'popularity_hits': popularity_hits,
            'rating': rating,
            'url': url
        }
        
    except Exception as e:
        logger.error(f"Erro ao scrape {slug}: {e}")
        return None


@router.delete("/cache")
async def clear_cache():
    """Limpa cache de scraping."""
    cache_file = Path("data/cache/distros_scraped.json")
    
    if cache_file.exists():
        cache_file.unlink()
        return {"status": "cleared"}
    
    return {"status": "already_empty"}
