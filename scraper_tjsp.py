"""
RASPADOR DE LEILÕES - JUSTIÇA ESTADUAL (TJSP - ARAÇATUBA)
---------------------------------------------------------
Módulo para raspagem e normalização de leilões judiciais da Comarca de Araçatuba.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")

def extrair_processo_tjsp(texto):
    """
    Identifica e valida número de processo CNJ do TJSP Araçatuba (.8.26.0032).
    """
    padrao = r"\d{7}-\d{2}\.\d{4}\.8\.26\.0032"
    match = re.search(padrao, texto)
    return match.group(0) if match else None

def raspar_leiloeiro_tjsp_exemplo(url_busca):
    """
    Exemplo genérico de extração de lote do TJSP filtrado por Araçatuba.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(url_busca, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ Erro ao acessar {url_busca}: Status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        oportunidades = []

        # Exemplo de iteração sobre cards de imóveis no HTML do leiloeiro
        # (Adapte os seletores CSS conforme o layout do site do leiloeiro alvo)
        for card in soup.select(".card-leilao, .item-lote"):
            cidade_texto = card.select_one(".cidade, .localizacao")
            
            # Garante a restrição geográfica estrita para Araçatuba
            if not cidade_texto or "araçatuba" not in cidade_texto.text.lower():
                continue

            titulo = card.select_one(".titulo, .descricao-curta").get_text(strip=True)
            link_lote = card.select_one("a")["href"]
            
            # Captura valores
            val_av = card.select_one(".valor-avaliacao").get_text(strip=True) if card.select_one(".valor-avaliacao") else "0"
            val_min = card.select_one(".lance-minimo").get_text(strip=True) if card.select_one(".lance-minimo") else "0"
            
            # Limpeza e conversão para float
            valor_avaliacao = float(re.sub(r"[^\d,]", "", val_av).replace(",", "."))
            valor_lance_minimo = float(re.sub(r"[^\d,]", "", val_min).replace(",", "."))
            
            desagio = ((valor_avaliacao - valor_lance_minimo) / valor_avaliacao) * 100 if valor_avaliacao > 0 else 0

            # Estrutura padronizada para o Supabase
            imovel_data = {
                "titulo": titulo,
                "tipo_imovel": "CASA",  # Ou lógica para identificar APARTAMENTO/TERRENO pelo texto
                "bairro": "Centro",     # Extraído do texto detalhado
                "cidade": "Araçatuba",
                "status_ocupacao": "DESCONHECIDO",
                "numero_processo": extrair_processo_tjsp(card.text) or "0000000-00.2026.8.26.0032",
                "vara_origem": "1ª Vara Cível de Araçatuba (TJSP)",
                "nome_leiloeiro": "Leiloeiro Homologado TJSP",
                "link_lote": link_lote,
                "link_edital": None,
                "hastas": [
                    {
                        "numero_hasta": 1,
                        "data_inicio": "2026-08-01 13:00:00",
                        "data_fim": "2026-08-10 13:00:00",
                        "valor_avaliacao": valor_avaliacao,
                        "valor_lance_minimo": valor_avaliacao,
                        "percentual_desagio": 0.0
                    },
                    {
                        "numero_hasta": 2,
                        "data_inicio": "2026-08-10 13:01:00",
                        "data_fim": "2026-08-20 13:00:00",
                        "valor_avaliacao": valor_avaliacao,
                        "valor_lance_minimo": valor_lance_minimo,
                        "percentual_desagio": round(desagio, 2)
                    }
                ]
            }
            
            oportunidades.append(imovel_data)

        return oportunidades

    except Exception as e:
        print(f"❌ Erro na raspagem TJSP: {e}")
        return []
