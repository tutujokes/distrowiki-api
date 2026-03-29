"""
Gerenciador de cache para dados da API.

Implementa cache em JSON com TTL de 24 horas, com suporte opcional
para Redis/KV para deploy em produção.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Any, Dict
from pathlib import Path
from upstash_redis import Redis

from ..models.distro import DistroMetadata

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        # Configuração
        self.cache_type = os.getenv("CACHE_TYPE", "file")  # 'file' ou 'redis'
        self.ttl = int(os.getenv("TTL_SECONDS", 86400))  # Padrão 24h
        self.cache_key = "distros_data"
        
        # Configuração Redis
        self.redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
        self.redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        
        self.redis_client = None
        if self.cache_type == "redis" and self.redis_url and self.redis_token:
            try:
                self.redis_client = Redis(url=self.redis_url, token=self.redis_token)
            except Exception as e:
                logger.error(f"Falha ao iniciar Redis: {e}. Voltando para arquivo.")
                self.cache_type = "file"

        # Configuração File (Fallback)
        self.cache_dir = Path("data/cache")
        self.cache_file = self.cache_dir / "distro_cache.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_distros_cache(self) -> Optional[List[DistroMetadata]]:
        """Recupera distros do cache se válido."""
        try:
            if self.cache_type == "redis" and self.redis_client:
                return self._get_from_redis()
            return self._get_from_file()
        except Exception as e:
            logger.error(f"Erro ao ler cache ({self.cache_type}): {e}")
            return None

    def get_distro_by_id(self, distro_id: str) -> Optional[DistroMetadata]:
        """Recupera uma única distro do cache por ID, sem carregar tudo."""
        try:
            # Redis: tenta buscar do hash individual primeiro
            if self.cache_type == "redis" and self.redis_client:
                data = self.redis_client.get(f"distro:{distro_id}")
                if data:
                    if isinstance(data, str):
                        return DistroMetadata(**json.loads(data))
                    return DistroMetadata(**data)
            
            # Fallback: carrega tudo e filtra
            all_distros = self.get_distros_cache()
            if all_distros:
                return next((d for d in all_distros if d.id == distro_id), None)
            return None
        except Exception as e:
            logger.error(f"Erro ao buscar distro {distro_id} do cache: {e}")
            return None

    def save_distros_cache(self, distros: List[DistroMetadata]):
        """Salva distros no cache."""
        try:
            data = [d.dict() for d in distros]
            
            if self.cache_type == "redis" and self.redis_client:
                self._save_to_redis(data)
                # Também salva índice individual por ID para lookups rápidos
                for d in distros:
                    try:
                        self.redis_client.set(
                            f"distro:{d.id}",
                            json.dumps(d.dict()),
                            ex=self.ttl
                        )
                    except Exception:
                        pass  # Não falhar por causa do índice
            else:
                self._save_to_file(data)
                
        except Exception as e:
            logger.error(f"Erro ao salvar cache ({self.cache_type}): {e}")

    def clear_cache(self):
        """Remove o cache."""
        try:
            if self.cache_type == "redis" and self.redis_client:
                self.redis_client.delete(self.cache_key)
                logger.info("Cache Redis limpo")
            
            # Sempre tenta limpar arquivo local também para garantir
            if self.cache_file.exists():
                self.cache_file.unlink()
                logger.info("Cache local limpo")
                
        except Exception as e:
            logger.error(f"Erro ao limpar cache: {e}")

    # --- Métodos Internos Redis ---
    
    def _get_from_redis(self) -> Optional[List[DistroMetadata]]:
        data = self.redis_client.get(self.cache_key)
        if not data:
            logger.info("Cache Redis vazio ou expirado")
            return None
            
        logger.info("Cache Redis encontrado (Hit)")
        # Upstash retorna string ou dict dependendo da versão/config, garantimos conversão
        if isinstance(data, str):
            json_data = json.loads(data)
        else:
            json_data = data
            
        return [DistroMetadata(**item) for item in json_data]

    def _save_to_redis(self, data: List[Dict[str, Any]]):
        # Salva como string JSON com tempo de expiração (ex)
        json_str = json.dumps(data)
        self.redis_client.set(self.cache_key, json_str, ex=self.ttl)
        logger.info(f"Dados salvos no Redis (TTL: {self.ttl}s)")

    # --- Métodos Internos File (Legado/Dev) ---

    def _get_from_file(self) -> Optional[List[DistroMetadata]]:
        if not self.cache_file.exists():
            return None
            
        # Verificar validade do arquivo (TTL)
        mtime = self.cache_file.stat().st_mtime
        age = datetime.now().timestamp() - mtime
        
        if age > self.ttl:
            logger.info(f"Cache local expirado ({age:.0f}s > {self.ttl}s)")
            return None
            
        logger.info("Lendo cache local")
        with open(self.cache_file, "r") as f:
            data = json.load(f)
            return [DistroMetadata(**item) for item in data]

    def _save_to_file(self, data: List[Dict[str, Any]]):
        with open(self.cache_file, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Dados salvos localmente em {self.cache_file}")
