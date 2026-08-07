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

def extrair_hastas_pagina(textos_visiveis: list, val_avaliacao: float) -> list:
    """
    Extrai hastas varrendo os textos visíveis com análise contextual de rótulos 
    (Lance Mínimo vs. Avaliação) e seleção de valor reduzido para 2ª praça.
    """
    hastas = []
    
    data_1a = None
    valor_1a = 0.0
    data_2a = None
    valor_2a = 0.0

    for i, texto in enumerate(textos_visiveis):
        texto_lower = texto.lower()

        # -------------------------------------------------------------
        # 1ª PRAÇA
        # -------------------------------------------------------------
        if re.search(r"1[ªºa]\s*(pra[çc]a|leil[ãa]o|etapa)|primeiro\s+leil[ãa]o", texto_lower):
            window = textos_visiveis[i+1 : min(i+25, len(textos_visiveis))]
            for idx, t in enumerate(window):
                # Data
                if not data_1a and re.search(r"\d{2}/\d{2}/\d{4}", t):
                    data_1a = fmt_data_iso(t)
                
                # Valor
                val = parse_valor_br(t)
                if val > 0 and ("," in t or "." in t) and not re.search(r"\d{2}/\d{2}/\d{4}", t):
                    ctx = " ".join(window[max(0, idx-2):idx+1]).lower()
                    if "avalia" not in ctx or valor_1a == 0.0:
                        if valor_1a == 0.0 or re.search(r"m[íi]nimo|lance", ctx):
                            valor_1a = val

        # -------------------------------------------------------------
        # 2ª PRAÇA
        # -------------------------------------------------------------
        if re.search(r"2[ªºa]\s*(pra[çc]a|leil[ãa]o|etapa)|segundo\s+leil[ãa]o", texto_lower):
            window = textos_visiveis[i+1 : min(i+25, len(textos_visiveis))]
            candidatos_valor_2a = []

            for idx, t in enumerate(window):
                if not data_2a and re.search(r"\d{2}/\d{2}/\d{4}", t):
                    data_2a = fmt_data_iso(t)
                
                val = parse_valor_br(t)
                if val > 0 and ("," in t or "." in t) and not re.search(r"\d{2}/\d{2}/\d{4}", t):
                    ctx = " ".join(window[max(0, idx-2):idx+1]).lower()
                    candidatos_valor_2a.append((val, ctx))

            # Raciocínio de escolha do valor da 2ª Praça:
            # 1ª Tentativa: Valor explicitamente associado a "mínimo" / "lance" (e sem "avaliação")
            for val, ctx in candidatos_valor_2a:
                if re.search(r"m[íi]nimo|lance|partir", ctx) and "avalia" not in ctx:
                    valor_2a = val
                    break

            # 2ª Tentativa: Se não achou por rótulo, pega o valor MENOR que a avaliação
            if valor_2a == 0.0 and candidatos_valor_2a:
                ref_aval = val_avaliacao if val_avaliacao > 0 else valor_1a
                valores_menores = [v for v, ctx in candidatos_valor_2a if 0 < v < ref_aval]
                
                if valores_menores:
                    valor_2a = valores_menores[0]
                else:
                    # Fallback: primeiro valor numérico da janela
                    valor_2a = candidatos_valor_2a[0][0]

    # Valor de referência para cálculo do deságio
    base_avaliacao = val_avaliacao if val_avaliacao > 0 else (valor_1a if valor_1a > 0 else valor_2a)

    # -------------------------------------------------------------
    # MONTAGEM DOS OBJETOS DE HASTA
    # -------------------------------------------------------------
    if data_1a or valor_1a > 0:
        val_lance_1 = valor_1a if valor_1a > 0 else base_avaliacao
        desagio_1 = round(((base_avaliacao - val_lance_1) / base_avaliacao) * 100, 2) if base_avaliacao > 0 else 0.0
        hastas.append({
            "numero_hasta": 1,
            "data_inicio": data_1a or "",
            "data_fim": data_1a or "",
            "valor_avaliacao": base_avaliacao,
            "valor_lance_minimo": val_lance_1,
            "percentual_desagio": max(desagio_1, 0.0)
        })

    if data_2a or valor_2a > 0:
        val_lance_2 = valor_2a if valor_2a > 0 else base_avaliacao
        desagio_2 = round(((base_avaliacao - val_lance_2) / base_avaliacao) * 100, 2) if base_avaliacao > 0 else 0.0
        hastas.append({
            "numero_hasta": 2,
            "data_inicio": data_2a or "",
            "data_fim": data_2a or "",
            "valor_avaliacao": base_avaliacao,
            "valor_lance_minimo": val_lance_2,
            "percentual_desagio": max(desagio_2, 0.0)
        })

    # -------------------------------------------------------------
    # FALLBACK: EXTRAJUDICIAL / HASTA ÚNICA
    # -------------------------------------------------------------
    if not hastas:
        data_unica = None
        valor_unico = 0.0
        for i, texto in enumerate(textos_visiveis):
            if valor_unico == 0.0:
                val = parse_valor_br(texto)
                contexto_previo = " ".join(textos_visiveis[max(0, i-4):i+1]).lower()
                if val > 0 and any(t in contexto_previo for t in ["inicial", "mínimo", "atual", "lance", "partir"]):
                    valor_unico = val
            if not data_unica and re.search(r"\d{2}/\d{2}/\d{4}", texto):
                contexto_previo = " ".join(textos_visiveis[max(0, i-4):i+1]).lower()
                if any(t in contexto_previo for t in ["encerramento", "data", "fim", "leilão"]):
                    data_unica = fmt_data_iso(texto)

        if data_unica or valor_unico > 0:
            base_unica = valor_unico if valor_unico > 0 else val_avaliacao
            hastas.append({
                "numero_hasta": 1,
                "data_inicio": data_unica or "",
                "data_fim": data_unica or "",
                "valor_avaliacao": base_unica,
                "valor_lance_minimo": valor_unico if valor_unico > 0 else base_unica,
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
