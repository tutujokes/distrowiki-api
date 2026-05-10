# distrowiki-api/api/services/scrapling_distrowatch_service.py

import logging
import asyncio
import random
from typing import List, Dict, Any, Optional
from scrapling.fetchers import StealthyFetcher
from scrapling.parser import Selector
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class ScraplingDistroWatchClient:
    """
    Novo cliente de scraping para DistroWatch usando a biblioteca Scrapling.
    Oferece maior resiliência contra mudanças de HTML e bloqueios.
    """
    
    BASE_URL = "https://distrowatch.com"
    
    def __init__(self, timeout: int = 30000):
        self.timeout = timeout

    async def _fetch_page(self, path: str) -> Optional[Any]:
        """Busca uma página usando StealthyFetcher (Firefox spoofing) e bypassa Cloudflare."""
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        try:
            # Adiciona wait_selector para garantir que passou o desafio do Cloudflare
            # O 403 inicial do Cloudflare será ignorado se o h1 carregar depois
            page = await StealthyFetcher.async_fetch(url, timeout=self.timeout, wait_selector="h1")
            
            # Se não tiver o elemento básico de uma página do DistroWatch, falhou
            if not page.css("h1"):
                logger.warning(f"⚠️ Falha ao buscar {url}: Elementos não carregaram (possível bloqueio Cloudflare)")
                return None
            
            return page
        except Exception as e:
            logger.error(f"❌ Erro de rede Scrapling ao buscar {url}: {e}")
            return None

    async def fetch_distro_details(self, distro_slug: str) -> Optional[Dict[str, Any]]:
        """
        Busca detalhes de uma distribuição específica.
        
        Campos retornados:
        - architecture (List[str])
        - popularity_rank (int)
        - release_type (str)
        - init_system (str)
        - file_systems (List[str])
        - latest_release (str - YYYY-MM-DD)
        """
        logger.info(f"🔍 Scrapling: Buscando detalhes de '{distro_slug}'")
        
        # O DistroWatch usa table.php?distribution=slug
        selector = await self._fetch_page(f"table.php?distribution={distro_slug}")
        
        if not selector:
            return None

        data = {
            "distro_id": distro_slug,
            "scraped_at": datetime.now().isoformat()
        }

        try:
            # Extrair Nome (a partir de h1)
            h1_elem = selector.css("h1")
            data["nome"] = None
            if h1_elem:
                data["nome"] = re.sub(r'<[^>]*>', '', h1_elem[0].get() or "").strip()
            if not data["nome"]:
                data["nome"] = distro_slug
                
            # Extrair Descricao
            desc_meta = selector.css('meta[name="description"]')
            data["descricao"] = ""
            if desc_meta and hasattr(desc_meta[0], 'attrib'):
                data["descricao"] = desc_meta[0].attrib.get("content", "").strip()

            # 1 & 2. Extrair Metadados e Popularidade (Nova estrutura Distrowatch: ul > li > b)
            li_elements = selector.css("ul li")
            for li in li_elements:
                b_elems = li.css("b")
                if not b_elems:
                    continue
                label = re.sub(r'<[^>]*>', '', b_elems[0].get() or "").strip(': \n')
                full_text = re.sub(r'<[^>]*>', '', li.get() or "").strip()
                # O valor é o resto do texto no LI, menos o label
                raw_label = re.sub(r'<[^>]*>', '', b_elems[0].get() or "")
                value = full_text.replace(raw_label, '', 1).strip()
                
                if "Architecture" in label or "Arquitetura" in label:
                    data["architecture"] = [a.strip() for a in value.split(",") if a.strip()]
                elif ("Release Model" in label) or ("Modelo de lançamento" in label) or ("Release Type" in label):
                    if "rolling" in value.lower():
                        data["release_type"] = "Rolling"
                    elif "lts" in value.lower():
                        data["release_type"] = "LTS"
                    else:
                        data["release_type"] = "Point Release"
                elif "Init Software" in label or "Init" in label:
                    data["init_system"] = value
                elif "File Systems" in label or "Filesystems" in label:
                    data["file_systems"] = [f.strip() for f in value.split(",") if f.strip()]
                elif "Popularity" in label or "Popularidade" in label:
                    rank_match = re.search(r'(\d+)', value)
                    if rank_match:
                        data["popularity_rank"] = int(rank_match.group(1))

            # 3. Data de última release
            # Procure por "Last Update" em <h2> ou similar
            h2_texts = [re.sub(r'<[^>]*>', '', el.get() or "").strip() for el in selector.css("h2")]
            for text in h2_texts:
                if "Last Update" in text or "Última atualização" in text:
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                    if date_match:
                        data["latest_release"] = date_match.group(1)
                        break

            logger.info(f"✅ Dados extraídos via Scrapling para {distro_slug}")
            return data

        except Exception as e:
            logger.error(f"❌ Erro ao parsear dados com Scrapling para {distro_slug}: {e}")
            return None

    async def fetch_all_distros(self, slugs: List[str]) -> List[Dict[str, Any]]:
        """
        Itera sobre uma lista de slugs e realiza scraping com delays.
        """
        results = []
        for i, slug in enumerate(slugs):
            logger.info(f"[{i+1}/{len(slugs)}] Processando {slug}...")
            result = await self.fetch_distro_details(slug)
            if result:
                results.append(result)
            
            # Politeness: delay básico entre requests
            if i < len(slugs) - 1:
                await asyncio.sleep(random.uniform(1.2, 2.5))
        
        return results

    async def fetch_ranking_list(self) -> List[Dict[str, Any]]:
        """
        Busca o ranking atual das top 100 distros no DistroWatch.
        """
        logger.info("📥 Scrapling: Buscando ranking do DistroWatch...")
        # A página principal (index.php) do DistroWatch contém o ranking na barra lateral
        # Mas podemos forçar o ranking "last month" via table.php
        selector = await self._fetch_page("dwres.php?resource=popularity")
        
        if not selector:
            return []

        ranking = []
        try:
            # A tabela de popularidade geralmente a classe .phr1, .phr2, etc. Ou apenas links contendo '?distribution='
            # Vamos buscar os links diretamente de uma tabela para evitar falsos positivos
            links = selector.css("table a[href*='table.php?distribution=']")
            
            # Use a Set to avoid duplicates if any, preserving order
            seen = set()
            valid_links = []
            for link in links:
                href = link.attrib.get('href', '') if hasattr(link, 'attrib') else ""
                slug = href.split('=')[-1]
                if slug and slug not in seen:
                    seen.add(slug)
                    valid_links.append(link)

            for i, link in enumerate(valid_links[:100], 1):
                href = link.attrib.get('href', '') if hasattr(link, 'attrib') else ""
                slug = href.split('=')[-1]
                if slug:
                    ranking.append({
                        "rank": i,
                        "slug": slug,
                        "name": re.sub(r'<[^>]*>', '', link.get() or "").strip()
                    })
            
            logger.info(f"✅ {len(ranking)} distros encontradas no ranking via Scrapling")
            return ranking
        except Exception as e:
            logger.error(f"❌ Erro ao parsear ranking com Scrapling: {e}")
            return []
