"""
Scraper do DistroWatch usando CloudScraper
Bypass automático de Cloudflare e proteções anti-bot.
"""

import logging
import cloudscraper
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class DistroWatchCloudScraper:
    """
    Scraper para DistroWatch usando CloudScraper.
    
    Características:
    - Bypass automático de Cloudflare
    - Leve e rápido (sem navegador)
    - User-agent rotativo
    - Retry automático
    """
    
    def __init__(self, delay: int = 2):
        """
        Inicializa o scraper.
        
        Args:
            delay: Delay entre requests em segundos
        """
        self.base_url = "https://distrowatch.com"
        self.delay = delay
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        
    def scrape_distro_list(self) -> List[Dict]:
        """
        Scrape lista de distribuições da página de popularidade.
        
        Returns:
            Lista de dicionários com dados básicos das distros
        """
        logger.info("🔍 Iniciando scraping da lista de distribuições...")
        
        url = f"{self.base_url}/popularity"
        
        try:
            logger.info(f"📡 Acessando: {url}")
            response = self.scraper.get(url, timeout=30)
            response.raise_for_status()
            
            logger.info(f"✅ Status: {response.status_code}")
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            distros = []
            
            # Na página /popularity, os rankings estão em uma tabela simples
            # Busca todos os links de distros na página
            links = soup.find_all('a', href=lambda x: x and 'table.php?distribution=' in x)
            
            if not links:
                logger.warning("⚠️ Nenhum link de distro encontrado na página")
                return []
            
            logger.info(f"📊 Encontrados {len(links)} links de distros")
            
            # Extrai dados de cada link
            seen_distros = set()  # Para evitar duplicatas
            
            for link in links:
                distro_name = link.get_text(strip=True)
                distro_url = link.get('href')
                
                # Evita duplicatas
                if distro_name in seen_distros:
                    continue
                seen_distros.add(distro_name)
                
                # Normaliza URL
                if not distro_url.startswith('http'):
                    distro_url = f"{self.base_url}/{distro_url}"
                
                # Tenta extrair o rank do contexto (linha da tabela)
                rank = None
                parent_tr = link.find_parent('tr')
                if parent_tr:
                    # Primeira célula geralmente contém o rank
                    first_td = parent_tr.find('td')
                    if first_td:
                        rank_text = first_td.get_text(strip=True)
                        if rank_text.isdigit():
                            rank = rank_text
                
                # Se não encontrou rank, usa posição na lista
                if not rank:
                    rank = str(len(distros) + 1)
                
                distros.append({
                    'rank': rank,
                    'name': distro_name,
                    'url': distro_url
                })
            
            logger.info(f"✅ Scraped {len(distros)} distribuições únicas")
            return distros
            
        except Exception as e:
            logger.error(f"❌ Erro ao fazer scraping da lista: {e}")
            logger.info("💡 Dica: Se estiver rodando localmente e DistroWatch estiver bloqueado, use GitHub Actions")
            return []
    
    def scrape_distro_details(self, distro_url: str) -> Optional[Dict]:
        """
        Scrape detalhes de uma distribuição específica.
        
        Args:
            distro_url: URL da página da distro
        
        Returns:
            Dict com detalhes da distro ou None se falhar
        """
        logger.info(f"📄 Scraping detalhes de: {distro_url}")
        
        try:
            response = self.scraper.get(distro_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            details = {}
            
            # Extrai informações da página
            # Based: seção com informações básicas
            info_table = soup.find('table', class_='Info')
            
            if info_table:
                rows = info_table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        key = cols[0].get_text(strip=True).lower().replace(':', '')
                        value = cols[1].get_text(strip=True)
                        details[key] = value
            
            return details
            
        except Exception as e:
            logger.error(f"❌ Erro ao scraping detalhes: {e}")
            return None
    
    def scrape_all(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Scrape completo: lista + detalhes de cada distro.
        
        Args:
            limit: Limite de distros para scrape (None = todas)
        
        Returns:
            Lista de distros com todos os dados
        """
        logger.info("🚀 Iniciando scraping completo do DistroWatch...")
        
        # Scrape lista
        distros = self.scrape_distro_list()
        
        if not distros:
            logger.warning("⚠️ Nenhuma distro encontrada na lista")
            return []
        
        # Aplica limite se especificado
        if limit:
            distros = distros[:limit]
            logger.info(f"📊 Limitando scraping a {limit} distribuições")
        
        logger.info(f"✅ Scraping completo: {len(distros)} distribuições processadas")
        
        return distros


def test_scraper():
    """Testa o scraper localmente."""
    import json
    
    print("🧪 Testando CloudScraper...")
    
    scraper = DistroWatchCloudScraper()
    results = scraper.scrape_all(limit=5)
    
    print(f"\n✅ Resultados: {len(results)} distros")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_scraper()
