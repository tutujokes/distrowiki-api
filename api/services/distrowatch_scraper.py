"""
DistroWatch Scraper Service with Playwright Browser Automation.

Implements stealth scraping using real browser to fetch additional distro metadata:
- Popularity ranking
- Release type (LTS/Rolling)
- Init system
- File systems
- Architectures

Uses Playwright with Chromium for:
1. Real browser fingerprint (bypasses 403 blocks)
2. JavaScript execution
3. Human-like behavior with random delays
4. Cookie and session persistence
"""

import logging
import random
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from bs4 import BeautifulSoup
import re

# Playwright for browser automation
try:
    from playwright.async_api import async_playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Fallback to httpx if Playwright not available
import httpx

# Importar mapeamento de IDs
from .id_mapping import get_distrowatch_id

logger = logging.getLogger(__name__)

# Importar o novo cliente Scrapling (opcional)
try:
    from .scrapling_distrowatch_service import ScraplingDistroWatchClient
    scrapling_client = ScraplingDistroWatchClient()
    SCRAPLING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Scrapling não disponível, usando apenas scraper legado: {e}")
    scrapling_client = None
    SCRAPLING_AVAILABLE = False


class DistroWatchScraper:
    """Scraper para coletar dados adicionais do DistroWatch."""
    
    BASE_URL = "https://distrowatch.com"
    
    # ====== ANTI-DETECTION: User-Agents Reais ======
    USER_AGENTS = [
        # Chrome Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Chrome Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        # Chrome Linux
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        # Firefox Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        # Firefox Mac
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:121.0) Gecko/20100101 Firefox/121.0",
        # Firefox Linux
        "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        # Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
        # Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]
    
    # ====== ANTI-DETECTION: Accept-Language por região ======
    ACCEPT_LANGUAGES = [
        "en-US,en;q=0.9",
        "en-GB,en;q=0.9,en-US;q=0.8",
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "de-DE,de;q=0.9,en;q=0.8",
        "fr-FR,fr;q=0.9,en;q=0.8",
        "es-ES,es;q=0.9,en;q=0.8",
    ]
    
    # ====== ANTI-DETECTION: Referers realistas ======
    REFERERS = [
        "https://www.google.com/",
        "https://www.google.com/search?q=linux+distributions",
        "https://duckduckgo.com/",
        "https://www.bing.com/",
        "https://distrowatch.com/",
        None,  # Às vezes sem referer
    ]
    
    # Delay config (segundos)
    MIN_DELAY = 5.0
    MAX_DELAY = 10.0
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.last_request_time: Optional[datetime] = None
        # Fallback httpx client
        self.client: Optional[httpx.AsyncClient] = None
        
    async def _init_browser(self):
        """Inicializa o navegador Playwright."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright não disponível, usando httpx como fallback")
            return False
            
        if self.browser is None:
            try:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                    ]
                )
                logger.info("Playwright browser inicializado com sucesso")
                return True
            except Exception as e:
                logger.error(f"Erro ao inicializar Playwright: {e}")
                return False
        return True
    
    async def _init_client(self):
        """Inicializa o cliente HTTP como fallback."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                cookies=httpx.Cookies(),
            )
    
    def _get_random_headers(self) -> Dict[str, str]:
        """Gera headers aleatórios para cada request."""
        ua = random.choice(self.USER_AGENTS)
        accept_lang = random.choice(self.ACCEPT_LANGUAGES)
        referer = random.choice(self.REFERERS)
        
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": accept_lang,
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site" if referer else "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        
        if referer:
            headers["Referer"] = referer
            
        return headers
    
    async def _delay_with_jitter(self):
        """Adiciona delay aleatório entre requests."""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            min_wait = self.MIN_DELAY - elapsed
            if min_wait > 0:
                # Adiciona jitter de ±30%
                jitter = random.uniform(0.7, 1.3)
                delay = random.uniform(self.MIN_DELAY, self.MAX_DELAY) * jitter
                actual_delay = max(min_wait, delay)
                logger.debug(f"Aguardando {actual_delay:.2f}s antes do próximo request...")
                await asyncio.sleep(actual_delay)
        
        self.last_request_time = datetime.now()
    
    async def fetch_distro_page(self, distrowiki_id: str, max_retries: int = 3) -> Optional[str]:
        """
        Busca a página de uma distro no DistroWatch usando Playwright.
        
        Args:
            distrowiki_id: ID da distro no DistroWiki (será convertido para ID do DW)
            max_retries: Número máximo de tentativas (padrão: 3)
            
        Returns:
            HTML da página ou None se falhar
        """
        # Converter ID para formato DistroWatch
        distrowatch_id = get_distrowatch_id(distrowiki_id)
        url = f"{self.BASE_URL}/table.php?distribution={distrowatch_id}"
        
        for attempt in range(1, max_retries + 1):
            await self._delay_with_jitter()
            
            # Tentar com Playwright primeiro
            if await self._init_browser():
                try:
                    if attempt > 1:
                        logger.info(f"Tentativa {attempt}/{max_retries} para {distrowatch_id}")
                    else:
                        logger.info(f"Scraping com Playwright: {distrowiki_id} -> {distrowatch_id}")
                    
                    # Criar contexto com fingerprint realista
                    context = await self.browser.new_context(
                        user_agent=random.choice(self.USER_AGENTS),
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US',
                        timezone_id='America/New_York',
                    )
                    
                    page = await context.new_page()
                    
                    # Navegar - usar domcontentloaded (mais rápido que networkidle)
                    response = await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    
                    if response and response.status == 200:
                        # Simular leitura humana
                        await page.wait_for_timeout(random.randint(1000, 2000))
                        
                        # Scroll suave
                        await page.evaluate('window.scrollBy(0, 300)')
                        await page.wait_for_timeout(random.randint(500, 1000))
                        
                        html = await page.content()
                        await context.close()
                        return html
                        
                    elif response and response.status in [403, 503]:
                        title = await page.title()
                        logger.info(f"Desafio Cloudflare (ou bloqueio) detectado para {distrowatch_id}. Status: {response.status}, Title: '{title}'. Aguardando resolução...")
                        try:
                            # Esperar Cloudflare resolver e carregar a tag h1 da distro
                            await page.wait_for_selector('h1', timeout=25000)
                            logger.info(f"Cloudflare resolvido para {distrowatch_id}!")
                            
                            # Scroll suave após resolver
                            await page.evaluate('window.scrollBy(0, 300)')
                            await page.wait_for_timeout(random.randint(500, 1000))
                            
                            html = await page.content()
                            await context.close()
                            return html
                        except Exception as e:
                            logger.error(f"Cloudflare não resolveu a tempo para {distrowatch_id}.")
                        
                        logger.warning(f"Status {response.status} definitivo para {distrowatch_id} (tentativa {attempt}/{max_retries})")
                        await context.close()
                        
                        if attempt < max_retries:
                            # Backoff exponencial: 10s, 20s, 40s
                            backoff = 10 * (2 ** (attempt - 1))
                            logger.info(f"Aguardando {backoff}s antes de retry...")
                            await asyncio.sleep(backoff)
                            continue
                        return None
                    else:
                        status = response.status if response else 'None'
                        logger.warning(f"Status {status} para {distrowatch_id} (Playwright)")
                        await context.close()
                        return None
                        
                except Exception as e:
                    logger.error(f"Erro Playwright para {distrowatch_id}: {e}")
                    if attempt < max_retries:
                        backoff = 5 * attempt
                        await asyncio.sleep(backoff)
                        continue
            
            # Fallback: usar httpx
            await self._init_client()
            headers = self._get_random_headers()
            
            try:
                logger.info(f"Fallback httpx: {distrowiki_id} -> {distrowatch_id}")
                response = await self.client.get(url, headers=headers)
                
                if response.status_code == 200:
                    return response.text
                elif response.status_code == 403 and attempt < max_retries:
                    backoff = 10 * (2 ** (attempt - 1))
                    logger.info(f"Aguardando {backoff}s antes de retry...")
                    await asyncio.sleep(backoff)
                    continue
                else:
                    logger.warning(f"Status {response.status_code} para {distrowatch_id}")
                    return None
                    
            except Exception as e:
                logger.error(f"Erro ao buscar {distrowatch_id}: {e}")
                if attempt >= max_retries:
                    return None
        
        return None
    
    async def close(self):
        """Fecha o browser e o cliente HTTP."""
        if self.browser:
            try:
                await self.browser.close()
                self.browser = None
            except Exception as e:
                logger.error(f"Erro ao fechar browser: {e}")
        
        if self.playwright:
            try:
                await self.playwright.stop()
                self.playwright = None
            except Exception as e:
                logger.error(f"Erro ao parar playwright: {e}")
        
        if self.client:
            try:
                await self.client.aclose()
                self.client = None
            except Exception as e:
                logger.error(f"Erro ao fechar httpx client: {e}")

    
    def parse_distro_data(self, html: str) -> Dict[str, Any]:
        """
        Extrai dados da página HTML do DistroWatch.
        
        Returns:
            Dict com: architecture, popularity_rank, release_type, init_system, file_systems
        """
        soup = BeautifulSoup(html, 'html.parser')
        data = {}
        
        try:
            # Encontrar tabela de metadados
            # DistroWatch usa tabelas para mostrar info
            
            # Architecture
            arch_match = self._find_table_value(soup, ["Architecture", "Arquitectura"])
            if arch_match:
                # Parse: "armhf, ppc64el, x86_64" -> ["armhf", "ppc64el", "x86_64"]
                data["architecture"] = [a.strip() for a in arch_match.split(",") if a.strip()]
            
            # Popularity Rank (do ranking section)
            rank_text = soup.find(string=re.compile(r"Page Hit Ranking", re.I))
            if rank_text:
                parent = rank_text.find_parent("td") or rank_text.find_parent("th")
                if parent:
                    next_cell = parent.find_next_sibling("td")
                    if next_cell:
                        rank_match = re.search(r'\d+', next_cell.get_text())
                        if rank_match:
                            data["popularity_rank"] = int(rank_match.group())
            
            # Release Type (Fixed/Rolling)
            release_type = self._find_table_value(soup, ["Release Model", "Modelo de lançamento"])
            if release_type:
                if "rolling" in release_type.lower():
                    data["release_type"] = "Rolling"
                elif "lts" in release_type.lower():
                    data["release_type"] = "LTS"
                elif "fixed" in release_type.lower():
                    data["release_type"] = "Point Release"
                else:
                    data["release_type"] = release_type
            
            # Init System
            init = self._find_table_value(soup, ["Init Software", "Init"])
            if init:
                data["init_system"] = init.strip()
            
            # File Systems
            fs = self._find_table_value(soup, ["File Systems", "Filesystems", "Sistemas de arquivos"])
            if fs:
                data["file_systems"] = [f.strip() for f in fs.split(",") if f.strip()]
            
            # Latest Release Date
            # DistroWatch shows "Last Update: YYYY-MM-DD HH:MM UTC" in an H2 tag
            # Try H2 header first (most reliable)
            h2_tags = soup.find_all("h2")
            for h2 in h2_tags:
                h2_text = h2.get_text()
                if "Last Update" in h2_text or "Última atualização" in h2_text:
                    # Extract date from "Last Update: 2026-01-04 08:22 UTC"
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', h2_text)
                    if date_match:
                        data["latest_release"] = date_match.group(1)
                        break
            
            # Fallback: try table cells
            if not data.get("latest_release"):
                last_update = self._find_table_value(soup, ["Release Date", "Last Update", "Latest Release"])
                if last_update:
                    data["latest_release"] = self._parse_distrowatch_date(last_update)
                
        except Exception as e:
            logger.error(f"Erro ao parsear HTML: {e}")
            
        return data
    
    def _parse_distrowatch_date(self, date_str: str) -> Optional[str]:
        """
        Converte data do DistroWatch para formato ISO (YYYY-MM-DD).
        
        DistroWatch usa formatos como:
        - "2024-07-04"
        - "July 4, 2024" 
        - "4 July 2024"
        - "04/07/2024"
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Já está em ISO?
        iso_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', date_str)
        if iso_match:
            return date_str
        
        # Tentar parsear com dateutil se disponível
        try:
            from dateutil import parser as date_parser
            parsed = date_parser.parse(date_str, dayfirst=True)
            return parsed.strftime('%Y-%m-%d')
        except:
            pass
        
        # Fallback: extrair números
        date_match = re.search(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', date_str)
        if date_match:
            day, month, year = date_match.groups()
            try:
                return f"{year}-{int(month):02d}-{int(day):02d}"
            except:
                pass
        
        return None
    
    def _find_table_value(self, soup: BeautifulSoup, labels: List[str]) -> Optional[str]:
        """Busca valor em tabela dado um label."""
        for label in labels:
            # Tenta encontrar célula com o label
            cell = soup.find(string=re.compile(label, re.I))
            if cell:
                parent = cell.find_parent("td") or cell.find_parent("th")
                if parent:
                    # Próxima célula geralmente tem o valor
                    next_cell = parent.find_next_sibling("td")
                    if next_cell:
                        return next_cell.get_text(strip=True)
        return None
    
    async def scrape_distro(self, distro_id: str) -> Dict[str, Any]:
        """
        Scrape completo de uma distro.
        
        Args:
            distro_id: ID da distro
            
        Returns:
            Dict com dados extraídos
        """
        html = await self.fetch_distro_page(distro_id)
        if not html:
            return {"error": f"Falha ao buscar {distro_id}"}
        
        data = self.parse_distro_data(html)
        data["distro_id"] = distro_id
        data["scraped_at"] = datetime.now().isoformat()
        
        return data
    
    async def scrape_multiple(self, distro_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Scrape de múltiplas distros com delays entre cada uma.
        
        Args:
            distro_ids: Lista de IDs
            
        Returns:
            Lista de resultados
        """
        results = []
        
        for i, distro_id in enumerate(distro_ids):
            logger.info(f"Processando {i+1}/{len(distro_ids)}: {distro_id}")
            result = await self.scrape_distro(distro_id)
            results.append(result)
            
            # Progress log a cada 10
            if (i + 1) % 10 == 0:
                logger.info(f"Progresso: {i+1}/{len(distro_ids)} distros processadas")
        
        return results
    
    async def close(self):
        """Fecha o cliente HTTP."""
        if self.client:
            await self.client.aclose()
            self.client = None



# ====== FACADE PARA INTEGRAÇÃO COM SCRAPLING ======

async def get_distro_details(distro_slug: str) -> Dict[str, Any]:
    """
    Função principal para obter metadados de uma distribuição.
    Tenta via Scrapling primeiro e cai para o scraper legado em caso de erro.
    """
    if SCRAPLING_AVAILABLE and scrapling_client:
        try:
            data = await scrapling_client.fetch_distro_details(distro_slug)
            if data:
                return data
            raise Exception("Scrapling retornou dados vazios")
        except Exception as e:
            logger.warning(f"⚠️  Scrapling falhou para '{distro_slug}', usando fallback legado: {e}")
    
    # Fallback para scraper legado
    scraper = DistroWatchScraper()
    try:
        return await scraper.scrape_distro(distro_slug)
    finally:
        await scraper.close()

async def get_all_distros(slugs: List[str]) -> List[Dict[str, Any]]:
    """
    Busca metadados para uma lista de distribuições com fallback.
    """
    results = []
    for slug in slugs:
        result = await get_distro_details(slug)
        results.append(result)
        # Delay básico de segurança entre as chamadas no facade
        await asyncio.sleep(1.0)
    return results

async def fetch_ranking_list() -> List[Dict[str, Any]]:
    """
    Busca o ranking do DistroWatch via Scrapling.
    """
    if not SCRAPLING_AVAILABLE or not scrapling_client:
        logger.warning("⚠️ Scrapling não disponível para buscar ranking")
        return []
    try:
        return await scrapling_client.fetch_ranking_list()
    except Exception as e:
        logger.error(f"❌ Falha ao buscar ranking via Scrapling: {e}")
        return []

# Funções auxiliares mantidas para retrocompatibilidade
async def scrape_distrowatch_data(distro_ids: List[str]) -> List[Dict[str, Any]]:
    """Helper legado: agora delega para get_all_distros."""
    return await get_all_distros(distro_ids)
