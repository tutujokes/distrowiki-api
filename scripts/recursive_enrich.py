import subprocess
import sys
import os
import time

def run_enrich(distros=None):
    cmd = [".venv/bin/python", "scripts/enrich_distrowatch.py", "--update-sheet"]
    if distros:
        cmd.extend(["--distros", ",".join(distros)])
    
    print(f"\n[SUPERVISOR] Rodando enrichment para: {distros if distros else 'TODOS'}...")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    output = []
    failed_ids = []
    
    # Capturar IDs que falharam do log
    # Padrão: "[N/100] Scraping: id" seguido de "Nenhum dado encontrado" ou erro
    current_id = None
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        output.append(line)
        
        if "Scraping:" in line:
            current_id = line.split("Scraping:")[-1].strip()
        
        if "Nenhum dado encontrado" in line or "error" in line.lower() or "Erro ao processar" in line:
            if current_id and current_id not in failed_ids:
                failed_ids.append(current_id)
                
    process.wait()
    return failed_ids

def main():
    max_retries = 3
    retry_count = 0
    
    # Primeira rodada: todos
    failed = run_enrich()
    
    while failed and retry_count < max_retries:
        retry_count += 1
        print(f"\n{'='*50}")
        print(f"[SUPERVISOR] Tentativa de Re-run {retry_count}/{max_retries} para {len(failed)} distros que falharam.")
        print(f"[SUPERVISOR] Falhas: {', '.join(failed)}")
        print(f"{'='*50}\n")
        
        # Esperar um pouco para não ser bloqueado
        time.sleep(10)
        
        failed = run_enrich(distros=failed)
        
    if failed:
        print(f"\n[SUPERVISOR] FINALIZADO. As seguintes distros falharam após {max_retries} tentativas:")
        print(f"IDs: {', '.join(failed)}")
        print("Provavelmente erro de DOM ou bloqueio persistente.")
    else:
        print("\n[SUPERVISOR] SUCESSO TOTAL! Todas as distros foram processadas.")

if __name__ == "__main__":
    main()
