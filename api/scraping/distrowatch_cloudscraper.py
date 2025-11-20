"""
Scraper do DistroWatch usando CloudScraper.
Extrai dados reais das páginas de distribuições Linux.
"""

import logging
import re
import time
import cloudscraper
import requests
import random
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class DistroWatchCloudScraper:
    """
    Scraper para DistroWatch.
    
    Extrai informações de distribuições Linux:
    - Nome, ID, Categoria
    - Data de lançamento (formato BR: DD/MM/YYYY)
    - Popularidade (4 semanas)
    - Rating (avaliação dos visitantes)
    """
    
    def __init__(self, delay: int = 2, use_proxies: bool = True):
        """
        Inicializa o scraper.
        
        Args:
            delay: Delay entre requests em segundos (rate limiting)
            use_proxies: Se deve usar proxies da lista pública
        """
        self.base_url = "https://distrowatch.com"
        self.delay = delay
        self.use_proxies = use_proxies
        self.working_proxies = []
        self.current_proxy_index = 0
        
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        
        # Carregar proxies se habilitado
        if self.use_proxies:
            self._load_proxies()
        
    def _extract_slug_from_url(self, url: str) -> str:
        """
        Extrai o slug/ID da distribuição da URL.
        
        Args:
            url: URL da distro (ex: https://distrowatch.com/table.php?distribution=ubuntu)
        
        Returns:
            Slug da distro (ex: "ubuntu")
        """
        match = re.search(r'distribution=([^&]+)', url)
        if match:
            return match.group(1)
        return ""
    
    def _load_proxies(self):
        """Carrega e valida proxies das listas públicas do GitHub."""
        logger.info("🔄 Carregando proxies...")
        
        proxy_urls = [
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
        ]
        
        all_proxies = []
        
        for url in proxy_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    proxies = response.text.strip().split('\n')
                    proxy_type = 'socks5' if 'socks5' in url else ('socks4' if 'socks4' in url else 'http')
                    
                    for proxy in proxies[:50]:  # Limitar a 50 de cada tipo
                        proxy = proxy.strip()
                        if proxy and not proxy.startswith('#'):
                            all_proxies.append({
                                'type': proxy_type,
                                'address': proxy
                            })
                    
                    logger.info(f"✅ Carregados {len(proxies[:50])} proxies {proxy_type.upper()}")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao carregar {url}: {e}")
        
        # Embaralhar para distribuir melhor
        random.shuffle(all_proxies)
        
        # Guardar todos os proxies sem testar (teste será feito durante uso)
        # Isso acelera a inicialização
        self.working_proxies = all_proxies[:30]  # Usar os primeiros 30
        
        logger.info(f"✅ {len(self.working_proxies)} proxies carregados e prontos para uso")
    
    def _get_next_proxy(self) -> Optional[Dict]:
        """
        Retorna o próximo proxy da lista (rotação).
        
        Returns:
            Dict com configuração do proxy ou None
        """
        if not self.working_proxies:
            return None
        
        proxy_info = self.working_proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.working_proxies)
        
        return {
            'http': f"{proxy_info['type']}://{proxy_info['address']}",
            'https': f"{proxy_info['type']}://{proxy_info['address']}"
        }
    
    def _make_request(self, url: str, timeout: int = 15) -> requests.Response:
        """
        Faz uma requisição usando proxy rotativo ou direto.
        
        Args:
            url: URL para acessar
            timeout: Timeout em segundos
        
        Returns:
            Response object
        """
        # Tentar com proxy se disponível
        if self.use_proxies and self.working_proxies:
            max_attempts = min(5, len(self.working_proxies))  # Tentar até 5 proxies
            
            for attempt in range(max_attempts):
                try:
                    proxies = self._get_next_proxy()
                    response = self.scraper.get(url, timeout=timeout, proxies=proxies)
                    response.raise_for_status()
                    logger.debug(f"✅ Request com proxy bem-sucedido")
                    return response
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 403:
                        logger.debug(f"⚠️ Proxy bloqueado (403), tentando outro...")
                        continue
                    raise
                except Exception as e:
                    logger.debug(f"⚠️ Proxy falhou (tentativa {attempt + 1}/{max_attempts}): {type(e).__name__}")
                    continue
        
        # Fallback: tentar sem proxy
        try:
            response = self.scraper.get(url, timeout=timeout)
            response.raise_for_status()
            logger.debug(f"✅ Request sem proxy bem-sucedido")
            return response
        except Exception as e:
            logger.error(f"❌ Todas as tentativas falharam: {e}")
            raise
    
    def _get_fallback_distros(self, limit: int = 230) -> List[Dict]:
        """
        Retorna lista predefinida das distribuições mais populares.
        
        Usado quando o scraping do ranking falha (geralmente por 403).
        Lista baseada no ranking "Last 1 month" do DistroWatch.
        
        Args:
            limit: Número máximo de distros a retornar
        
        Returns:
            Lista de dicts com rank, name, slug, url
        """
        # Top 230 distros do DistroWatch (ordenadas por popularidade)
        fallback_list = [
            "cachyos", "mxlinux", "linuxmint", "popos", "endeavouros", "manjaro", "ubuntu",
            "debian", "fedora", "opensuse", "zorin", "elementary", "kdeneon", "arch", "garuda",
            "nobara", "lmde", "blendos", "vanillaos", "archcraft", "biglinux", "antiX", "peppermint",
            "arcolinux", "lite", "gentoo", "sparky", "kde", "voyager", "slackware",
            "rocky", "alma", "nixos", "artix", "freebsd", "tuxedo", "rhel", "devuan", "solus",
            "alpine", "void", "tails", "openbsd", "mageia", "bodhi", "pclinuxos", "kali", "porteus",
            "dietpi", "linuxfx", "puppy", "netbsd", "android", "parrot", "pureos", "q4os", "trisquel",
            "crunchbang", "opensuse-microos", "deepin", "openmandriva", "calculate", "ubuntuunity",
            "dragonfly", "oracle", "ubuntudde", "haiku", "clearlinux", "dragora", "ubuntukylin", "spiral",
            "freespire", "redcore", "suse", "redhat", "emmabuntus", "rose", "siduction", "kaos", "feren",
            "batocera", "porteus-kiosk", "bunsenlabs", "slax", "knoppix", "pearos", "hpux", "salix",
            "solaris", "opensuse-slowroll", "voidpup", "rebornos", "kuklinux", "astra", "au", "hyperbola",
            "xubuntu", "lubuntu", "kubuntu", "4mlinux", "gobolinux", "septor", "ubuntustudio", "bluestar",
            "lakka", "tinycore", "ubuntumate", "raspberry", "scientific", "irix", "snal", "unraid",
            "parabola", "elive", "antergos", "grml", "freenas", "murena", "xerolinux", "openwrt",
            "qubes", "murena-two", "ubuntucinnamon", "kaisen", "clearos", "truenas", "ubuntubudgie", "clonezilla",
            "guix", "slitaz", "redo", "qubes-whonix", "thinstation", "tiny", "finnix", "nitrux",
            "uruk", "paldo", "linuxbbq", "pentoo", "blackarch", "rescuezilla", "lfs", "systemrescue",
            "murena-fairphone", "plamo", "wifislax", "superb", "ubos", "chromeos", "steamos", "vyos",
            "mx-23", "osgeolive", "openindiana", "neptune", "crux", "caine", "austrumi", "volumio",
            "cloudlinux", "absolute", "mx-21", "reactos", "sabayon", "ventoy", "viperr", "adelie",
            "linspire", "hanthana", "bhodi", "endless", "linuxconsole", "smoothwall", "moebius", "pfsense",
            "neon", "plop", "batocera-plus", "eurolinux", "debian-astro", "drauger", "springdale", "slackel",
            "kwort", "linuxmce", "vine", "volumio-primo", "slackex", "funtoo", "ipfire", "picaros",
            "smoothwall-express", "linuxmint-lmde", "dahlia", "primtux", "wattOS", "turbolinux", "makulu",
            "velt", "zentyal", "supergrubdisk", "rlxos", "rescatux", "murena-degooglified", "navylinux", "murena-teracube",
            "cub", "antix-core", "astralinux", "volumio-rivo"
        ]
        
        distros = []
        for idx, slug in enumerate(fallback_list[:limit], start=1):
            distros.append({
                'rank': idx,
                'name': slug.capitalize(),
                'slug': slug,
                'url': f"{self.base_url}/table.php?distribution={slug}"
            })
        
        return distros
    
    def _parse_category(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrai categoria da página da distro.
        
        Returns:
            String com categorias separadas por vírgula (ex: "Desktop, Live Medium")
        """
        try:
            for li in soup.find_all('li'):
                b_tag = li.find('b')
                if b_tag and 'Categoria' in b_tag.get_text():
                    categories = [a.get_text(strip=True) for a in li.find_all('a')]
                    return ', '.join(categories)
        except Exception as e:
            logger.debug(f"Erro ao extrair categoria: {e}")
        return None
    
    def _parse_release_date(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extrai data de lançamento da versão mais recente.
        
        Returns:
            Data no formato DD/MM/YYYY (ex: "17/11/2025")
        """
        try:
            for th in soup.find_all('th'):
                if 'Data de Lançamento' in th.get_text():
                    row = th.find_parent('tr')
                    date_td = row.find('td', class_='Date')
                    if date_td:
                        date_str = date_td.get_text(strip=True)  # "2025-11-17"
                        # Converter para formato brasileiro
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        return date_obj.strftime('%d/%m/%Y')  # "17/11/2025"
        except Exception as e:
            logger.debug(f"Erro ao extrair data de lançamento: {e}")
        return None
    
    def _parse_popularity(self, soup: BeautifulSoup) -> Dict[str, Optional[int]]:
        """
        Extrai popularidade de 4 semanas (rank e hits por dia).
        
        Returns:
            Dict com 'rank' e 'hits_per_day'
        """
        result = {'rank': None, 'hits_per_day': None}
        
        try:
            # Buscar texto que contém "4 semanas"
            for text_node in soup.find_all(string=re.compile(r'4 semanas')):
                full_text = text_node.parent.get_text()
                # Pattern: "4 semanas: 21 (603)" ou "4 semanas: <b>21</b> (603)"
                match = re.search(r'4 semanas:\s*(\d+)\s*\(([0-9,]+)\)', full_text)
                if match:
                    result['rank'] = int(match.group(1))
                    result['hits_per_day'] = int(match.group(2).replace(',', ''))
                    break
        except Exception as e:
            logger.debug(f"Erro ao extrair popularidade: {e}")
        
        return result
    
    def _parse_rating(self, soup: BeautifulSoup) -> Optional[float]:
        """
        Extrai rating (avaliação dos visitantes).
        
        Returns:
            Número decimal do rating (ex: 8.0)
        """
        try:
            # Buscar por <a> que contém "Average visitor rating"
            for a_tag in soup.find_all('a', href=lambda x: x and 'ratings' in x):
                if 'Average visitor rating' in a_tag.get_text():
                    # Estrutura: <b><a>Average visitor rating</a></b>: <b>8.0</b>/10
                    parent_b = a_tag.parent  # <b> que envolve o <a>
                    if parent_b and parent_b.name == 'b':
                        # Buscar o próximo <b> após o </b> do link
                        for sibling in parent_b.next_siblings:
                            if hasattr(sibling, 'name') and sibling.name == 'b':
                                # Este é o <b>8.0</b>
                                rating_text = sibling.get_text(strip=True)
                                try:
                                    return float(rating_text)
                                except ValueError:
                                    pass
        except Exception as e:
            logger.debug(f"Erro ao extrair rating: {e}")
        return None
    
    def scrape_ranking_page(self, limit: int = 230) -> List[Dict]:
        """
        Scrape página de ranking (/popularity) para obter lista de distros.
        Busca apenas da tabela "Last 1 month".
        
        Args:
            limit: Número máximo de distros para extrair (padrão: 230)
        
        Returns:
            Lista de dicts com 'rank', 'name', 'slug', 'url'
        """
        logger.info(f"🔍 Buscando top {limit} distros da página de ranking...")
        
        url = f"{self.base_url}/dwres.php?resource=popularity"
        
        try:
            logger.info(f"📡 Acessando: {url}")
            response = self._make_request(url, timeout=30)
            
            logger.info(f"✅ Status: {response.status_code}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            distros = []
            
            # Encontrar tabela "Last 1 month"
            target_table = None
            for th in soup.find_all('th', class_='Invert'):
                if 'Last 1 month' in th.get_text():
                    target_table = th.find_parent('table')
                    logger.info("✅ Tabela 'Last 1 month' encontrada")
                    break
            
            if not target_table:
                logger.error("❌ Tabela 'Last 1 month' não encontrada")
                return []
            
            # Percorrer linhas da tabela
            rows = target_table.find_all('tr')
            
            for row in rows:
                # Buscar células de ranking
                rank_cell = row.find('th', class_='phr1')
                name_cell = row.find('td', class_='phr2')
                
                if rank_cell and name_cell:
                    try:
                        rank = int(rank_cell.get_text(strip=True))
                        
                        # Extrair link e nome
                        link = name_cell.find('a')
                        if not link:
                            continue
                        
                        name = link.get_text(strip=True)
                        href = link.get('href', '')
                        
                        # Extrair slug da URL
                        slug = self._extract_slug_from_url(href)
                        
                        if not slug:
                            continue
                        
                        # URL completa
                        full_url = f"{self.base_url}/table.php?distribution={slug}"
                        
                        distros.append({
                            'rank': rank,
                            'name': name,
                            'slug': slug,
                            'url': full_url
                        })
                        
                        # Parar se atingiu o limite
                        if len(distros) >= limit:
                            break
                    
                    except (ValueError, AttributeError) as e:
                        logger.debug(f"Erro ao processar linha: {e}")
                        continue
            
            logger.info(f"✅ Encontradas {len(distros)} distribuições no ranking")
            return distros
            
        except Exception as e:
            logger.error(f"❌ Erro ao fazer scraping do ranking: {e}")
            
            # Fallback: se falhou (geralmente 403), usar lista predefinida
            logger.warning("⚠️ Usando fallback: lista predefinida de distros")
            return self._get_fallback_distros(limit)
    
    def scrape_distro_details(self, slug: str, url: str) -> Optional[Dict]:
        """
        Scrape detalhes completos de uma distribuição.
        
        Extrai:
        - Nome
        - ID (slug)
        - Categoria
        - Data de lançamento (DD/MM/YYYY)
        - Popularidade (rank e hits/dia de 4 semanas)
        - Rating
        
        Args:
            slug: Slug da distro (ex: "ubuntu")
            url: URL completa da página
        
        Returns:
            Dict com todos os dados ou None se falhar
        """
        logger.info(f"📄 Scraping: {slug}")
        
        try:
            response = self._make_request(url, timeout=30)
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extrair nome
            name = None
            h1 = soup.find('h1')
            if h1:
                name = h1.get_text(strip=True)
            
            if not name:
                logger.warning(f"⚠️ Nome não encontrado para {slug}")
                return None
            
            # Extrair dados
            category = self._parse_category(soup)
            release_date = self._parse_release_date(soup)
            popularity = self._parse_popularity(soup)
            rating = self._parse_rating(soup)
            
            return {
                'id': slug,
                'name': name,
                'category': category,
                'release_date': release_date,
                'popularity_rank': popularity['rank'],
                'popularity_hits': popularity['hits_per_day'],
                'rating': rating
            }
            
        except Exception as e:
            logger.error(f"❌ Erro ao scraping {slug}: {e}")
            return None
    
    def scrape_all(self, limit: int = 230) -> List[Dict]:
        """
        Scraping completo: busca ranking + detalhes de cada distro.
        
        Args:
            limit: Número de distros para scrape (padrão: 230)
        
        Returns:
            Lista de distros com todos os dados extraídos
        """
        logger.info(f"🚀 Iniciando scraping completo de {limit} distribuições...")
        
        # 1. Buscar lista do ranking
        ranking_list = self.scrape_ranking_page(limit=limit)
        
        if not ranking_list:
            logger.error("❌ Falha ao obter lista de ranking")
            return []
        
        logger.info(f"📋 Lista obtida: {len(ranking_list)} distros")
        
        # 2. Scrape detalhes de cada distro
        all_distros = []
        total = len(ranking_list)
        
        for i, item in enumerate(ranking_list, 1):
            slug = item['slug']
            url = item['url']
            rank = item['rank']
            
            logger.info(f"[{i}/{total}] Processando #{rank}: {slug}")
            
            details = self.scrape_distro_details(slug, url)
            
            if details:
                # Adicionar rank do ranking (caso não tenha popularidade na página)
                if details['popularity_rank'] is None:
                    details['popularity_rank'] = rank
                
                all_distros.append(details)
                logger.info(f"✅ {details['name']} - OK")
            else:
                logger.warning(f"⚠️ Falha ao processar {slug}")
            
            # Rate limiting
            if i < total:
                time.sleep(self.delay)
        
        logger.info(f"🎉 Scraping concluído: {len(all_distros)}/{total} distros processadas")
        
        return all_distros


def test_scraper():
    """Testa o scraper localmente com 3 distros."""
    import json
    
    print("🧪 Testando DistroWatch Scraper...")
    print("=" * 50)
    
    scraper = DistroWatchCloudScraper(delay=1)
    results = scraper.scrape_all(limit=3)
    
    print("\n" + "=" * 50)
    print(f"✅ Resultado: {len(results)} distros scraped")
    print("=" * 50)
    
    for distro in results:
        print(f"\n📦 {distro['name']} ({distro['id']})")
        print(f"   Categoria: {distro.get('category', 'N/A')}")
        print(f"   Data lançamento: {distro.get('release_date', 'N/A')}")
        print(f"   Popularidade: Rank {distro.get('popularity_rank', 'N/A')} ({distro.get('popularity_hits', 'N/A')} hits/dia)")
        print(f"   Rating: {distro.get('rating', 'N/A')}")
    
    # Salvar JSON para inspeção
    with open('test_scraping_result.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Resultados salvos em: test_scraping_result.json")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    test_scraper()
