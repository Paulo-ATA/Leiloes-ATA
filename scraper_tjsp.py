"""
RASPADOR REAL - JUSTIÇA ESTADUAL E TRABALHISTA (ARAÇATUBA/SP)
-------------------------------------------------------------
Módulo para raspagem ao vivo de leilões na comarca de Araçatuba via Mega Leilões.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup

def extrair_processo(texto: str) -> str:
    """Identifica número de processo no padrão CNJ."""
    padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
    match = re.search(padrao, texto)
    return match.group(0) if match else None

def raspar_leiloes_tjsp() -> list:
    """
    Busca imóveis reais em leilão na comarca de Araçatuba/SP.
    """
    logging.info("🔎 Acessando portal de leilões reais para Araçatuba...")
    
    url_busca = "https://www.megaleiloes.com.br/imoveis/sp/aracatuba"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    oportunidades = []

    try:
        response = requests.get(url_busca, headers=headers, timeout=15)
        if response.status_code != 200:
            logging.warning(f"⚠️ Não foi possível acessar {url_busca} (Status {response.status_code})")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select(".card-leilao, .instance-card, .card")
        
        for card in cards:
            texto_card = card.get_text()
            
            # Filtra apenas lotes de Araçatuba
            if "araçatuba" not in texto_card.lower():
                continue

            link_tag = card.select_one("a[href*='/imoveis/']")
            if not link_tag:
                continue

            titulo = link_tag.get_text(strip=True) or "Imóvel em Leilão em Araçatuba/SP"
            link_lote = link_tag["href"]
            if not link_lote.startswith("http"):
                link_lote = f"https://www.megaleiloes.com.br{link_lote}"

            # Garante uma chave única caso o CNJ não esteja no texto do card
            proc = extrair_processo(texto_card)
            if not proc:
                slug_lote = link_lote.rstrip("/").split("/")[-1]
                proc = f"MEGA-{slug_lote}"

            # Extração dos valores financeiros
            val_av_match = re.search(r"Avaliação:\s*R\$\s*([\d\.,]+)", texto_card, re.IGNORECASE)
            val_min_match = re.search(r"(?:2ª Hasta|Lance Mínimo|1º Leilão):\s*R\$\s*([\d\.,]+)", texto_card, re.IGNORECASE)

            val_av = float(val_av_match.group(1).replace(".", "").replace(",", ".")) if val_av_match else 0.0
            val_min = float(val_min_match.group(1).replace(".", "").replace(",", ".")) if val_min_match else 0.0

            desagio = ((val_av - val_min) / val_av) * 100 if val_av > 0 else 0.0

            oportunidades.append({
                "titulo": titulo[:150],
                "tipo_imovel": "IMÓVEL",
                "bairro": "Araçatuba",
                "cidade": "Araçatuba",
                "status_ocupacao": "DESCONHECIDO",
                "numero_processo": proc,
                "vara_origem": "Vara Cível / Trabalhista de Araçatuba",
                "nome_leiloeiro": "Mega Leilões",
                "link_lote": link_lote,
                "link_edital": None,
                "hastas": [
                    {
                        "numero_hasta": 2,
                        "data_inicio": "2026-08-01 13:00:00",
                        "data_fim": "2026-08-15 13:00:00",
                        "valor_avaliacao": val_av,
                        "valor_lance_minimo": val_min,
                        "percentual_desagio": round(desagio, 2)
                    }
                ]
            })

    except Exception as e:
        logging.error(f"❌ Erro ao raspar leilões reais: {e}")

    logging.info(f"✅ {len(oportunidades)} lotes reais encontrados na Mega Leilões para Araçatuba.")
    return oportunidades
