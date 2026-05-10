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

from api.main import app
from fastapi.staticfiles import StaticFiles

dist_path = Path(__file__).parent / "dist"
public_path = Path(__file__).parent / "public"

if dist_path.exists():
    app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="dist-assets")
    logger.info(f"✅ Arquivos estáticos de dist montados: {dist_path / 'assets'}")

if public_path.exists():
    app.mount("/public", StaticFiles(directory=public_path), name="public")
    logger.info(f"✅ Arquivos públicos montados: {public_path}")

__all__ = ["app"]

