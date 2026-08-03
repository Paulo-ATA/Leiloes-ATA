"""
RASPADOR DE LEILÕES DE IMÓVEIS (ARAÇATUBA/SP) - TJSP & EXTRAJUDICIAL
-------------------------------------------------------------------
Versão 4: Substituição de Regex em bloco por varredura estrutural
(stripped_strings) atuando como "radar" de proximidade.
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")

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
        # Tenta casar Data + Hora
        match_dt = re.search(r"(\d{2}/\d{2}/\d{4})[^\d]*(\d{2}:\d{2})", data_str)
        if match_dt:
            dt = datetime.strptime(f"{match_dt.group(1)} {match_dt.group(2)}", "%d/%m/%Y %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Tenta casar apenas Data (fallback)
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

def extrair_hastas_pagina(textos_visiveis: list, val_avaliacao: float) -> list:
    """Extrai hastas varrendo a lista de textos visíveis por proximidade."""
    hastas = []
    
    data_1a = None
    valor_1a = 0.0
    data_2a = None
    valor_2a = 0.0

    # Varredura para Judicial (1ª e 2ª Praças)
    for i, texto in enumerate(textos_visiveis):
        texto_lower = texto.lower()

        # Gatilho: 1ª Praça
        if re.search(r"1[ªºa]\s*(pra[çc]a|leil[ãa]o|etapa)|primeiro\s+leil[ãa]o", texto_lower):
            for j in range(1, 16):
                if i + j < len(textos_visiveis):
                    if not data_1a and re.search(r"\d{2}/\d{2}/\d{4}", textos_visiveis[i+j]):
                        data_1a = fmt_data_iso(textos_visiveis[i+j])
                    if valor_1a == 0.0 and "R$" in textos_visiveis[i+j]:
                        valor_1a = parse_valor_br(textos_visiveis[i+j])

        # Gatilho: 2ª Praça
        if re.search(r"2[ªºa]\s*(pra[çc]a|leil[ãa]o|etapa)|segundo\s+leil[ãa]o", texto_lower):
            for j in range(1, 16):
                if i + j < len(textos_visiveis):
                    if not data_2a and re.search(r"\d{2}/\d{2}/\d{4}", textos_visiveis[i+j]):
                        data_2a = fmt_data_iso(textos_visiveis[i+j])
                    if valor_2a == 0.0 and "R$" in textos_visiveis[i+j]:
                        valor_2a = parse_valor_br(textos_visiveis[i+j])

    # Montagem do Judicial
    if data_1a or valor_1a > 0:
        desagio = round(((val_avaliacao - valor_1a) / val_avaliacao) * 100, 2) if val_avaliacao > 0 and valor_1a > 0 else 0.0
        hastas.append({
            "numero_hasta": 1,
            "data_inicio": data_1a or "",
            "data_fim": data_1a or "",
            "valor_avaliacao": val_avaliacao,
            "valor_lance_minimo": valor_1a if valor_1a > 0 else val_avaliacao,
            "percentual_desagio": max(desagio, 0.0)
        })

    if data_2a or valor_2a > 0:
        desagio = round(((val_avaliacao - valor_2a) / val_avaliacao) * 100, 2) if val_avaliacao > 0 and valor_2a > 0 else 0.0
        hastas.append({
            "numero_hasta": 2,
            "data_inicio": data_2a or "",
            "data_fim": data_2a or "",
            "valor_avaliacao": val_avaliacao,
            "valor_lance_minimo": valor_2a if valor_2a > 0 else val_avaliacao,
            "percentual_desagio": max(desagio, 0.0)
        })

    # Fallback para Extrajudicial (Hasta Única / Lance Inicial)
    if not hastas:
        data_unica = None
        valor_unico = 0.0
        
        for i, texto in enumerate(textos_visiveis):
            if "R$" in texto and valor_unico == 0.0:
                contexto_previo = " ".join(textos_visiveis[max(0, i-4):i+1]).lower()
                if any(t in contexto_previo for t in ["inicial", "mínimo", "atual", "lance", "partir"]):
                    valor_unico = parse_valor_br(texto)
            
            if not data_unica and re.search(r"\d{2}/\d{2}/\d{4}", texto):
                contexto_previo = " ".join(textos_visiveis[max(0, i-4):i+1]).lower()
                if any(t in contexto_previo for t in ["encerramento", "data", "fim", "leilão"]):
                    data_unica = fmt_data_iso(texto)

        if data_unica or valor_unico > 0:
            desagio = round(((val_avaliacao - valor_unico) / val_avaliacao) * 100, 2) if val_avaliacao > 0 and valor_unico > 0 else 0.0
            hastas.append({
                "numero_hasta": 1,
                "data_inicio": data_unica or "",
                "data_fim": data_unica or "",
                "valor_avaliacao": val_avaliacao,
                "valor_lance_minimo": valor_unico if valor_unico > 0 else val_avaliacao,
                "percentual_desagio": max(desagio, 0.0)
            })

    return hastas

def raspar_detalhes_lote(url_lote: str) -> dict:
    try:
        resp = requests.get(url_lote, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Lista estruturada de todos os fragmentos visíveis no site
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

        # Valor de Avaliação com varredura por radar
        val_avaliacao = 0.0
        val_elem = soup.select_one(".instance-valuation, .valor-avaliacao, .avaliacao")
        if val_elem:
            val_avaliacao = parse_valor_br(val_elem.get_text())

        if val_avaliacao == 0.0:
            for i, txt in enumerate(textos_visiveis):
                if re.search(r"avalia[çc][ãa]o", txt.lower()):
                    # Radar: Inspeciona até 6 fragmentos à frente buscando "R$"
                    for j in range(1, 7):
                        if i + j < len(textos_visiveis) and "R$" in textos_visiveis[i+j]:
                            val_avaliacao = parse_valor_br(textos_visiveis[i+j])
                            break
                    if val_avaliacao > 0:
                        break

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
            "hastas_json": json.dumps(hastas, ensure_ascii=False)
        }

    except Exception as e:
        print(f"❌ Erro ao raspar detalhes de {url_lote}: {e}")
        return {}

def salvar_no_supabase(dados: dict):
    if not dados or not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        query = """
        INSERT INTO leiloes (
            numero_processo, vara_origem, tribunal, titulo, tipo_imovel, bairro, cidade,
            status_ocupacao, nome_leiloeiro, link_lote, link_edital,
            valor_debitos_iptu, valor_debitos_condominio, debitos_subrogados,
            hastas_json, updated_at
        ) VALUES (
            %(numero_processo)s, %(vara_origem)s, %(tribunal)s, %(titulo)s, %(tipo_imovel)s, %(bairro)s, %(cidade)s,
            %(status_ocupacao)s, %(nome_leiloeiro)s, %(link_lote)s, %(link_edital)s,
            %(valor_debitos_iptu)s, %(valor_debitos_condominio)s, %(debitos_subrogados)s,
            %(hastas_json)s, NOW()
        )
        ON CONFLICT (numero_processo) DO UPDATE SET
            tribunal = EXCLUDED.tribunal,
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
