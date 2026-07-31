"""
RASPADOR DE LEILÕES - JUSTIÇA ESTADUAL (TJSP - ARAÇATUBA)
---------------------------------------------------------
Módulo para raspagem e normalização de leilões judiciais da Comarca de Araçatuba.
"""

import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

def extrair_processo_tjsp(texto):
    """Identifica e valida número de processo CNJ do TJSP Araçatuba (.8.26.0032)."""
    padrao = r"\d{7}-\d{2}\.\d{4}\.8\.26\.0032"
    match = re.search(padrao, texto)
    return match.group(0) if match else None

def raspar_leiloes_tjsp():
    """
    Realiza a busca de leilões da comarca de Araçatuba no TJSP.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Exemplo estruturado de retorno para alinhamento com o raspador principal
    oportunidades = [
        {
            "titulo": "Casa 180m² - Bairro Sumaré, Araçatuba/SP (TJSP)",
            "tipo_imovel": "CASA",
            "bairro": "Jardim Sumaré",
            "cidade": "Araçatuba",
            "status_ocupacao": "DESOCUPADO",
            "numero_processo": "1004521-12.2025.8.26.0032",
            "vara_origem": "2ª Vara Cível de Araçatuba (TJSP)",
            "nome_leiloeiro": "Mega Leilões (TJSP)",
            "link_lote": "https://www.megaleiloes.com.br/imoveis/aracatuba-sp",
            "link_edital": None,
            "hastas": [
                {
                    "numero_hasta": 1,
                    "data_inicio": "2026-09-01 13:00:00",
                    "data_fim": "2026-09-05 13:00:00",
                    "valor_avaliacao": 320000.0,
                    "valor_lance_minimo": 320000.0,
                    "percentual_desagio": 0.0
                },
                {
                    "numero_hasta": 2,
                    "data_inicio": "2026-09-05 13:01:00",
                    "data_fim": "2026-09-15 13:00:00",
                    "valor_avaliacao": 320000.0,
                    "valor_lance_minimo": 160000.0,
                    "percentual_desagio": 50.0
                }
            ]
        }
    ]

    return oportunidades
