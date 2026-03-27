"""
Job de atualização diária do catálogo de distribuições.

Este script deve ser executado via cron serverless (ex: Vercel Cron)
para atualizar o cache de distribuições 1x por dia.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.services.distrowatch_scraper import fetch_ranking_list, get_distro_details
from api.cache.cache_manager import get_cache_manager
from api.models.distro import DistroMetadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def fetch_and_update_distros():
    """
    Busca dados atualizados de distribuições e atualiza o cache.
    
    Processo:
    1. Buscar ranking do DistroWatch (Last 1 month)
    2. Scraping completo de cada distribuição
    3. Atualizar cache JSON com TTL de 24h
    """
    start_time = datetime.utcnow()
    logger.info("=" * 60)
    logger.info("🔄 Iniciando job de atualização de distribuições")
    logger.info(f"⏰ Timestamp: {start_time.isoformat()}")
    logger.info("=" * 60)
    
    distrowatch_service = None  # Não mais necessário como classe
    cache_manager = get_cache_manager()
    
    try:
        # 1. Buscar ranking do DistroWatch
        logger.info("📥 Buscando ranking do DistroWatch (Last 1 month)...")
        ranking = await fetch_ranking_list()
        logger.info(f"✅ {len(ranking)} distribuições encontradas no ranking")
        
        # 2. Scraping completo de cada distribuição
        logger.info("� Realizando scraping detalhado de cada distribuição...")
        distros = []
        errors = 0
        
        for i, item in enumerate(ranking, 1):
            try:
                slug = item['slug']
                rank = item['rank']
                logger.info(f"  [{i}/{len(ranking)}] #{rank} {slug}...")
                
                # Buscar dados da distro (Scrapling com fallback legado)
                scraped_data = await get_distro_details(slug)
                
                if scraped_data:
                    # Converter retorno do scraper para DistroMetadata
                    # (Estamos mantendo a estrutura compatível)
                    distro = DistroMetadata(
                        id=slug,
                        name=scraped_data.get("nome", slug), # Fallback se não vier nome
                        description=scraped_data.get("descricao", ""),
                        architecture=scraped_data.get("architecture"),
                        popularity_rank=scraped_data.get("popularity_rank"),
                        release_type=scraped_data.get("release_type"),
                        init_system=scraped_data.get("init_system"),
                        file_systems=scraped_data.get("file_systems"),
                        latest_release_date=scraped_data.get("latest_release"),
                        ranking=rank
                    )
                
                if distro:
                    # Garantir que o ranking esteja atualizado
                    if not distro.ranking:
                        distro.ranking = rank
                    distros.append(distro)
                    logger.info(f"  ✓ {distro.name} obtida com sucesso")
                else:
                    logger.warning(f"  ✗ Falhou ao obter {slug}")
                    errors += 1
                
                # Rate limiting: 1.5s entre requests
                if i < len(ranking):
                    await asyncio.sleep(1.5)
                    
            except Exception as e:
                logger.warning(f"  ⚠️  Erro ao processar {item.get('slug', '?')}: {e}")
                errors += 1
        
        logger.info(f"✅ Scraping concluído: {len(distros)} distros, {errors} erros")
        
        # 3. Atualizar cache
        logger.info("💾 Atualizando cache...")
        success = cache_manager.set_distros_cache(distros)
        
        if success:
            logger.info("✅ Cache atualizado com sucesso")
        else:
            logger.error("❌ Erro ao atualizar cache")
            raise Exception("Falha ao salvar cache")
        
        # 4. Estatísticas finais
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info("=" * 60)
        logger.info("📊 ESTATÍSTICAS DA ATUALIZAÇÃO")
        logger.info("=" * 60)
        logger.info(f"  Total de distribuições: {len(distros)}")
        logger.info(f"  Erros encontrados: {errors}")
        logger.info(f"  Duração: {duration:.2f}s ({duration/60:.1f} min)")
        logger.info(f"  Timestamp início: {start_time.isoformat()}")
        logger.info(f"  Timestamp fim: {end_time.isoformat()}")
        
        # Estatísticas por família
        from collections import Counter
        family_counts = Counter(d.family.value for d in distros)
        logger.info("  Distribuição por família:")
        for family, count in family_counts.most_common():
            logger.info(f"    - {family}: {count}")
        
        # Top 10 no ranking
        logger.info("  Top 10 distribuições:")
        top_10 = sorted([d for d in distros if d.ranking], key=lambda x: x.ranking)[:10]
        for distro in top_10:
            logger.info(f"    #{distro.ranking:2d} - {distro.name} ({distro.family.value})")
        
        logger.info("=" * 60)
        logger.info("✅ Job concluído com sucesso!")
        logger.info("=" * 60)
        
        return {
            "success": True,
            "distros_count": len(distros),
            "errors": errors,
            "duration_seconds": duration,
            "timestamp": end_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Erro fatal no job de atualização: {e}", exc_info=True)
        raise
        
    finally:
        # await distrowatch_service.close() # Facade gerencia o tempo de vida


async def main():
    """Função principal do job."""
    try:
        result = await fetch_and_update_distros()
        return result
    except Exception as e:
        logger.error(f"Job falhou: {e}")
        sys.exit(1)


# Para execução via Vercel Cron ou similar
def handler(request=None):
    """
    Handler para Vercel Cron.
    
    Args:
        request: Request object (opcional).
    
    Returns:
        Response dict.
    """
    try:
        result = asyncio.run(main())
        return {
            "statusCode": 200,
            "body": result
        }
    except Exception as e:
        logger.error(f"Handler falhou: {e}")
        return {
            "statusCode": 500,
            "body": {
                "success": False,
                "error": str(e)
            }
        }


# Para execução direta via script
if __name__ == "__main__":
    print("\n🚀 DistroWiki - Job de Atualização de Distribuições\n")
    
    try:
        result = asyncio.run(main())
        print("\n✅ Job executado com sucesso!")
        print(f"📊 Resultado: {result}\n")
    except KeyboardInterrupt:
        print("\n⚠️  Job interrompido pelo usuário\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro ao executar job: {e}\n")
        sys.exit(1)
