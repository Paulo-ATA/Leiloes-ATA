"""
RASPADOR REAL DETALHADO (DEEP SCRAPER) - MEGA LEILÕES (ARAÇATUBA/SP)
-------------------------------------------------------------------
Captura de dados imobiliários, processo CNJ, lance mínimo, datas, 
débitos (IPTU/Condomínio) e análise de sub-rogação legal.
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

def analisar_debitos_e_subrogacao(texto: str) -> tuple:
    """
    Identifica débitos de IPTU e condomínio e analisa cláusulas de sub-rogação.
    Retorna: (valor_iptu, valor_condominio, debitos_subrogados, obs_texto)
    """
    val_iptu = 0.0
    val_condo = 0.0

    # 1. IPTU e Débitos Fiscais
    match_iptu = re.search(
        r"(?:IPTU|d[eé]bitos?\s+fiscais?|d[íi]vida\s+ativa|prefeitura)[^\d]*?R\$\s*([\d\.,]+)",
        texto,
        re.IGNORECASE
    )
    if match_iptu:
        val_iptu = parse_valor_br(match_iptu.group(1))

    # 2. Débitos Condominiais
    match_condo = re.search(
        r"(?:condom[íi]nio|d[eé]bitos?\s+condominiais?)[^\d]*?R\$\s*([\d\.,]+)",
        texto,
        re.IGNORECASE
    )
    if match_condo:
        val_condo = parse_valor_br(match_condo.group(1))

    # 3. Análise do Termo de Sub-rogação / Responsabilidade
    subrogados = True  # Padrão legal genérico (Art. 130 CTN)

    # Expressões que indicam que o arrematante assumirá a dívida
    padrões_nao_subroga = [
        r"responsabilidade\s+do\s+arrematante",
        r"por\s+conta\s+do\s+arrematante",
        r"dever[áa]\s+ser\s+pago\s+pelo\s+arrematante",
        r"sem\s+sub-roga[çc][ãa]o",
        r"arrematante\s+responder[áa]"
    ]

    for pat in padrões_nao_subroga:
        if re.search(pat, texto, re.IGNORECASE):
            subrogados = False
            break

    # Se explicitamente citar sub-rogação ou Art. 130
    if re.search(r"(?:sub-roga(?:r[ãa]o|m-se)|art(?:igo|\.)?\s*130|ficar[ãa]o?\s+sub-rogados)", texto, re.IGNORECASE):
        subrogados = True

    # Monta texto descritivo explicativo
    obs_list = []
    if val_iptu > 0:
        obs_list.append(f"IPTU/Fiscal: R$ {val_iptu:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    if val_condo > 0:
        obs_list.append(f"Condomínio: R$ {val_condo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    regra = "Sub-rogados no preço da arrematação" if subrogados else "ALERT: Débitos por conta do ARREMATANTE"
    obs_list.append(f"Regra: {regra}")

    return val_iptu, val_condo, subrogados, " | ".join(obs_list)

def raspar_detalhes_lote(url_lote: str, headers: dict) -> dict:
    """Acessa a página individual do imóvel para capturar informações profundas."""
    try:
        resp = requests.get(url_lote, headers=headers, timeout=12)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        texto_pagina = soup.get_text(separator=" ", strip=True)

        # 1. Título do Imóvel
        titulo_tag = soup.select_one("h1, .instance-title, .card-title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Imóvel em Leilão em Araçatuba/SP"

        # 2. Número do Processo CNJ
        num_processo = extrair_processo(texto_pagina)
        if not num_processo:
            slug = url_lote.rstrip("/").split("/")[-1]
            num_processo = f"MEGA-{slug[:35]}"

        # 3. Análise Detalhada de Débitos e Sub-rogação
        val_iptu, val_condo, debitos_subrogados, obs_debitos = analisar_debitos_e_subrogacao(texto_pagina)

        # 4. Extração de Valores Financials (Avaliação e 2ª Hasta)
        val_av = 0.0
        val_min = 0.0

        # Captura da Avaliação
        match_av = re.search(r"Avalia[çc][ãa]o[^\d]*?R\$\s*([\d\.,]+)", texto_pagina, re.IGNORECASE)
        if match_av:
            val_av = parse_valor_br(match_av.group(1))

        # Captura do Lance Mínimo da 2ª Hasta
        match_min_2a = re.search(r"(?:2º\s*Leil[ãa]o|2ª\s*Hasta)[^R\$]*?R\$\s*([\d\.,]+)", texto_pagina, re.IGNORECASE)
        if match_min_2a:
            val_min = parse_valor_br(match_min_2a.group(1))

        # Descarte de falsos positivos (impede que o robô use valores de IPTU/condomínio como lance mínimo)
        if val_min > 0 and (val_min == val_iptu or val_min == val_condo or val_min < (val_av * 0.35)):
            val_min = 0.0

        # Regra de fallback caso o lance mínimo não venha estruturado no HTML
        if val_av > 0 and val_min == 0.0:
            todos_r = re.findall(r"R\$\s*([\d\.,]+)", texto_pagina)
            floats = sorted(list(set([parse_valor_br(v) for v in todos_r])))
            # Seleciona apenas valores plausíveis para lance mínimo (35% a 95% da avaliação)
            plausiveis = [v for v in floats if (val_av * 0.35) <= v < val_av and v != val_iptu and v != val_condo]
            if plausiveis:
                val_min = plausiveis[-1]
            else:
                # Regra padrão TJSP para 2ª hasta (60% do valor de avaliação)
                val_min = round(val_av * 0.60, 2)

        desagio = ((val_av - val_min) / val_av) * 100 if val_av > 0 and val_min > 0 else 0.0

        # 5. Bairro
        bairro = "Araçatuba"
        match_bairro = re.search(r"(?:bairro|b\.|jardim|parque|residencial)\s*([A-Za-zÀ-ÿ0-9\s]+?)(?:,|\.|-|\n)", texto_pagina, re.IGNORECASE)
        if match_bairro:
            cand = match_bairro.group(1).strip()
            if 3 <= len(cand) < 30 and not cand.isdigit():
                bairro = cand.title()

        # 6. Link do Edital PDF
        link_edital = None
        edital_tag = soup.select_one("a[href*='edital'], a[href*='.pdf']")
        if edital_tag and edital_tag.get("href"):
            link_edital = edital_tag["href"]
            if not link_edital.startswith("http"):
                link_edital = f"https://www.megaleiloes.com.br{link_edital}"

        # 7. Extração de Datas
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
            "valor_debitos_iptu": val_iptu,
            "valor_debitos_condominio": val_condo,
            "debitos_subrogados": debitos_subrogados,
            "observacoes_debitos": obs_debitos,
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
        
        links_lotes = set()
        for a_tag in soup.select("a[href*='/imoveis/']"):
            href = a_tag.get("href", "")
            if "/sp/aracatuba/" in href and href not in links_lotes:
                full_url = href if href.startswith("http") else f"https://www.megaleiloes.com.br{href}"
                links_lotes.add(full_url)

        logging.info(f"🔗 {len(links_lotes)} links de lotes encontrados em Araçatuba. Extraindo detalhes...")

        for url in links_lotes:
            detalhes = raspar_detalhes_lote(url, headers)
            if detalhes:
                oportunidades.append(detalhes)

    except Exception as e:
        logging.error(f"❌ Erro ao raspar leilões reais: {e}")

    logging.info(f"✅ {len(oportunidades)} lotes reais detalhados com sucesso!")
    return oportunidades
