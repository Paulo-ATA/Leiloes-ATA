"""
RAIO-X DE LEILÕES (DIAGNÓSTICO ISOLADO)
-------------------------------------------------------------------
Script independente para descobrir onde a Mega Leilões esconde os valores.
"""

import requests
import re

def executar_raiox():
    url = "https://www.megaleiloes.com.br/imoveis/casas/sp/aracatuba/casa-107-m2-em-terreno-de-300-m2-uruamara-aracatuba-sp-j126874"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    print(f"📸 Tirando o Raio-X da página: {url}...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        html = response.text
        
        print("🔍 Procurando por padrões de valores (R$) escondidos no código...\n")

        matches = re.finditer(r".{0,80}R\$.{0,80}", html)
        encontrou = False

        for i, match in enumerate(matches):
            if i >= 20:
                print("... (Muitos resultados encontrados, exibindo apenas os 20 primeiros) ...")
                break
                
            texto_encontrado = match.group(0).strip()
            texto_limpo = re.sub(r'\s+', ' ', texto_encontrado) 
            
            print(f"--- Achado {i+1} ---")
            print(f"{texto_limpo}\n")
            encontrou = True

        if not encontrou:
            print("❌ NENHUM 'R$' ENCONTRADO! O site está bloqueando o robô ou usando uma API paralela.")

    except Exception as e:
        print(f"❌ Erro ao tentar acessar o site: {e}")

if __name__ == "__main__":
    executar_raiox()
