#!/usr/bin/env python3
"""
Teste rápido do scraper com proxies.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from api.scraping.distrowatch_cloudscraper import DistroWatchCloudScraper

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    logger.info("🚀 Testando scraper com proxies...")
    
    # Criar scraper com proxies habilitados
    scraper = DistroWatchCloudScraper(use_proxies=True, delay=1)
    
    # Testar com apenas 3 distros
    logger.info("📋 Iniciando scraping de 3 distros para teste...")
    results = scraper.scrape_all(limit=3)
    
    logger.info(f"\n✅ Resultado final:")
    logger.info(f"  - Total: {results['total']} distros")
    logger.info(f"  - Scraped at: {results['scraped_at']}")
    
    if results['distros']:
        logger.info(f"\n📊 Primeira distro:")
        first = results['distros'][0]
        for key, value in first.items():
            logger.info(f"  - {key}: {value}")
    else:
        logger.warning("⚠️ Nenhuma distro foi extraída!")

if __name__ == "__main__":
    main()
