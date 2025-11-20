"""
DistroWiki API - Backend FastAPI

API para catálogo de distribuições Linux, conforme especificação do Módulo 1.
Fornece endpoints para listagem, filtros e comparação de distros.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes import distros_router, logo_router
from .scraping import scraping_router

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia ciclo de vida da aplicação.
    
    Executado na inicialização e encerramento do servidor.
    """
    # Startup
    logger.info("🚀 Iniciando DistroWiki API...")
    logger.info("📦 Módulo 1: Catálogo de Distros")
    
    yield
    
    # Shutdown
    logger.info("👋 Encerrando DistroWiki API...")


# Criar aplicação FastAPI
app = FastAPI(
    title="DistroWiki API",
    description="""
    API para catálogo de distribuições Linux.
    
    ## Módulo 1: Catálogo de Distros
    
    Fornece metadados de distribuições Linux obtidos do Wikidata e Wikipedia:
    - Nome, descrição, família/base
    - Ambientes gráficos disponíveis
    - Data de lançamento
    - Site oficial
    
    **Características:**
    - Cache de 24 horas
    - Atualização automática via cron
    - Filtros por família e ambiente gráfico
    - Paginação e ordenação
    
    **Fontes de Dados:**
    - Wikidata (SPARQL)
    - Wikipedia (fallback)
    
    ---
    
    **Projeto:** DistroWiki  
    **Licença:** MIT  
    **Repositório:** https://github.com/tutujokes/DistroWiki
    """,
    version="1.0.0",
    contact={
        "name": "DistroWiki Team",
        "url": "https://github.com/tutujokes/DistroWiki",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://distrowiki.vercel.app",
        "https://distrowiki.site",
        "https://www.distrowiki.site",
    ],
    allow_origin_regex=r"^https://.*\.(vercel\.app|lovable\.dev|lovableproject\.com|lovable\.app)$|^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Registrar rotas
app.include_router(distros_router)
app.include_router(logo_router)
app.include_router(scraping_router)


@app.get("/", tags=["Root"])
async def root():
    """
    Endpoint raiz da API.
    
    Retorna informações básicas sobre a API.
    """
    return {
        "name": "DistroWiki API",
        "version": "1.0.0",
        "module": "Módulo 1: Catálogo de Distros",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "distros": "/distros",
            "distro_detail": "/distros/{id}",
            "refresh_cache": "/distros/refresh",
            "cache_info": "/distros/cache/info"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Endpoint de health check.
    
    Útil para monitoramento e verificação de disponibilidade.
    """
    return {
        "status": "healthy",
        "module": "catalog",
        "cache_backend": "json"
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Handler global para exceções não tratadas.
    
    Evita exposição de stack traces em produção.
    """
    import traceback
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    
    # Em desenvolvimento, mostrar stack trace
    error_detail = str(exc)
    if hasattr(exc, '__traceback__'):
        error_detail = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erro interno do servidor",
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": error_detail if True else None  # Mostrar traceback temporariamente
        }
    )


# Para execução com uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
