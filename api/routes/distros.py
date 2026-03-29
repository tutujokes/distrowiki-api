"""
Rotas da API para distribuições Linux.
"""

import logging
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Header

from ..models.distro import DistroMetadata, DistroListResponse
from ..services.google_sheets_service import GoogleSheetsService
from ..cache.cache_manager import CacheManager

logger = logging.getLogger(__name__)
router = APIRouter()


# Dependência para CacheManager
def get_cache_manager() -> CacheManager:
    """Retorna instância do CacheManager."""
    return CacheManager()


@router.get("/distros", response_model=DistroListResponse)
async def get_distros(
    page: int = Query(1, ge=1, description="Número da página"),
    page_size: int = Query(20, ge=1, le=100, description="Itens por página"),
    family: Optional[str] = Query(None, description="Filtrar por família"),
    sort_by: Optional[str] = Query("name", description="Campo para ordenação"),
    order: Optional[str] = Query("asc", description="Ordem: asc ou desc"),
    force_refresh: bool = Query(False, description="Forçar atualização do cache"),
    cache_manager: CacheManager = Depends(get_cache_manager),
):
    """
    Retorna lista paginada de distribuições Linux.
    
    - **page**: Número da página (padrão: 1)
    - **page_size**: Tamanho da página (padrão: 20, máx: 100)
    - **family**: Filtrar por família (ex: Debian, Arch)
    - **sort_by**: Campo para ordenação (name, rating, etc)
    - **order**: asc ou desc
    - **force_refresh**: Se true, ignora cache e busca dados atualizados
    """
    try:
        # Verificar se tem cache válido
        cached_data = None if force_refresh else cache_manager.get_distros_cache()
        
        if cached_data:
            logger.info("Usando dados do cache")
            distros = cached_data
        else:
            logger.info("Buscando dados do Google Sheets...")
            sheets_service = GoogleSheetsService()
            distros = await sheets_service.fetch_all_distros()
            await sheets_service.close()
            
            # Salvar no cache
            cache_manager.save_distros_cache(distros)
            logger.info(f"Cache atualizado com {len(distros)} distros")
        
        # Filtrar por família se especificado
        if family:
            distros = [d for d in distros if d.family.lower() == family.lower()]
        
        # Ordenar
        reverse = (order.lower() == "desc")
        if sort_by == "name":
            distros.sort(key=lambda x: x.name.lower(), reverse=reverse)
        elif sort_by == "rating":
            distros.sort(key=lambda x: x.rating or 0, reverse=reverse)
        elif sort_by == "family":
            distros.sort(key=lambda x: x.family.lower(), reverse=reverse)
        
        # Paginar
        total = len(distros)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = distros[start:end]
        
        return DistroListResponse(
            distros=paginated,
            total=total,
            page=page,
            page_size=page_size,
            cache_timestamp=None
        )
        
    except Exception as e:
        logger.error(f"Erro ao buscar distros: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/distros/{distro_id}", response_model=DistroMetadata)
async def get_distro_by_id(
    distro_id: str,
    force_refresh: bool = Query(False, description="Forçar atualização do cache"),
    cache_manager: CacheManager = Depends(get_cache_manager),
):
    """
    Retorna detalhes de uma distribuição específica pelo ID.
    
    - **distro_id**: ID único da distribuição (ex: ubuntu, fedora)
    - **force_refresh**: Se true, ignora cache
    """
    try:
        # Tentar lookup direto por ID (O(1) no Redis)
        if not force_refresh:
            distro = cache_manager.get_distro_by_id(distro_id)
            if distro:
                return distro
        
        # Fallback: carregar todos e salvar no cache
        cached_data = None if force_refresh else cache_manager.get_distros_cache()
        
        if cached_data:
            distros = cached_data
        else:
            sheets_service = GoogleSheetsService()
            distros = await sheets_service.fetch_all_distros()
            await sheets_service.close()
            cache_manager.save_distros_cache(distros)
        
        # Buscar distro pelo ID
        distro = next((d for d in distros if d.id == distro_id), None)
        
        if not distro:
            raise HTTPException(
                status_code=404,
                detail=f"Distribuição '{distro_id}' não encontrada"
            )
        
        return distro
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar distro {distro_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/refresh", 
    summary="Força atualização do cache de distros",
    response_model=Dict[str, Any]
)
async def refresh_distros_cache(
    api_key: str = Header(..., alias="X-API-Key", description="API Key para autenticação"),
    cache_manager: CacheManager = Depends(get_cache_manager)
):
    """
    Remove o cache de distros forçando nova busca nos próximos requests.
    
    Requer autenticação via API Key no header X-API-Key.
    
    **Uso:**
    ```
    curl -X POST 'http://localhost:8000/cache/refresh' \\
      -H 'X-API-Key: YOUR_API_KEY'
    ```
    """
    # Verificar API Key
    expected_key = os.getenv("API_KEY")
    if not expected_key or api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="API Key inválida ou ausente. Use header X-API-Key."
        )
    
    try:
        cache_manager.clear_cache()

        return {
            "success": True,
            "message": "Comando de limpeza de cache enviado com sucesso",
            "timestamp": datetime.utcnow().isoformat(),
            "next_request": "Próximo GET /distros irá buscar dados atualizados"
        }

    except Exception as e:
        logger.error(f"Erro ao remover cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/distros/trending", summary="Distros em alta")
async def get_trending_distros(
    cache_manager: CacheManager = Depends(get_cache_manager),
):
    """
    Retorna distros em alta: top 10 por ranking + releases recentes (últimos 60 dias).
    
    Ideal para seções dinâmicas de 'Em Alta' no frontend.
    """
    try:
        distros = cache_manager.get_distros_cache()
        
        if not distros:
            sheets_service = GoogleSheetsService()
            distros = await sheets_service.fetch_all_distros()
            await sheets_service.close()
            cache_manager.save_distros_cache(distros)
        
        # Top 10 por ranking de popularidade
        ranked = [d for d in distros if d.ranking and d.ranking > 0]
        ranked.sort(key=lambda x: x.ranking or 999)
        top_popular = ranked[:10]
        
        # Releases recentes (últimos 60 dias)
        now = datetime.utcnow()
        recent_releases = []
        for d in distros:
            if d.latest_release_date:
                try:
                    release_date = datetime.fromisoformat(
                        d.latest_release_date.replace("Z", "+00:00").replace("+00:00", "")
                    )
                    days_ago = (now - release_date).days
                    if 0 <= days_ago <= 60:
                        recent_releases.append(d)
                except (ValueError, TypeError):
                    pass
        
        recent_releases.sort(
            key=lambda x: x.latest_release_date or "", reverse=True
        )
        
        return {
            "popular": [d.dict() for d in top_popular],
            "recent_releases": [d.dict() for d in recent_releases[:10]],
            "total_distros": len(distros),
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar trending: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))