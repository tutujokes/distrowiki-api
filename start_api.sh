#!/bin/bash

# Script para iniciar a API DistroWiki
# Uso: ./start_api.sh

echo -e "\n🚀 Iniciando DistroWiki API...\n"

# Verificar se está no diretório correto
if [ ! -f "api/main.py" ]; then
    echo "❌ Erro: Execute este script do diretório raiz do projeto"
    exit 1
fi

# Verificar se venv existe
if [ ! -f "venv/bin/python" ]; then
    echo "❌ Erro: Ambiente virtual não encontrado"
    echo "Execute: python3 -m venv venv"
    exit 1
fi

# Iniciar servidor
echo -e "📡 Iniciando servidor FastAPI..."
echo "   URL: http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo -e "\n⌨️  Pressione Ctrl+C para parar o servidor\n"

# Aguardar 3 segundos e abrir navegador
(sleep 3 && xdg-open "http://localhost:8000/docs") &

# Executar servidor
./venv/bin/python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000