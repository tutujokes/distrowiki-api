"""
Script para popular os novos campos das distros via scraping do DistroWatch.

Executa o scraping de todas as distros e atualiza o Google Sheets.

Uso:
    python enrich_distrowatch.py [--limit N] [--update-sheet] [--use-static-data]
"""

import asyncio
import argparse
import logging
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega variáveis de ambiente do .env
from dotenv import load_dotenv
load_dotenv()

from api.services.distrowatch_scraper import DistroWatchScraper
from api.services.google_sheets_service import GoogleSheetsService
from api.services.static_distro_data import get_static_data, has_static_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Cache global de ID -> Nome
DISTRO_ID_TO_NAME = {}


async def get_all_distro_ids() -> list:
    """Busca todos os IDs de distros da planilha e popula o cache de nomes."""
    global DISTRO_ID_TO_NAME
    sheets = GoogleSheetsService()
    try:
        distros = await sheets.fetch_all_distros()
        # Popula o cache de id -> nome para usar na formatação
        DISTRO_ID_TO_NAME = {d.id: d.name for d in distros if d.id and d.name}
        return [d.id for d in distros if d.id]
    finally:
        await sheets.close()


async def scrape_all_distros(distro_ids: list, limit: int = None) -> list:
    """Faz scraping de todas as distros."""
    if limit:
        distro_ids = distro_ids[:limit]
    
    logger.info(f"Iniciando scraping de {len(distro_ids)} distros...")
    
    results = []
    
    try:
        from api.services.distrowatch_scraper import get_distro_details
        for i, distro_id in enumerate(distro_ids):
            logger.info(f"[{i+1}/{len(distro_ids)}] Scraping: {distro_id}")
            
            try:
                result = await get_distro_details(distro_id)
                results.append({
                    "distro_id": distro_id,
                    **result
                })
                
                # Log de sucesso com dados encontrados
                found_fields = [k for k, v in result.items() if v and k not in ["distro_id", "scraped_at", "error"]]
                if found_fields:
                    logger.info(f"  → Encontrado: {', '.join(found_fields)}")
                else:
                    logger.warning(f"  → Nenhum dado encontrado")
                    
            except Exception as e:
                logger.error(f"  → Erro: {e}")
                results.append({
                    "distro_id": distro_id,
                    "error": str(e)
                })
    except Exception as e:
        logger.error(f"Erro fatal no loop de scraping: {e}")
    
    return results


def format_results_for_sheet(results: list) -> list:
    """Formata resultados para atualização da planilha."""
    formatted = []
    
    for r in results:
        if "error" in r:
            continue
        
        distro_id = r.get("distro_id", "")
        # Busca o nome real da distro a partir do cache
        distro_name = DISTRO_ID_TO_NAME.get(distro_id, distro_id)
        
        # Só adiciona se tiver algum dado para atualizar
        has_data = any([
            r.get("architecture"),
            r.get("popularity_rank"),
            r.get("release_type"),
            r.get("init_system"),
            r.get("file_systems"),
        ])
        
        if has_data:
            formatted.append({
                "Name": distro_name,  # Usa o nome real para match na planilha
                "Architecture": ", ".join(r.get("architecture", [])) if r.get("architecture") else "",
                "Popularity Rank": str(r.get("popularity_rank", "")) if r.get("popularity_rank") else "",
                "Release Type": r.get("release_type", ""),
                "Init System": r.get("init_system", ""),
                "File Systems": ", ".join(r.get("file_systems", [])) if r.get("file_systems") else "",
            })
    
    return formatted


async def update_spreadsheet(data: list):
    """Atualiza o Google Sheets com os dados."""
    from enum import Enum
    
    class EnrichFields(Enum):
        ARCHITECTURE = "Architecture"
        POPULARITY_RANK = "Popularity Rank"
        RELEASE_TYPE = "Release Type"
        INIT_SYSTEM = "Init System"
        FILE_SYSTEMS = "File Systems"
    
    sheets = GoogleSheetsService()
    try:
        result = await sheets.update_enriched_data(data, list(EnrichFields))
        return result
    finally:
        await sheets.close()


def get_static_results(distro_ids: list) -> list:
    """Usa dados estáticos ao invés de scraping."""
    results = []
    for distro_id in distro_ids:
        static = get_static_data(distro_id)
        if static:
            results.append({
                "distro_id": distro_id,
                "popularity_rank": static.get("popularity_rank"),
                "init_system": static.get("init_system", ""),
                "file_systems": static.get("file_systems", []),
                "release_type": static.get("release_type", ""),
                "architecture": static.get("architecture", []),
            })
        else:
            results.append({
                "distro_id": distro_id,
                "error": "Sem dados estáticos"
            })
    return results


async def main():
    parser = argparse.ArgumentParser(description="Enriquece dados via DistroWatch")
    parser.add_argument("--limit", type=int, help="Limita número de distros")
    parser.add_argument("--distros", type=str, help="IDs das distros para scrapear, separados por vírgula (ex: alma,ubuntu)")
    parser.add_argument("--update-sheet", action="store_true", help="Atualiza Google Sheets")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o que seria feito")
    parser.add_argument("--use-static-data", action="store_true", help="Usa dados estáticos ao invés de scraping")
    args = parser.parse_args()
    
    logger.info("=== DistroWatch Enrichment Script ===")
    
    # Buscar IDs das distros
    logger.info("Buscando lista de distros...")
    distro_ids = await get_all_distro_ids()
    logger.info(f"Encontradas {len(distro_ids)} distros")
    
    if args.distros:
        specific_distros = [d.strip() for d in args.distros.split(",")]
        distro_ids = [d for d in distro_ids if d in specific_distros]
        logger.info(f"Filtrando para {len(distro_ids)} distros específicas: {', '.join(distro_ids)}")

    if args.dry_run:
        logger.info(f"Modo dry-run: mostrando primeiras {args.limit or 10} distros")
        for did in distro_ids[:(args.limit or 10)]:
            print(f"  - {did}")
        return
    
    # Aplicar limite
    if args.limit:
        distro_ids = distro_ids[:args.limit]
    
    # Obter dados (estáticos ou via scraping)
    if args.use_static_data:
        logger.info(f"Usando dados estáticos para {len(distro_ids)} distros...")
        results = get_static_results(distro_ids)
    else:
        logger.info(f"Iniciando scraping de {len(distro_ids)} distros...")
        results = await scrape_all_distros(distro_ids)
    
    # Estatísticas
    success = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]
    
    logger.info(f"\n=== Resultados ===")
    logger.info(f"Total: {len(results)}")
    logger.info(f"Sucesso: {len(success)}")
    logger.info(f"Erros: {len(errors)}")
    
    # Mostrar amostra de dados
    if success:
        logger.info(f"\nAmostra (primeira distro com dados):")
        sample = next((r for r in success if any(v for k, v in r.items() if k not in ["distro_id", "scraped_at"])), None)
        if sample:
            for k, v in sample.items():
                if v and k not in ["scraped_at"]:
                    print(f"  {k}: {v}")
    
    # Atualizar planilha
    if args.update_sheet and success:
        logger.info("\nAtualizando Google Sheets...")
        formatted = format_results_for_sheet(success)
        result = await update_spreadsheet(formatted)
        logger.info(f"Resultado: {result}")
    
    logger.info("\n=== Concluído ===")


if __name__ == "__main__":
    asyncio.run(main())
