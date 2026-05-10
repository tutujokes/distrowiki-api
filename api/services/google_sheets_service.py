"""
Serviço de integração com Google Sheets.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx
import os
import json
from ..models.distro import DistroMetadata, DistroFamily, DesktopEnvironment
from ..services.static_performance_data import get_or_calculate_performance

logger = logging.getLogger(__name__)

def _parse_int(value: str) -> Optional[int]:
    """Parse seguro de inteiro."""
    if not value or not value.strip():
        return None
    try:
        clean = ''.join(c for c in value if c.isdigit())
        return int(clean) if clean else None
    except:
        return None

def _parse_float(value: str) -> Optional[float]:
    """Parse seguro de float."""
    if not value or not value.strip():
        return None
    try:
        clean = value.replace(',', '.').strip()
        return float(clean)
    except:
        return None

def _parse_size_to_gb(value: str) -> Optional[float]:
    """
    Parse de tamanho de imagem para GB.
    
    Converte strings como "2.5 GB", "800 MB", "1.5GB" para float em GB.
    
    Args:
        value: String com tamanho (ex: "2.5 GB", "800 MB")
    
    Returns:
        Tamanho em GB como float ou None
    """
    if not value or not value.strip():
        return None
    
    try:
        import re
        value_clean = value.strip().upper()
        
        # Extrair número
        match = re.search(r'([\d,.]+)', value_clean)
        if not match:
            return None
        
        number = float(match.group(1).replace(',', '.'))
        
        # Detectar unidade e converter para GB
        if 'MB' in value_clean:
            return round(number / 1024, 2)  # MB → GB
        elif 'GB' in value_clean:
            return round(number, 2)
        else:
            # Assume GB se não especificar
            return round(number, 2)
    except:
        return None

class GoogleSheetsService:
    """Serviço para buscar e atualizar dados do Google Sheets."""

    SHEET_ID = "1ObKRlMRWtABnau6lZTT6en1BajVkV6m2LtLhXEHZ_Zk"
    SHEET_NAME = "distrowiki_complete"
    SHEETS_API_URL = "https://sheets.googleapis.com/v4/spreadsheets"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    TIMEOUT = 30.0

    FAMILY_MAPPING = {
        "debian": DistroFamily.DEBIAN,
        "ubuntu": DistroFamily.UBUNTU,
        "fedora": DistroFamily.FEDORA,
        "red hat": DistroFamily.FEDORA,
        "rhel": DistroFamily.FEDORA,
        "arch": DistroFamily.ARCH,
        "arch linux": DistroFamily.ARCH,
        "opensuse": DistroFamily.OPENSUSE,
        "suse": DistroFamily.OPENSUSE,
        "gentoo": DistroFamily.GENTOO,
        "slackware": DistroFamily.SLACKWARE,
        "independent": DistroFamily.INDEPENDENT,
    }

    DE_MAPPING = {
        "gnome": DesktopEnvironment.GNOME,
        "kde": DesktopEnvironment.KDE,
        "plasma": DesktopEnvironment.KDE,
        "xfce": DesktopEnvironment.XFCE,
        "mate": DesktopEnvironment.MATE,
        "cinnamon": DesktopEnvironment.CINNAMON,
        "lxde": DesktopEnvironment.LXDE,
        "lxqt": DesktopEnvironment.LXQT,
        "budgie": DesktopEnvironment.BUDGIE,
        "pantheon": DesktopEnvironment.PANTHEON,
        "deepin": DesktopEnvironment.DEEPIN,
        "i3": DesktopEnvironment.I3,
        "sway": DesktopEnvironment.SWAY,
    }

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
        )
        self.credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.access_token = None

    async def close(self):
        await self.client.aclose()

    async def fetch_all_distros(self) -> List[DistroMetadata]:
        try:
            logger.info(f"Buscando dados de Google Sheets...")
            csv_url = f"https://docs.google.com/spreadsheets/d/{self.SHEET_ID}/gviz/tq?tqx=out:csv&sheet={self.SHEET_NAME}"
            response = await self.client.get(csv_url)
            response.raise_for_status()
            lines = response.text.strip().split('\n')

            if len(lines) < 2:
                return []

            headers = self._parse_csv_line(lines[0])
            distros = []

            for line in lines[1:]:
                if not line.strip():
                    continue
                try:
                    row_data = self._parse_csv_line(line)
                    distro = self._parse_distro_row(headers, row_data)
                    if distro:
                        distros.append(distro)
                except Exception as e:
                    logger.warning(f"Erro: {e}")

            logger.info(f"Total de {len(distros)} distribuições processadas")
            return distros
        except Exception as e:
            logger.error(f"Erro: {e}", exc_info=True)
            raise

    def _parse_csv_line(self, line: str) -> List[str]:
        values = []
        current = ""
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                values.append(current.strip().strip('"'))
                current = ""
            else:
                current += char
        values.append(current.strip().strip('"'))
        return values

    def _parse_distro_row(self, headers: List[str], row_data: List[str]) -> Optional[DistroMetadata]:
        try:
            data = {}
            for i, header in enumerate(headers):
                if i < len(row_data):
                    data[header.lower().strip()] = row_data[i].strip()

            name = data.get("name", "").strip()
            if not name:
                return None

            distro_id = data.get("distro id", "").strip() or self._normalize_id(name)
            base = data.get("base", "").strip() or data.get("os type", "").strip()
            family = self._map_family(base)
            desktop_str = data.get("desktop", "").strip()
            desktop_environments = self._parse_desktop_environments(desktop_str)

            # ====== DATAS ======
            latest_release_str = data.get("latest release", "").strip()
            release_date_str = data.get("release date", "").strip()

            # Parse data da última versão
            latest_release_datetime = self._parse_date(latest_release_str)

            # Formatar para DD/MM/AAAA (string brasileira)
            latest_release = None
            if latest_release_datetime:
                latest_release = latest_release_datetime.strftime("%d/%m/%Y")

            # Parse ano de lançamento original (int)
            release_year = None
            if release_date_str:
                try:
                    # Se for só ano (ex: "2021")
                    if len(release_date_str) == 4 and release_date_str.isdigit():
                        release_year = int(release_date_str)
                    # Se for data completa, extrai o ano
                    else:
                        parsed_date = self._parse_date(release_date_str)
                        if parsed_date:
                            release_year = parsed_date.year
                except:
                    pass

            idle_ram = _parse_int(data.get("idle ram usage", ""))
            cpu_score = _parse_float(data.get("cpu score", ""))
            io_score = _parse_float(data.get("i/o score", ""))
            requirements = data.get("requirements", "").strip() or None
            package_mgmt = data.get("package management", "").strip() or None
            image_size = _parse_size_to_gb(data.get("image size", ""))
            office_suite = data.get("office suite", "").strip() or None

            # ====== NOVOS CAMPOS ======
            # Arquitetura (pode ter múltiplas separadas por vírgula)
            arch_str = data.get("architecture", "").strip()
            architecture = None
            if arch_str:
                architecture = [a.strip() for a in arch_str.split(",") if a.strip()]
            
            # Ranking de popularidade
            popularity_rank = _parse_int(data.get("popularity rank", "") or data.get("ranking", ""))
            
            # Tipo de release (LTS, Rolling, Point Release)
            release_type = data.get("release type", "").strip() or data.get("update model", "").strip() or None
            
            # Sistema de init
            init_system = data.get("init system", "").strip() or data.get("init", "").strip() or None
            
            # File systems suportados (lista)
            fs_str = data.get("file systems", "").strip() or data.get("filesystems", "").strip()
            file_systems = None
            if fs_str:
                file_systems = [f.strip() for f in fs_str.split(",") if f.strip()]
            # ====== FIM NOVOS CAMPOS ======

            # Performance: dados curados/proxy TÊM PRIORIDADE sobre a planilha
            # (a planilha pode conter scores antigos inflados gerados por LLM)
            desktop_str_list = [de.value if hasattr(de, 'value') else str(de) for de in desktop_environments]
            family_str = family.value if hasattr(family, 'value') else str(family)
            perf = get_or_calculate_performance(
                distro_id=distro_id,
                desktop_environments=desktop_str_list,
                family=family_str,
                release_type=release_type,
                init_system=init_system,
                file_systems=file_systems,
            )
            # Curado/proxy sempre sobrescreve; planilha só se não houver nem curado nem proxy
            idle_ram = perf.get("idle_ram_usage") or idle_ram
            cpu_score = perf.get("cpu_score") or cpu_score
            io_score = perf.get("io_score") or io_score

            return DistroMetadata(
                id=distro_id,
                name=name,
                summary=data.get("description", "").strip() or None,
                description=data.get("description", "").strip() or None,
                logo=data.get("logo", "").strip() or None,
                family=family,
                based_on=base or None,
                origin=data.get("origin", "").strip() or None,
                desktop_environments=desktop_environments,
                category=data.get("category", "").strip() or None,
                status=data.get("status", "").strip() or None,
                latest_release_date=latest_release,
                release_year=release_year,
                homepage=data.get("website", "").strip() or None,
                os_type=data.get("os type", "").strip() or None,
                architecture=architecture,
                popularity_rank=popularity_rank,
                release_type=release_type,
                init_system=init_system,
                file_systems=file_systems,
                rating=_parse_float(data.get("rating", "")) or 0.0,
                idle_ram_usage=idle_ram,
                cpu_score=cpu_score,
                io_score=io_score,
                requirements=requirements,
                package_management=package_mgmt,
                image_size=image_size,
                office_suite=office_suite,
            )
        except Exception as e:
            logger.warning(f"Erro ao parsear: {e}")
            return None

    def _normalize_id(self, name: str) -> str:
        return name.lower().replace(" ", "-").replace("/", "-")

    def _map_family(self, family_str: str) -> str:
        if not family_str:
            return DistroFamily.INDEPENDENT
        family_lower = family_str.lower().strip()
        for key, value in self.FAMILY_MAPPING.items():
            if key in family_lower:
                return value
        return DistroFamily.INDEPENDENT

    def _parse_desktop_environments(self, desktop_str: str) -> List[str]:
        if not desktop_str:
            return []
        des = []
        for de_item in desktop_str.split(','):
            de_lower = de_item.strip().lower()
            for key, value in self.DE_MAPPING.items():
                if key in de_lower:
                    if value not in des:
                        des.append(value)
                    break
        return des

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        date_str = date_str.strip()
        formats = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _parse_rating(self, price_str: str) -> float:
        if not price_str:
            return 0.0
        try:
            import re
            match = re.search(r'[\d.]+', price_str.replace(',', '.'))
            if match:
                value = float(match.group())
                if value > 100:
                    return 100.0
                return value
        except:
            pass
        return 0.0

    async def _get_access_token(self) -> str:
        try:
            from google.oauth2 import service_account
            import google.auth.transport.requests
            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            if os.getenv("GCP_PRIVATE_KEY"):
                credentials_info = {
                    "type": "service_account",
                    "project_id": os.getenv("GCP_PROJECT_ID"),
                    "private_key": os.getenv("GCP_PRIVATE_KEY").replace('\\n', '\n'),
                    "client_email": os.getenv("GCP_SERVICE_ACCOUNT_EMAIL"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                creds = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
            elif self.credentials_file and os.path.exists(self.credentials_file):
                with open(self.credentials_file, 'r') as f:
                    credentials_info = json.load(f)
                creds = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
            else:
                raise ValueError("Credenciais não encontradas")
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            return creds.token
        except Exception as e:
            logger.error(f"Erro: {e}")
            raise

    async def update_enriched_data(self, enriched_data: List[Dict[str, Any]], fields: List[Any]) -> Dict[str, Any]:
        try:
            access_token = await self._get_access_token()
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            range_header = f"{self.SHEET_NAME}!1:1"
            url_get_header = f"{self.SHEETS_API_URL}/{self.SHEET_ID}/values/{range_header}"
            response = await self.client.get(url_get_header, headers=headers)
            response.raise_for_status()
            headers_row = response.json().get('values', [[]])[0]
            column_map = {header: idx for idx, header in enumerate(headers_row)}

            range_names = f"{self.SHEET_NAME}!A:A"
            url_get_names = f"{self.SHEETS_API_URL}/{self.SHEET_ID}/values/{range_names}"
            response = await self.client.get(url_get_names, headers=headers)
            response.raise_for_status()
            names_column = response.json().get('values', [])
            name_to_row = {row[0]: idx + 1 for idx, row in enumerate(names_column) if row and len(row) > 0}

            batch_data = []
            for enriched_item in enriched_data:
                if 'error' in enriched_item:
                    continue
                distro_name = enriched_item.get('Name')
                if not distro_name or distro_name not in name_to_row:
                    continue
                row_number = name_to_row[distro_name]
                for field in fields:
                    field_value = field.value
                    if field_value in enriched_item and field_value in column_map:
                        col_idx = column_map[field_value]
                        col_letter = self._get_column_letter(col_idx)
                        batch_data.append({'range': f"{self.SHEET_NAME}!{col_letter}{row_number}", 'values': [[enriched_item[field_value]]]})

            if batch_data:
                url_batch_update = f"{self.SHEETS_API_URL}/{self.SHEET_ID}/values:batchUpdate"
                response = await self.client.post(
                    url_batch_update,
                    json={"valueInputOption": "RAW", "data": batch_data},
                    headers=headers,
                )
                response.raise_for_status()
                return {'success': True, 'updated_cells': len(batch_data)}
            return {'success': False, 'message': 'Nenhum dado para atualizar'}
        except Exception as e:
            logger.error(f"Erro: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _get_column_letter(col_idx: int) -> str:
        result = ""
        while col_idx >= 0:
            result = chr(col_idx % 26 + 65) + result
            col_idx = col_idx // 26 - 1
        return result
