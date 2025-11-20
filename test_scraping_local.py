#!/usr/bin/env python3
"""
Teste de scraping usando páginas HTML salvas localmente em /url
"""

import json
import re
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime


def scrape_ranking_page_local(html_file: str, limit: int = 10):
    """Scrape página de ranking salva localmente."""
    print(f"\n📋 Lendo {html_file}...")
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    distros = []
    
    # Procurar por linhas com classe phr1 e phr2
    print(f"✅ Procurando distros na tabela...")
    
    rows_with_rank = soup.find_all('th', class_='phr1')
    
    for rank_cell in rows_with_rank:
        rank = int(rank_cell.get_text(strip=True))
        
        # Procurar próximo td com classe phr2
        name_cell = rank_cell.find_next_sibling('td', class_='phr2')
        
        if name_cell:
            link = name_cell.find('a')
            
            if link:
                name = link.get_text(strip=True)
                href = link.get('href', '')
                
                # Extrair slug da URL (formato: https://distrowatch.com/cachyos)
                match = re.search(r'distrowatch\.com/([a-z0-9_-]+)$', href)
                if match:
                    slug = match.group(1)
                    distros.append({
                        'rank': rank,
                        'name': name,
                        'slug': slug,
                        'html_file': f"url/DistroWatch.com_ {name}.html"
                    })
                    print(f"  [{rank}] {name} ({slug})")
                else:
                    print(f"  ⚠️  [{rank}] {name} - URL não reconhecida: {href}")
        
        if len(distros) >= limit:
            break
    
    print(f"\n✅ Total: {len(distros)} distros na lista\n")
    return distros


def scrape_distro_details_local(slug: str, html_file: str):
    """Scrape detalhes de uma distro de arquivo HTML local."""
    print(f"🔍 Parsing {html_file}...")
    
    if not Path(html_file).exists():
        print(f"  ❌ Arquivo não encontrado: {html_file}")
        return None
    
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Nome
        name = None
        h1 = soup.find('h1')
        if h1:
            name = h1.get_text(strip=True)
            print(f"  ✓ Nome: {name}")
        
        # Categoria
        category = None
        for li in soup.find_all('li'):
            b = li.find('b')
            if b and 'Categoria' in b.get_text():
                cats = [a.get_text(strip=True) for a in li.find_all('a')]
                category = ', '.join(cats)
                print(f"  ✓ Categoria: {category}")
                break
        
        # Data de lançamento
        release_date = None
        for th in soup.find_all('th'):
            if 'Data de Lançamento' in th.get_text():
                row = th.find_parent('tr')
                date_td = row.find('td', class_='Date')
                if date_td:
                    date_str = date_td.get_text(strip=True)
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        release_date = date_obj.strftime('%d/%m/%Y')
                        print(f"  ✓ Data de lançamento: {release_date}")
                    except:
                        release_date = date_str
                        print(f"  ✓ Data de lançamento (raw): {release_date}")
                break
        
        # Popularidade (4 semanas)
        popularity_rank = None
        popularity_hits = None
        for text_node in soup.find_all(string=re.compile(r'4 semanas')):
            full_text = text_node.parent.get_text()
            match = re.search(r'4 semanas:\s*(\d+)\s*\(([0-9,.]+)\)', full_text)
            if match:
                popularity_rank = int(match.group(1))
                hits_str = match.group(2).replace(',', '').replace('.', '')
                try:
                    popularity_hits = int(hits_str)
                except:
                    # Tentar formato brasileiro (1.234)
                    hits_str = match.group(2).replace('.', '')
                    popularity_hits = int(hits_str)
                print(f"  ✓ Popularidade: Rank #{popularity_rank} ({popularity_hits} hits/dia)")
                break
        
        # Rating
        rating = None
        for a_tag in soup.find_all('a', href=lambda x: x and 'ratings' in x):
            if 'Average visitor rating' in a_tag.get_text():
                parent = a_tag.parent
                if parent:
                    # Procurar próximo <b> após o link
                    for sibling in parent.next_siblings:
                        if hasattr(sibling, 'name') and sibling.name == 'b':
                            try:
                                rating_str = sibling.get_text(strip=True).replace(',', '.')
                                rating = float(rating_str)
                                print(f"  ✓ Rating: {rating}/10")
                            except Exception as e:
                                print(f"  ⚠️  Erro ao extrair rating: {e}")
                            break
                break
        
        result = {
            'id': slug,
            'name': name,
            'category': category,
            'release_date': release_date,
            'popularity_rank': popularity_rank,
            'popularity_hits': popularity_hits,
            'rating': rating,
            'source_file': html_file
        }
        
        print(f"  ✅ Sucesso!\n")
        return result
        
    except Exception as e:
        print(f"  ❌ Erro: {e}\n")
        return None


def main():
    """Executa teste completo de scraping."""
    print("\n" + "="*70)
    print("🧪 TESTE DE SCRAPING LOCAL - DistroWatch")
    print("="*70)
    
    # 1. Scrape página de ranking
    ranking_file = "url/popularity page"
    distros_list = scrape_ranking_page_local(ranking_file, limit=10)
    
    if not distros_list:
        print("❌ Nenhuma distro encontrada na página de ranking")
        return
    
    # 2. Scrape detalhes de cada distro encontrada
    print("\n" + "-"*70)
    print("📦 SCRAPING DE DETALHES")
    print("-"*70 + "\n")
    
    results = []
    for item in distros_list:
        details = scrape_distro_details_local(item['slug'], item['html_file'])
        if details:
            results.append(details)
    
    # 3. Salvar resultados
    output = {
        "scraped_at": datetime.utcnow().isoformat() + 'Z',
        "source": "local_html_files",
        "total": len(results),
        "distros": results
    }
    
    output_file = "test_scraping_local_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    # 4. Resumo
    print("\n" + "="*70)
    print("📊 RESUMO")
    print("="*70)
    print(f"✅ Distros encontradas no ranking: {len(distros_list)}")
    print(f"✅ Distros com detalhes extraídos: {len(results)}")
    print(f"✅ Taxa de sucesso: {len(results)/len(distros_list)*100:.1f}%")
    print(f"💾 Resultados salvos em: {output_file}")
    
    # 5. Mostrar amostra
    if results:
        print(f"\n📋 AMOSTRA DE DADOS (primeira distro):")
        print("-"*70)
        sample = results[0]
        for key, value in sample.items():
            print(f"  {key:20s}: {value}")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()
