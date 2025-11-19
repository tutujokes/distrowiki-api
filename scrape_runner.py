#!/usr/bin/env python3
"""
Script standalone para scraping via GitHub Actions
Roda diariamente e salva resultados em JSON usando CloudScraper
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

# Adiciona path para importar diretamente o scraper
sys.path.insert(0, str(Path(__file__).parent))

# Importa diretamente o módulo do scraper sem passar pelo __init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "distrowatch_cloudscraper",
    Path(__file__).parent / "api" / "scraping" / "distrowatch_cloudscraper.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DistroWatchCloudScraper = module.DistroWatchCloudScraper

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Executa scraping e salva resultados."""
    logger.info("🚀 Iniciando scraping do DistroWatch via GitHub Actions...")
    
    # Cria diretório de cache se não existir
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Configura scraper (CloudScraper é síncrono)
        scraper = DistroWatchCloudScraper(delay=2)
        
        # Executa scraping (top 100 distros)
        logger.info("🔍 Scraping top 100 distribuições...")
        results = scraper.scrape_all(limit=100)
        
        # Prepara dados
        data = {
            'scraped_at': datetime.now().isoformat(),
            'scraped_by': 'github-actions',
            'total': len(results),
            'distros': results,
            'metadata': {
                'source': 'distrowatch.com',
                'scraper': 'cloudscraper',
                'version': '3.0.0'
            }
        }
        
        # Salva JSON
        output_file = cache_dir / 'distros_scraped.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Scraping concluído!")
        logger.info(f"📊 Total de distros: {len(results)}")
        logger.info(f"💾 Salvo em: {output_file}")
        
        # Imprime resumo para GitHub Actions
        print(f"\n{'='*50}")
        print(f"🎉 SCRAPING CONCLUÍDO COM SUCESSO")
        print(f"{'='*50}")
        print(f"📅 Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🐧 Distros scraped: {len(results)}")
        print(f"💾 Arquivo: {output_file}")
        print(f"{'='*50}\n")
        
        # Imprime primeiras 5 distros
        if results:
            print("🔝 Top 5 Distros:")
            for i, distro in enumerate(results[:5], 1):
                print(f"  {i}. {distro.get('name', 'N/A')} (Rank: {distro.get('rank', 'N/A')})")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Erro durante scraping: {e}", exc_info=True)
        print(f"\n{'='*50}")
        print(f"❌ ERRO NO SCRAPING")
        print(f"{'='*50}")
        print(f"Erro: {str(e)}")
        print(f"{'='*50}\n")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
