#!/usr/bin/env python3
"""
Testa proxies um por um contra o DistroWatch para encontrar os que funcionam.
Usa CloudScraper e Playwright para bypass de proteções.
"""

import requests
import cloudscraper
import time
import json
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# URL de teste do DistroWatch
TEST_URL = "https://distrowatch.com/dwres.php?resource=popularity"

def load_proxy_lists():
    """Carrega as listas de proxies do GitHub."""
    print("🔄 Carregando listas de proxies...")
    
    proxy_lists = {
        'http': "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
        'socks5': "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
        'socks4': "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt"
    }
    
    all_proxies = []
    
    for proxy_type, url in proxy_lists.items():
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                proxies = response.text.strip().split('\n')
                count = 0
                for proxy in proxies:
                    proxy = proxy.strip()
                    if proxy and not proxy.startswith('#'):
                        all_proxies.append({
                            'type': proxy_type,
                            'address': proxy
                        })
                        count += 1
                print(f"  ✅ {count} proxies {proxy_type.upper()}")
        except Exception as e:
            print(f"  ❌ Erro ao carregar {proxy_type}: {e}")
    
    print(f"\n📊 Total: {len(all_proxies)} proxies carregados\n")
    return all_proxies

def test_proxy_cloudscraper(proxy_info, scraper, timeout=8):
    """
    Testa proxy usando CloudScraper.
    
    Args:
        proxy_info: Dict com 'type' e 'address'
        scraper: CloudScraper instance
        timeout: Timeout em segundos
    
    Returns:
        (success, status, method)
    """
    proxy_type = proxy_info['type']
    proxy_address = proxy_info['address']
    
    proxies = {
        'http': f'{proxy_type}://{proxy_address}',
        'https': f'{proxy_type}://{proxy_address}'
    }
    
    try:
        response = scraper.get(TEST_URL, proxies=proxies, timeout=timeout)
        
        if response.status_code == 200:
            if 'distrowatch' in response.text.lower() or 'Last 1 month' in response.text:
                return True, response.status_code, "CloudScraper"
        
        return False, response.status_code, "CloudScraper"
        
    except requests.exceptions.Timeout:
        return False, "TIMEOUT", "CloudScraper"
    except requests.exceptions.ProxyError:
        return False, "PROXY_ERROR", "CloudScraper"
    except requests.exceptions.SSLError:
        return False, "SSL_ERROR", "CloudScraper"
    except requests.exceptions.ConnectionError:
        return False, "CONNECTION_ERROR", "CloudScraper"
    except Exception as e:
        return False, str(type(e).__name__), "CloudScraper"

def test_proxy_playwright(proxy_info, playwright, timeout=8000):
    """
    Testa proxy usando Playwright (headless browser).
    
    Args:
        proxy_info: Dict com 'type' e 'address'
        playwright: Playwright instance
        timeout: Timeout em milissegundos
    
    Returns:
        (success, status, method)
    """
    proxy_type = proxy_info['type']
    proxy_address = proxy_info['address']
    
    # Playwright só suporta HTTP/HTTPS e SOCKS5
    if proxy_type not in ['http', 'socks5']:
        return False, "UNSUPPORTED", "Playwright"
    
    try:
        # Extrair host e porta
        parts = proxy_address.split(':')
        if len(parts) != 2:
            return False, "INVALID_FORMAT", "Playwright"
        
        server = parts[0]
        port = int(parts[1])
        
        # Configurar proxy
        proxy_config = {
            'server': f'{proxy_type}://{server}:{port}'
        }
        
        # Criar browser com proxy
        browser = playwright.chromium.launch(
            headless=True,
            proxy=proxy_config
        )
        
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        
        page = context.new_page()
        page.set_default_timeout(timeout)
        
        # Tentar acessar
        response = page.goto(TEST_URL, wait_until='domcontentloaded')
        
        # Verificar conteúdo
        content = page.content()
        
        browser.close()
        
        if response.status == 200:
            if 'distrowatch' in content.lower() or 'Last 1 month' in content:
                return True, 200, "Playwright"
        
        return False, response.status, "Playwright"
        
    except PlaywrightTimeout:
        return False, "TIMEOUT", "Playwright"
    except Exception as e:
        return False, str(type(e).__name__), "Playwright"

def main():
    print("=" * 70)
    print("🧪 TESTE DE PROXIES CONTRA DISTROWATCH")
    print("=" * 70)
    print()
    
    # Carregar proxies
    all_proxies = load_proxy_lists()
    
    if not all_proxies:
        print("❌ Nenhum proxy foi carregado!")
        return
    
    # Criar CloudScraper
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    # Testar proxies um por um
    working_proxies = []
    failed_count = 0
    
    print(f"🔍 Testando {len(all_proxies)} proxies (um por um)...")
    print(f"⏱️  Timeout: 8 segundos por proxy")
    print(f"🎯 URL de teste: {TEST_URL}")
    print(f"🔧 Métodos: CloudScraper + Playwright")
    print()
    print("-" * 70)
    
    start_time = time.time()
    
    # Inicializar Playwright
    with sync_playwright() as playwright:
        for i, proxy_info in enumerate(all_proxies, 1):
            proxy_str = f"{proxy_info['type']}://{proxy_info['address']}"
            
            print(f"[{i}/{len(all_proxies)}] {proxy_str[:45]}...", end=" ", flush=True)
            
            # Tentar com CloudScraper primeiro
            success, status, method = test_proxy_cloudscraper(proxy_info, scraper, timeout=8)
            
            # Se falhar com CloudScraper, tentar com Playwright
            if not success and proxy_info['type'] in ['http', 'socks5']:
                print(f"CS:{status} ", end="", flush=True)
                success, status, method = test_proxy_playwright(proxy_info, playwright, timeout=8000)
            
            if success:
                print(f"✅ OK ({method})")
                proxy_info['method'] = method
                working_proxies.append(proxy_info)
            else:
                print(f"❌ {status}")
                failed_count += 1
            
            # Pequeno delay entre testes
            time.sleep(0.3)
            
            # Mostrar progresso a cada 20 proxies
            if i % 20 == 0:
                elapsed = time.time() - start_time
                avg_time = elapsed / i
                remaining = (len(all_proxies) - i) * avg_time
                print(f"\n📊 Progresso: {i}/{len(all_proxies)} | "
                      f"✅ {len(working_proxies)} | "
                      f"❌ {failed_count} | "
                      f"⏱️  ~{remaining/60:.1f}min restantes\n")
    
    # Resultados finais
    elapsed_time = time.time() - start_time
    
    print()
    print("=" * 70)
    print("📊 RESULTADOS FINAIS")
    print("=" * 70)
    print(f"✅ Proxies funcionando: {len(working_proxies)}")
    print(f"❌ Proxies falharam: {failed_count}")
    print(f"📈 Taxa de sucesso: {len(working_proxies)/len(all_proxies)*100:.1f}%")
    print(f"⏱️  Tempo total: {elapsed_time/60:.1f} minutos")
    print()
    
    if working_proxies:
        print("🎯 Proxies funcionais por tipo:")
        for proxy_type in ['http', 'socks5', 'socks4']:
            type_count = len([p for p in working_proxies if p['type'] == proxy_type])
            if type_count > 0:
                print(f"  - {proxy_type.upper()}: {type_count}")
        
        # Salvar em arquivo JSON
        output = {
            'tested_at': datetime.utcnow().isoformat() + 'Z',
            'total_tested': len(all_proxies),
            'working_count': len(working_proxies),
            'success_rate': len(working_proxies) / len(all_proxies),
            'proxies': working_proxies
        }
        
        output_file = 'working_proxies_distrowatch.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Proxies funcionais salvos em: {output_file}")
        print(f"\n📝 Você pode usar esses proxies no scraper!")
    else:
        print("⚠️  Nenhum proxy funcional foi encontrado.")
        print("💡 Sugestões:")
        print("   - Tente novamente mais tarde (listas são atualizadas)")
        print("   - Use VPN ou outro método")
        print("   - Execute de outro local/rede")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Teste interrompido pelo usuário")
    except Exception as e:
        print(f"\n\n❌ Erro: {e}")
