"""
FastAPI Application Entry Point for Vercel

This is the main entry point that Vercel looks for when deploying a FastAPI application.
Vercel will automatically discover the 'app' variable and use it as the application.
"""

import sys
import os
import logging
from pathlib import Path

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Adicionar o diretório raiz ao path Python
sys.path.insert(0, os.path.dirname(__file__))

try:
    logger.info("Importando api.main...")
    from api.main import app
    
    # Montar arquivos estáticos
    from fastapi.staticfiles import StaticFiles
    
    dist_path = Path(__file__).parent / "dist"
    public_path = Path(__file__).parent / "public"
    
    if dist_path.exists():
        app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="dist-assets")
        logger.info(f"✅ Arquivos estáticos de dist montados: {dist_path / 'assets'}")
    
    if public_path.exists():
        app.mount("/public", StaticFiles(directory=public_path), name="public")
        logger.info(f"✅ Arquivos públicos montados: {public_path}")
    
    logger.info("✅ Aplicação FastAPI importada com sucesso!")
    
except Exception as e:
    logger.error(f"❌ Erro ao importar api.main: {e}", exc_info=True)
    
    # Fallback: criar app mínimo com informações de erro
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import traceback
    
    app = FastAPI()
    
    @app.get("/")
    async def root():
        return {
            "error": "Falha ao importar aplicação principal",
            "details": str(e),
            "traceback": traceback.format_exc()
        }
    
    @app.get("/api/distros")
    async def distros_error():
        return JSONResponse(
            status_code=500,
            content={
                "error": "API não está disponível - erro ao importar módulos",
                "details": str(e)
            }
        )

__all__ = ["app"]

