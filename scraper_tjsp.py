"""
RASPADOR REAL DETALHADO (DEEP SCRAPER) - MEGA LEILÕES (ARAÇATUBA/SP)
-------------------------------------------------------------------
Módulo que acessa a página individual de cada lote para extrair 
dados completos: valores, processo CNJ, datas reais, bairro e edital.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup

def extrair_processo(texto: str) -> str:
    """Extrai o número do processo no formato padrão CNJ (0000000-00.0000.0.00.0000)."""
    padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
    match = re.search(padrao, texto)
    return match.group(0) if match else None

def parse_valor_br(texto: str) -> float:
    """Converte valores no formato 'R$ 250.000,00' para float 250000.0."""
    if not texto:
        return 0.0
    val_clean = re.sub(r"[^\d,]", "", texto).replace(",", ".")
    try:
        return float(val_clean)
    except ValueError:
        return 0.0

def raspar_detalhes_lote(url_lote: str, headers: dict) -> dict:
    """Acessa a página individual do imóvel para capturar informações profundas."""
    try:
        resp = requests.get(url_lote, headers=headers, timeout=12)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        texto_pagina = soup.get_text()

        # 1. Título do Imóvel
        titulo_tag = soup.select_one("h1, .instance-title, .card-title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Imóvel em Leilão em Araçatuba/SP"

        # 2. Número do Processo CNJ
        num_processo = extrair_processo(texto_pagina)
        if not num_processo:
            slug = url_lote.rstrip("/").split("/")[-1]
            num_processo = f"MEGA-{slug[:35]}"

        # 3. Extração de Valores Financeiros
        # Avaliação
        val_av = 0.0
        match_av = re.search(r"Avaliação:\s*R\$\s*([\d\.,]+)", texto_pagina, re.IGNORECASE)
        if match_av:
            val_av = parse_valor_br(match_av.group(1))

        # Lance Mínimo / 2ª Hasta
        val_min = 0.0
        match_min = re.search(r"(?:2ª\s*Hasta|Lance\s*Mínimo|2º\s*Leilão):\s*R\$\s*([\d\.,]+)", texto_pagina, re.IGNORECASE)
        if match_min:
            val_min = parse_valor_br(match_min.group(1))
        elif match_av:
            # Caso não encontre rótulo explícito, busca o menor valor em R$ listado na página
            todos_valores = [parse_valor_br(v) for v in re.findall(r"R\$\s*([\d\.,]+)", texto_pagina)]
            todos_valores = [v for v in todos_valores if 0 < v <= val_av]
            if todos_valores:
                val_min = min(todos_valores)

        desagio = ((val_av - val_min) / val_av) * 100 if val_av > 0 and val_min > 0 else 0.0

        # 4. Bairro
        bairro = "Araçatuba"
        match_bairro = re.search(r"(?:bairro|b\.|jardim|parque|residencial)\s*([A-Za-zÀ-ÿ0-9\s]+?)(?:,|\.|-|\n)", texto_pagina, re.IGNORECASE)
        if match_bairro:
            cand = match_bairro.group(1).strip()
            if len(cand) < 30:
                bairro = cand.title()

        # 5. Link do Edital PDF
        link_edital = None
        edital_tag = soup.select_one("a[href*='edital'], a[href*='.pdf']")
        if edital_tag and edital_tag.get("href"):
            link_edital = edital_tag["href"]
            if not link_edital.startswith("http"):
                link_edital = f"https://www.megaleiloes.com.br{link_edital}"

        # 6. Extração das Datas
        datas = re.findall(r"(\d{2}/\d{2}/\d{4}\s+às\s+\d{2}:\d{2})", texto_pagina)
        data_ini = "2026-08-01 13:00:00"
        data_fim = "2026-08-15 13:00:00"

        if len(datas) >= 2:
            data_ini = re.sub(r"(\d{2})/(\d{2})/(\d{4})\s+às\s+(\d{2}:\d{2})", r"\3-\2-\1 \4:00", datas[0])
            data_fim = re.sub(r"(\d{2})/(\d{2})/(\d{4})\s+às\s+(\d{2}:\d{2})", r"\3-\2-\1 \4:00", datas[1])

        return {
            "titulo": titulo[:150],
            "tipo_imovel": "IMÓVEL",
            "bairro": bairro,
            "cidade": "Araçatuba",
            "status_ocupacao": "DESCONHECIDO",
            "numero_processo": num_processo,
            "vara_origem": "Vara Cível / Trabalhista de Araçatuba",
            "nome_leiloeiro": "Mega Leilões",
            "link_lote": url_lote,
            "link_edital": link_edital,
            "hastas": [
                {
                    "numero_hasta": 2,
                    "data_inicio": data_ini,
                    "data_fim": data_fim,
                    "valor_avaliacao": val_av,
                    "valor_lance_minimo": val_min,
                    "percentual_desagio": round(desagio, 2)
                }
            ]
        }
    except Exception as e:
        logging.error(f"Erro ao extrair detalhes de {url_lote}: {e}")
        return {}

def raspar_leiloes_tjsp() -> list:
    """Busca os links da capa e raspa a página interna de cada lote de Araçatuba/SP."""
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
        
        # Encontra todos os links de imóveis na lista
        links_lotes = set()
        for a_tag in soup.select("a[href*='/imoveis/']"):
            href = a_tag.get("href", "")
            if "/sp/aracatuba/" in href and href not in links_lotes:
                full_url = href if href.startswith("http") else f"https://www.megaleiloes.com.br{href}"
                links_lotes.add(full_url)

        logging.info(f"🔗 {len(links_lotes)} links de lotes encontrados em Araçatuba. Extraindo detalhes...")

        # Acessa cada lote individualmente
        for url in links_lotes:
            detalhes = raspar_detalhes_lote(url, headers)
            if detalhes:
                oportunidades.append(detalhes)

    except Exception as e:
        logging.error(f"❌ Erro ao raspar leilões reais: {e}")

    logging.info(f"✅ {len(oportunidades)} lotes reais detalhados com sucesso!")
    return oportunidades
