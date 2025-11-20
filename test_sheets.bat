@echo off
REM Script para testar Google Sheets no Windows

echo.
echo ========================================
echo  DistroWiki - Teste Google Sheets
echo ========================================
echo.

cd /d "%~dp0"

REM Ativar venv se existir
if exist venv\Scripts\activate.bat (
    echo [*] Ativando virtual environment...
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment ativado
    echo.
)

REM Rodar teste
echo [*] Testando conexão com Google Sheets...
echo.

python test_sheets.py

if errorlevel 1 (
    echo.
    echo [ERRO] Falha no teste
    echo.
    echo Possíveis soluções:
    echo 1. Verificar se a planilha é pública
    echo 2. Verificar ID da planilha
    echo 3. Verificar nome da aba
    echo.
    pause
) else (
    echo.
    echo [OK] Teste completado com sucesso!
    echo.
    pause
)
