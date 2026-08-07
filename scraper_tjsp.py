"""
RASPADOR DE LEILÕES DE IMÓVEIS (ARAÇATUBA/SP) - TJSP & EXTRAJUDICIAL
-------------------------------------------------------------------
Versão Definitiva: Extração estruturada, robusta e desacoplada.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def parse_valor_br(texto_valor: str) -> float:
    if not texto_valor:
        return 0.0
    limpo = re.sub(r"[^\d,]", "", str(texto_valor)).replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0

def fmt_data_iso(data_str: str) -> str:
    if not data_str:
        return ""
    try:
        match_dt = re.search(r"(\d{2}/\d{2}/\d{4})[^\d]*(\d{2}:\d{2})", data_str)
        if match_dt:
            dt = datetime.strptime(f"{match_dt.group(1)} {match_dt.group(2)}", "%d/%m/%Y %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        
        match_d = re.search(r"(\d{2}/\d{2}/\d{4})", data_str)
        if match_d:
            dt = datetime.strptime(match_d.group(1), "%d/%m/%Y")
            return dt.strftime("%Y-%m-%d 00:00:00")
    except Exception:
        pass
    return data_str

def extrair_bairro(titulo: str, endereco: str) -> str:
    if endereco:
        partes_end = [p.strip() for p in endereco.split(",")]
        if len(partes_end) >= 4:
            candidato = partes_end[-3]
            if candidato.lower() not in ["sp", "araçatuba", "aracatuba", "centro"]:
                return candidato.title()
    if titulo:
        partes_tit = [p.strip() for p in titulo.split("-")]
        if len(partes_tit) >= 3:
            candidato = partes_tit[-2]
            if candidato.lower() not in ["sp", "araçatuba", "aracatuba"]:
                return candidato.title()
    return "Araçatuba"

import re
from bs4 import BeautifulSoup

def extrair_hastas_pagina(soup: BeautifulSoup, val_avaliacao: float) -> list:
    """
    Extrai as praças/hastas analisando a estrutura HTML específica da Mega Leilões.
    """
    hastas = []
    
    # Busca os blocos/cards de cada praça na página da Mega Leilões
    blocos_praca = soup.find_all(['div', 'section'], class_=re.compile(r'instance|praca|batch-instance', re.I))
    
    # Se encontrou blocos estruturados na página
    if blocos_praca:
        for idx, bloco in enumerate(blocos_praca, start=1):
            texto_bloco = bloco.get_text(separator=' ', strip=True)
            texto_lower = texto_bloco.lower()

            # Evita processar blocos irrelevantes
            if not any(k in texto_lower for k in ['1ª', '2ª', 'praça', 'leilão', 'lance mínimo', 'encerramento']):
                continue

            # Busca Data do leilão no bloco
            data_match = re.search(r'\d{2}/\d{2}/\d{4}', texto_bloco)
            data_hasta = fmt_data_iso(data_match.group(0)) if data_match else ""

            # Extrai valores monetários presentes EXCLUSIVAMENTE dentro deste bloco
            matches_valores = re.findall(r'(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})', texto_bloco)
            valores_bloco = [parse_valor_br(v) for v in matches_valores if parse_valor_br(v) > 0]

            if not valores_bloco:
                continue

            # Lógica de seleção do lance mínimo do bloco
            # Se houver mais de um valor, o lance mínimo é o menor valor significativo (evitando valores < 10.000 se o imóvel for grande)
            base_aval = val_avaliacao if val_avaliacao > 0 else max(valores_bloco)
            
            # Filtra valores que representam de fato o imóvel (ex: > 30% da avaliação para evitar pegar incrementos de R$ 2.000)
            valores_validos = [v for v in valores_bloco if v >= (base_aval * 0.30)]
            
            lance_minimo = min(valores_validos) if valores_validos else (min(valores_bloco) if valores_bloco else base_aval)

            desagio = round(((base_aval - lance_minimo) / base_aval) * 100, 2) if base_aval > 0 else 0.0

            hastas.append({
                "numero_hasta": idx,
                "data_inicio": data_hasta,
                "data_fim": data_hasta,
                "valor_avaliacao": base_aval,
                "valor_lance_minimo": lance_minimo,
                "percentual_desagio": max(desagio, 0.0)
            })

    # FALLBACK: Se o leilão for extrajudicial ou a estrutura HTML for simplificada (Hasta Única)
    if not hastas:
        texto_completo = soup.get_text(separator=' ', strip=True)
        
        # Procura por lance inicial/mínimo
        match_valor = re.search(r'(?:lance\s*m[íi]nimo|lance\s*inicial|a\s*partir\s*de)\s*:?\s*(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})', texto_completo, re.I)
        valor_unico = parse_valor_br(match_valor.group(1)) if match_valor else val_avaliacao
        
        data_match = re.search(r'\d{2}/\d{2}/\d{4}', texto_completo)
        data_unica = fmt_data_iso(data_match.group(0)) if data_match else ""

        base_aval = val_avaliacao if val_avaliacao > 0 else valor_unico

        hastas.append({
            "numero_hasta": 1,
            "data_inicio": data_unica,
            "data_fim": data_unica,
            "valor_avaliacao": base_aval,
            "valor_lance_minimo": valor_unico if valor_unico > 0 else base_aval,
            "percentual_desagio": 0.0
        })

    return hastas

def raspar_detalhes_lote(url_lote: str) -> dict:
    try:
        resp = requests.get(url_lote, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        textos_visiveis = list(soup.stripped_strings)
        texto_blocos = " | ".join(textos_visiveis)

        titulo_tag = soup.select_one("h1, .instance-title, .card-title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Imóvel em Leilão em Araçatuba/SP"

        match_end = re.search(r"(?:Rua|Av|Avenida|Praça|Alameda)[^|]+,[^|]+,[^|]+, Araçatuba, SP", texto_blocos, re.IGNORECASE)
        endereco = match_end.group(0) if match_end else ""
        bairro = extrair_bairro(titulo, endereco)

        match_proc = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", texto_blocos)
        is_extrajudicial = False if match_proc else ("extrajudicial" in titulo.lower() or "comitente" in texto_blocos.lower())

        if is_extrajudicial:
            match_comitente = re.search(r"Comitente(?:.*?\|\s*|\s*:\s*)([A-Za-z0-9\s\.\-S\/A]+?)(?:\s*\||\s+CNPJ)", texto_blocos, re.IGNORECASE)
            comitente = match_comitente.group(1).strip() if match_comitente else "Instituição Financeira"
            codigo_lote = url_lote.split("?")[0].rstrip("/").split("-")[-1].upper()
            num_processo = f"EXTRA-{codigo_lote}"
            vara_origem = f"Alienação Fiduciária ({comitente})"
            tribunal = "Extrajudicial"
            debitos_subrogados = False
        else:
            num_processo = match_proc.group(0) if match_proc else "NÃO INFORMADO"
            match_vara = re.search(r"(\d+ª\s+Vara\s+C[íi]vel.*?Comarca\s+de\s+Araçatuba(?:/SP)?)", texto_blocos, re.IGNORECASE)
            vara_origem = match_vara.group(1).strip() if match_vara else "Vara Cível de Araçatuba/SP"
            tribunal = "TJSP"
            debitos_subrogados = True

        link_edital = None
        edital_tag = soup.find("a", href=re.compile(r"edital.*\.pdf", re.IGNORECASE))
        if edital_tag:
            link_edital = edital_tag["href"]
            if not link_edital.startswith("http"):
                link_edital = f"https://www.megaleiloes.com.br{link_edital}"

        val_avaliacao = 0.0
        val_elem = soup.select_one(".instance-valuation, .valor-avaliacao, .avaliacao")
        if val_elem:
            val_avaliacao = parse_valor_br(val_elem.get_text())

        hastas = extrair_hastas_pagina(textos_visiveis, val_avaliacao)

        return {
            "numero_processo": num_processo,
            "vara_origem": vara_origem,
            "tribunal": tribunal,
            "titulo": titulo,
            "tipo_imovel": "IMÓVEL",
            "bairro": bairro,
            "cidade": "Araçatuba",
            "status_ocupacao": "DESCONHECIDO",
            "nome_leiloeiro": "Mega Leilões",
            "link_lote": url_lote.split("?")[0],
            "link_edital": link_edital,
            "valor_debitos_iptu": 0.0,
            "valor_debitos_condominio": 0.0,
            "debitos_subrogados": debitos_subrogados,
            "hastas": hastas  # Lista nativa pura para normalização no orquestrador
        }

    except Exception as e:
        print(f"❌ Erro ao raspar detalhes de {url_lote}: {e}")
        return {}

def raspar_leiloes_tjsp(urls_alvo: list = None) -> list:
    if not urls_alvo:
        url_busca = "https://www.megaleiloes.com.br/imoveis/sp/aracatuba"
        try:
            resp = requests.get(url_busca, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=re.compile(r"/imoveis/.*aracatuba", re.IGNORECASE))
                todas_urls = list(set([l["href"] for l in links if "href" in l.attrs]))
                urls_alvo = []
                for u in todas_urls:
                    u_completa = u if u.startswith("http") else f"https://www.megaleiloes.com.br{u}"
                    url_base = u_completa.split("?")[0]
                    if re.search(r"-[a-z0-9]+$", url_base, re.IGNORECASE):
                        urls_alvo.append(u_completa)
        except Exception as e:
            print(f"❌ Erro ao buscar lista de leilões: {e}")
            urls_alvo = []
            
    resultados = []
    for url in urls_alvo:
        print(f"🔍 Processando lote: {url}")
        dados = raspar_detalhes_lote(url)
        if dados:
            resultados.append(dados)
    return resultados
