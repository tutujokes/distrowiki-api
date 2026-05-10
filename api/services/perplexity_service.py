import os
import logging
import asyncio
from openai import OpenAI
from typing import List, Dict, Any, Optional
from enum import Enum
import json
import re

logger = logging.getLogger(__name__)

# Enum com campos da planilha que podem ser enriquecidos via IA
class SheetColumn(str, Enum):
    DESCRIPTION = "Description"
    IDLE_RAM_USAGE = "Idle RAM Usage"
    CPU_SCORE = "CPU Score"
    IO_SCORE = "I/O Score"
    REQUIREMENTS = "Requirements"
    OFFICE_SUITE = "Office Suite"
    CATEGORY = "Category"
    DESKTOP = "Desktop"
    IMAGE_SIZE = "Image Size"
    OS_TYPE = "OS Type"
    BASE = "Base"
    ORIGIN = "Origin"
    STATUS = "Status"
    PACKAGE_MANAGEMENT = "Package Management"
    RELEASE_DATE = "Release Date"
    LATEST_RELEASE = "Latest Release"
    WEBSITE = "Website"
    PRICE = "Price (R$)" 

# Descrições simplificadas para o prompt da IA (deixar o Sonar Reasoning Pro pensar)
FIELD_PROMPTS = {
    SheetColumn.DESCRIPTION: "uma descrição concisa em português da distribuição, destacando seu diferencial (máx. 200 caracteres)",
    SheetColumn.IDLE_RAM_USAGE: "uso de RAM em idle (MB) considerando o ambiente gráfico padrão. Retorne apenas o número inteiro.",
    SheetColumn.CPU_SCORE: "score de performance de CPU de 1.0 a 10.0. Retorne apenas um número decimal.",
    SheetColumn.IO_SCORE: "score de performance de I/O (disco) de 1.0 a 10.0. Retorne apenas um número decimal.",
    SheetColumn.REQUIREMENTS: "requisitos mínimos de HARDWARE para rodar (RAM/CPU/disco). Responda apenas: 'Leve' (funciona em PCs antigos com menos de 2GB RAM), 'Médio' (precisa de 2-4GB RAM e processador moderno), ou 'Alto' (precisa de 4GB+ RAM, GPU dedicada ou muito espaço em disco)",
    SheetColumn.OFFICE_SUITE: "suite de escritório padrão incluída (ex: LibreOffice, OnlyOffice, nenhuma)",
    SheetColumn.CATEGORY: "categoria principal: Desktop, Server, IoT, Education, Gaming, etc.",
    SheetColumn.DESKTOP: "ambiente desktop padrão (GNOME, KDE, XFCE, etc.)",
    SheetColumn.IMAGE_SIZE: "tamanho típico da ISO em GB",
    SheetColumn.OS_TYPE: "tipo do SO: Linux, BSD, etc.",
    SheetColumn.BASE: "distribuição base (Debian, Arch, Independent, etc.)",
    SheetColumn.ORIGIN: "país de origem da distribuição em português. Se incerto, retorne 'Internacional'.",
    SheetColumn.STATUS: "status: Active, Discontinued, Beta",
    SheetColumn.PACKAGE_MANAGEMENT: "gerenciador de pacotes principal (apt, pacman, dnf, etc.)",
    SheetColumn.RELEASE_DATE: "data do lançamento original da distribuição no formato DD/MM/AAAA",
    SheetColumn.LATEST_RELEASE: "data da versão mais recente no formato DD/MM/YYYY",
    SheetColumn.WEBSITE: "URL completa da homepage oficial.",
    SheetColumn.PRICE: "modelo de preço: 'Gratuito', 'Pago', 'Freemium' ou 'Doações'",
}

# Configuração da API Perplexity
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")


def validate_ram_idle(distro_name: str, desktop_env: str, ram_value: int) -> int:
    """Valida e corrige valores de RAM idle irrealistas.

    Args:
        distro_name: nome da distribuição
        desktop_env: ambiente gráfico (string)
        ram_value: valor retornado pela IA (MB)

    Returns:
        Valor inteiro de RAM em MB ajustado dentro do range esperado.
    """
    # Mapeamento de Desktop Environment para range esperado
    de_ranges = {
        'gnome': (900, 1600),
        'kde plasma': (800, 1400),
        'kde': (800, 1400),
        'xfce': (400, 700),
        'lxqt': (350, 600),
        'lxde': (300, 550),
        'mate': (600, 900),
        'cinnamon': (700, 1000),
        'budgie': (700, 1000),
        'i3': (300, 500),
        'sway': (300, 500),
        'openbox': (300, 500),
        'pantheon': (800, 1200),
        'deepin': (900, 1300),
    }

    de_lower = desktop_env.lower() if desktop_env else ''
    min_ram, max_ram = de_ranges.get(de_lower, (300, 2000))  # Range mais amplo por padrão

    # Se valor está fora do range, ajustar
    try:
        ram_int = int(ram_value)
    except Exception:
        logger.warning(f"{distro_name}: valor de RAM inválido recebido: {ram_value}. Usando mínimo {min_ram}")
        return min_ram

    if ram_int < min_ram:
        logger.warning(f"{distro_name}: RAM {ram_int} MB muito baixo, ajustando para {min_ram} MB")
        return min_ram

    if ram_int > max_ram:
        logger.warning(f"{distro_name}: RAM {ram_int} MB muito alto, ajustando para {max_ram} MB")
        return max_ram

    return ram_int


async def enrich_distros_with_perplexity(
    distro_names: List[str],
    fields: List[SheetColumn] = None,
    desktop_envs: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Enriquecimento dinâmico dos dados das distros via Perplexity API (Sonar Reasoning Pro).

    Args:
        distro_names: Lista de nomes das distribuições
        fields: Lista de colunas da planilha para enriquecer. Se None, usa campos padrão.
    """
    if fields is None or len(fields) == 0:
        # Default: apenas campos textuais/factuais (LLM é bom nisso)
        # Performance (CPU, I/O, RAM) agora vem de static_performance_data.py
        fields = [
            SheetColumn.DESCRIPTION,
            SheetColumn.DESKTOP,
            SheetColumn.CATEGORY,
            SheetColumn.REQUIREMENTS,
        ]

    results = []
    request_count = 0
    
    # Cliente Perplexity (compatível com OpenAI)
    client = OpenAI(
        api_key=PERPLEXITY_API_KEY,
        base_url="https://api.perplexity.ai"
    )
    
    for name in distro_names:
        # Rate limiting: esperar entre requests
        if request_count > 0:
            await asyncio.sleep(1.5)
        request_count += 1
        
        field_lines = [f'  "{field.value}": {FIELD_PROMPTS[field]}' for field in fields]

        # System prompt para forçar resposta JSON
        system_message = (
            "You are a Linux distribution data assistant. Your role is to provide structured JSON data "
            "about Linux distributions. You MUST always respond with valid JSON only, no explanations. "
            "When exact data is unavailable, provide reasonable estimates based on similar distributions, "
            "common benchmarks, and typical characteristics. Never refuse to provide data - always give your best estimate."
        )

        prompt = (
            f"Provide performance data for the Linux distribution '{name}' as JSON.\n\n"
            "RULES:\n"
            "1. Respond with ONLY a JSON object, no text before or after\n"
            "2. Use estimates when exact data is unavailable\n"
            "3. Never explain or refuse - just provide the JSON\n\n"
            "Return this exact structure:\n"
            "{\n" + ",\n".join(field_lines) + "\n}\n"
        )

        try:
            response = client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=800,
                temperature=0.3,
            )

            content = response.choices[0].message.content
            logger.info(f"{name}: Resposta bruta (primeiros 500 chars): {content[:500] if content else 'VAZIA'}")
            
            # Remover tags <think>...</think> se presentes
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
            
            # Limpar markdown code blocks
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content)
            content = content.strip()
            
            # Limpar markdown code blocks
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content)
            content = content.strip()

            # Tentar encontrar JSON - pode estar após texto de raciocínio
            # Procurar por qualquer bloco {...}
            match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL)
            
            if not match:
                # Tentar encontrar JSON mais agressivamente
                json_start = content.rfind("{")
                json_end = content.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    potential_json = content[json_start:json_end]
                    try:
                        enriched = json.loads(potential_json)
                        match = True  # Flag para prosseguir
                    except json.JSONDecodeError:
                        match = None
                        
            if match:
                if match is True:
                    # Já parseou acima
                    pass
                else:
                    enriched = json.loads(match.group())
                enriched["Name"] = name

                # 1. Pegar Desktop Environment da própria resposta da IA
                desktop_env = (
                    enriched.get("Desktop") or enriched.get("desktop") or ""
                )

                # 2. Validar RAM se presente (usar nome exato da chave)
                if "Idle RAM Usage" in enriched:
                    raw_value = enriched["Idle RAM Usage"]

                    # Extrair número do valor (pode vir como "1200 MB", "1200", etc)
                    try:
                        ram_digits = re.search(r"\d+", str(raw_value))
                        if ram_digits:
                            ram_val = int(ram_digits.group())
                        else:
                            ram_val = int(raw_value)
                    except:
                        logger.warning(
                            f"{name}: Valor de RAM inválido: {raw_value}"
                        )
                        ram_val = 800  # Default médio

                    # Aplicar validação
                    validated_ram = validate_ram_idle(name, desktop_env, ram_val)
                    enriched["Idle RAM Usage"] = validated_ram
                    logger.info(
                        f"{name} ({desktop_env}): RAM validado = {validated_ram} MB"
                    )

                # 3. Validar CPU Score se presente
                if "CPU Score" in enriched:
                    try:
                        cpu = float(enriched["CPU Score"])
                        enriched["CPU Score"] = round(max(1.0, min(10.0, cpu)), 1)
                    except:
                        enriched["CPU Score"] = 7.0

                # 4. Validar I/O Score se presente
                if "I/O Score" in enriched:
                    try:
                        io = float(enriched["I/O Score"])
                        enriched["I/O Score"] = round(max(1.0, min(10.0, io)), 1)
                    except:
                        enriched["I/O Score"] = 7.0

                results.append(enriched)
                logger.info(f"{name}: Enriquecido com sucesso -> {list(enriched.keys())}")
            else:
                logger.error(f"{name}: Não foi possível extrair JSON da resposta")
                results.append({"Name": name, "error": "Formato inesperado"})

        except Exception as e:
            logger.error(f"Erro ao enriquecer {name}: {e}")
            results.append({"Name": name, "error": str(e)})

    return results
