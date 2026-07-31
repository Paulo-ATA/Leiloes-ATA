"""
RASPADOR DE LEILÕES DE IMÓVEIS (ARAÇATUBA/SP) - TJSP & EXTRAJUDICIAL
-------------------------------------------------------------------
Captura e processa lotes da Mega Leilões para a cidade de Araçatuba/SP.
Exporta a função 'raspar_leiloes_tjsp' utilizada pelo 'scraper_aracatuba.py'.
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

def extrair_hastas_pagina(soup: BeautifulSoup, texto_pagina: str, val_avaliacao: float) -> list:
    """Extrai a tabela de 1ª e 2ª Praças com valores e datas corretas."""
    hastas = []

    # Procura padrões de 1ª e 2ª Praça / Hasta
    padrão_pracas = re.findall(
        r"(1ª|2ª)\s*(?:Praça|Hasta|Leilã[o0])[^\d]*?(\d{2}/\d{2}/\d{4}[^\n\r]*?\d{2}:\d{2})[^\d]*?R\$\s*([\d\.,]+)",
        texto_pagina,
        re.IGNORECASE
    )

    if padrão_pracas:
        for num_str, data_raw, valor_raw in padrão_pracas:
            num_hasta = 1 if "1" in num_str else 2
            v_lance = parse_valor_br(valor_raw)
            dt_iso = fmt_data_iso(data_raw)
            
            desagio = 0.0
            if val_avaliacao > 0 and v_lance > 0:
                desagio = round(((val_avaliacao - v_lance) / val_avaliacao) * 100, 2)

            hastas.append({
                "numero_hasta": num_hasta,
                "data_inicio": dt_iso,
                "data_fim": dt_iso,
                "valor_avaliacao": val_avaliacao,
                "valor_lance_minimo": v_lance,
                "percentual_desagio": max(desagio, 0.0)
            })

    # Tratamento para Leilões Extrajudiciais com "Valor inicial"
    if not hastas:
        match_ini = re.search(r"Valor\s+inicial[^\d]*?R\$\s*([\d\.,]+)", texto_pagina, re.IGNORECASE)
        match_data_fim = re.search(r"Data[^\d]*?(\d{2}/\d{2}/\d{4}[^\n\r]*?\d{2}:\d{2})", texto_pagina, re.IGNORECASE)

        v_lance = parse_valor_br(match_ini.group(1)) if match_ini else val_avaliacao
        dt_iso = fmt_data_iso(match_data_fim.group(1)) if match_data_fim else ""

        desagio = 0.0
        if val_avaliacao > 0 and v_lance > 0:
            desagio = round(((val_avaliacao - v_lance) / val_avaliacao) * 100, 2)

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
        texto_pagina = soup.get_text(separator=" ", strip=True)

        # 1. Título do Lote
        titulo_tag = soup.select_one("h1, .instance-title, .card-title")
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Imóvel em Leilão em Araçatuba/SP"

        # 2. Endereço e Bairro
        match_end = re.search(r"(?:Rua|Av|Avenida|Praça|Alameda)[^,\n]+,[^,\n]+,[^,\n]+, Araçatuba, SP", texto_pagina, re.IGNORECASE)
        endereco = match_end.group(0) if match_end else ""
        bairro = extrair_bairro(titulo, endereco)

        # 3. Natureza: Judicial vs. Extrajudicial
        is_extrajudicial = "extrajudicial" in texto_pagina.lower() or "comitente" in texto_pagina.lower()
        
        if is_extrajudicial:
            match_comitente = re.search(r"Comitente[^\w]*([A-Za-z0-9\s\.\-S\/A]+?)(?:Extrajudicial|Valor|Aberto|Datas|\n)", texto_pagina, re.IGNORECASE)
            comitente = match_comitente.group(1).strip() if match_comitente else "Instituição Financeira"
            slug = url_lote.rstrip("/").split("/")[-1]
            num_processo = f"EXTRA-{slug[:20]}"
            vara_origem = f"Alienação Fiduciária ({comitente})"
            debitos_subrogados = False
        else:
            match_proc = re.search(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", texto_pagina)
            num_processo = match_proc.group(0) if match_proc else "NÃO INFORMADO"

            match_vara = re.search(r"(\d+ª\s+Vara\s+[^\n,\.]+Comarca\s+de\s+Araçatuba/SP)", texto_pagina, re.IGNORECASE)
            vara_origem = match_vara.group(1).strip() if match_vara else "Vara Cível de Araçatuba/SP"
            debitos_subrogados = True

        # 4. Links Úteis (Edital em PDF)
        link_edital = None
        edital_tag = soup.find("a", href=re.compile(r"edital.*\.pdf", re.IGNORECASE))
        if edital_tag:
            link_edital = edital_tag["href"]
            if not link_edital.startswith("http"):
                link_edital = f"https://www.megaleiloes.com.br{link_edital}"

        # 5. Avaliação e Hastas
        match_av = re.search(r"Valor\s+de\s+Avalia[çc][ãa]o[^\d]*?R\$\s*([\d\.,]+)", texto_pagina, re.IGNORECASE)
        val_avaliacao = parse_valor_br(match_av.group(1)) if match_av else 0.0

        hastas = extrair_hastas_pagina(soup, texto_pagina, val_avaliacao)

        # 6. Débitos IPTU / Condomínio
        val_iptu = 0.0
        val_condo = 0.0

        return {
            "numero_processo": num_processo,
            "vara_origem": vara_origem,
            "titulo": titulo,
            "tipo_imovel": "IMÓVEL",
            "bairro": bairro,
            "cidade": "Araçatuba",
            "status_ocupacao": "DESCONHECIDO",
            "nome_leiloeiro": "Mega Leilões",
            "link_lote": url_lote,
            "link_edital": link_edital,
            "valor_debitos_iptu": val_iptu,
            "valor_debitos_condominio": val_condo,
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

# ------------------------------------------------------------------------------
# FUNÇÃO PRINCIPAL IMPORTADA PELO 'scraper_aracatuba.py'
# ------------------------------------------------------------------------------
def raspar_leiloes_tjsp(urls_alvo: list = None) -> list:
    """
    Função pública invocada pelo orquestrador.
    Se não receber uma lista de URLs, busca automaticamente os imóveis de Araçatuba.
    """
    if not urls_alvo:
        url_busca = "https://www.megaleiloes.com.br/imoveis/sp/aracatuba"
        try:
            resp = requests.get(url_busca, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=re.compile(r"/imoveis/.*aracatuba", re.IGNORECASE))
                urls_alvo = list(set([l["href"] for l in links if "href" in l.attrs]))
                # Garante URLs completas
                urls_alvo = [u if u.startswith("http") else f"https://www.megaleiloes.com.br{u}" for u in urls_alvo]
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
    # Teste local direto
    raspar_leiloes_tjsp()
