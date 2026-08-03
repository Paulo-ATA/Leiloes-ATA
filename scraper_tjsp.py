"""
RASPADOR DE LEILÕES DE IMÓVEIS (ARAÇATUBA/SP) - TJSP & EXTRAJUDICIAL
-------------------------------------------------------------------
Versão Corrigida: Captura estruturada de praças/hastas, valores e datas.
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def parse_valor_br(texto_valor: str) -> float:
    """Converte valores no formato brasileiro 'R$ 123.456,78' para float."""
    if not texto_valor:
        return 0.0
    limpo = re.sub(r"[^\d,]", "", str(texto_valor)).replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return 0.0

def fmt_data_iso(data_str: str) -> str:
    """Converte datas para o formato ISO 'YYYY-MM-DD HH:MM:SS'."""
    if not data_str:
        return ""
    try:
        match = re.search(r"(\d{2}/\d{2}/\d{4})[^\d]*(\d{2}:\d{2})", data_str)
        if match:
            dt_raw = f"{match.group(1)} {match.group(2)}"
            dt = datetime.strptime(dt_raw, "%d/%m/%Y %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return data_str

def extrair_bairro(titulo: str, endereco: str) -> str:
    """Extrai o bairro priorizando a linha de endereço ou o título do lote."""
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

def extrair_hastas_pagina(texto_linhas: str, val_avaliacao: float) -> list:
    """
    Extrai 1ª e 2ª praça analisando a proximidade de datas e valores
    no texto com quebras de linha preservadas.
    """
    hastas = []

    # 1. Busca por 1ª Praça / 1º Leilão
    match_1a = re.search(
        r"(?:1ª|1º|1a)\s*(?:Praça|Hasta|Leilã[o0]|Praça/Hasta).*?(\d{2}/\d{2}/\d{4}[^\n\r]*?\d{2}:\d{2}).*?R\$\s*([\d\.,]+)",
        texto_linhas,
        re.IGNORECASE | re.DOTALL
    )
    if match_1a:
        dt_iso = fmt_data_iso(match_1a.group(1))
        v_lance = parse_valor_br(match_1a.group(2))
        desagio = round(((val_avaliacao - v_lance) / val_avaliacao) * 100, 2) if val_avaliacao > 0 else 0.0
        hastas.append({
            "numero_hasta": 1,
            "data_inicio": dt_iso,
            "data_fim": dt_iso,
            "valor_avaliacao": val_avaliacao,
            "valor_lance_minimo": v_lance,
            "percentual_desagio": max(desagio, 0.0)
        })

    # 2. Busca por 2ª Praça / 2º Leilão
    match_2a = re.search(
        r"(?:2ª|2º|2a)\s*(?:Praça|Hasta|Leilã[o0]|Praça/Hasta).*?(\d{2}/\d{2}/\d{4}[^\n\r]*?\d{2}:\d{2}).*?R\$\s*([\d\.,]+)",
        texto_linhas,
        re.IGNORECASE | re.DOTALL
    )
    if match_2a:
        dt_iso = fmt_data_iso(match_2a.group(1))
        v_lance = parse_valor_br(match_2a.group(2))
        desagio = round(((val_avaliacao - v_lance) / val_avaliacao) * 100, 2) if val_avaliacao > 0 else 0.0
        hastas.append({
            "numero_hasta": 2,
            "data_inicio": dt_iso,
            "data_fim": dt_iso,
            "valor_avaliacao": val_avaliacao,
            "valor_lance_minimo": v_lance,
            "percentual_desagio": max(desagio, 0.0)
        })

    # 3. Fallback para Leilões Extrajudiciais (Valor inicial)
    if not hastas:
        match_ini = re.search(r"Valor\s+inicial[^\d]*?R\$\s*([\d\.,]+)", texto_linhas, re.IGNORECASE)
        match_data = re.search(r"(?:Data|Encerramento|Fim)[^\d]*?(\d{2}/\d{2}/\d{4}[^\n\r]*?\d{2}:\d{2})", texto_linhas, re.IGNORECASE)

        if match_ini or match_data:
            v_lance = parse_valor_br(match_ini.group(1)) if match_ini else val_avaliacao
            dt_iso = fmt_data_iso(match_data.group(1)) if match_data else ""
            desagio = round(((val_avaliacao - v_lance) / val_avaliacao) * 100, 2) if val_avaliacao > 0 and v_lance > 0 else 0.0

            hastas.append({
                "numero_hasta": 2,
                "data_inicio": dt_iso,
                "data_fim": dt_iso,
                "valor_avaliacao": val_avaliacao,
                "valor_lance_minimo": v_lance,
                "percentual_desagio": max(desagio, 0.0)
            })

    return hastas

def raspar_detalhes_lote(url_lote: str) -> dict:
    """Raspagem minuciosa de uma página individual de lote."""
    try:
        resp = requests.get(url_lote, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Obtém texto preservando quebras de linha estruturais
        texto_linhas = soup.get_text("\n", strip=True)
        texto_limpo_linha = re.sub(r"[ \t]+", " ", texto_linhas)

        # 1. Título do Lote
        titulo_tag = soup.select_one("h1, .instance-title, .card-title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Imóvel em Leilão em Araçatuba/SP"

        # 2. Endereço e Bairro
        match_end = re.search(r"(?:Rua|Av|Avenida|Praça|Alameda)[^,\n]+,[^,\n]+,[^,\n]+, Araçatuba, SP", texto_limpo_linha, re.IGNORECASE)
        endereco = match_end.group(0) if match_end else ""
        bairro = extrair_bairro(titulo, endereco)

        # 3. Natureza: Judicial vs. Extrajudicial
        match_proc = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", texto_limpo_linha)
        is_extrajudicial = False if match_proc else ("extrajudicial" in titulo.lower() or "comitente" in texto_limpo_linha.lower())

        if is_extrajudicial:
            match_comitente = re.search(r"Comitente[^\w]*([A-Za-z0-9\s\.\-S\/A]+?)(?:Extrajudicial|Valor|Aberto|Datas|Início|\n)", texto_limpo_linha, re.IGNORECASE)
            comitente = match_comitente.group(1).strip() if match_comitente else "Instituição Financeira"
            slug = url_lote.split("?")[0].rstrip("/").split("/")[-1]
            num_processo = f"EXTRA-{slug[:20]}"
            vara_origem = f"Alienação Fiduciária ({comitente})"
            debitos_subrogados = False
        else:
            num_processo = match_proc.group(0) if match_proc else "NÃO INFORMADO"
            match_vara = re.search(r"(\d+ª\s+Vara\s+C[íi]vel[^\n,\.]*Comarca\s+de\s+Araçatuba/SP)", texto_limpo_linha, re.IGNORECASE)
            if match_vara:
                vara_origem = match_vara.group(1).strip()
            else:
                vara_origem = "Vara Cível de Araçatuba/SP"
            debitos_subrogados = True

        # 4. Links Úteis (Edital em PDF)
        link_edital = None
        edital_tag = soup.find("a", href=re.compile(r"edital.*\.pdf", re.IGNORECASE))
        if edital_tag:
            link_edital = edital_tag["href"]
            if not link_edital.startswith("http"):
                link_edital = f"https://www.megaleiloes.com.br{link_edital}"

        # 5. Valor de Avaliação
        match_av = re.search(r"Valor\s+de\s+Avalia[çc][ãa]o[^\d]*?R\$\s*([\d\.,]+)", texto_limpo_linha, re.IGNORECASE)
        val_avaliacao = parse_valor_br(match_av.group(1)) if match_av else 0.0

        # 6. Extração das Praças
        hastas = extrair_hastas_pagina(texto_limpo_linha, val_avaliacao)

        return {
            "numero_processo": num_processo,
            "vara_origem": vara_origem,
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
            "hastas_json": json.dumps(hastas, ensure_ascii=False)
        }

    except Exception as e:
        print(f"❌ Erro ao raspar detalhes de {url_lote}: {e}")
        return {}

def salvar_no_supabase(dados: dict):
    """Insere ou atualiza um imóvel no Supabase."""
    if not dados or not DATABASE_URL:
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        query = """
        INSERT INTO leiloes (
            numero_processo, vara_origem, titulo, tipo_imovel, bairro, cidade,
            status_ocupacao, nome_leiloeiro, link_lote, link_edital,
            valor_debitos_iptu, valor_debitos_condominio, debitos_subrogados,
            hastas_json, updated_at
        ) VALUES (
            %(numero_processo)s, %(vara_origem)s, %(titulo)s, %(tipo_imovel)s, %(bairro)s, %(cidade)s,
            %(status_ocupacao)s, %(nome_leiloeiro)s, %(link_lote)s, %(link_edital)s,
            %(valor_debitos_iptu)s, %(valor_debitos_condominio)s, %(debitos_subrogados)s,
            %(hastas_json)s, NOW()
        )
        ON CONFLICT (numero_processo) DO UPDATE SET
            titulo = EXCLUDED.titulo,
            bairro = EXCLUDED.bairro,
            vara_origem = EXCLUDED.vara_origem,
            link_edital = EXCLUDED.link_edital,
            valor_debitos_iptu = EXCLUDED.valor_debitos_iptu,
            valor_debitos_condominio = EXCLUDED.valor_debitos_condominio,
            debitos_subrogados = EXCLUDED.debitos_subrogados,
            hastas_json = EXCLUDED.hastas_json,
            updated_at = NOW();
        """
        cursor.execute(query, dados)
        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ Salvo no Supabase: {dados['titulo']}")

    except Exception as e:
        print(f"❌ Erro ao salvar no Supabase: {e}")

def raspar_leiloes_tjsp(urls_alvo: list = None) -> list:
    """Função invocada pelo orquestrador scraper_aracatuba.py."""
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
            salvar_no_supabase(dados)
            resultados.append(dados)

    return resultados

if __name__ == "__main__":
    raspar_leiloes_tjsp()
