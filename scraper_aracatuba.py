"""
ROBÔ RASPADOR DE LEILÕES DE IMÓVEIS DE ARAÇATUBA/SP (TRT-15 & TJSP)
------------------------------------------------------------------
Orquestrador Definitivo: Integração limpa, normalização e salvamento Supabase.
"""

import os
import re
import json
import logging
import datetime
from typing import Dict, List, Optional
import requests
import psycopg2
from psycopg2.extras import execute_values

from scraper_tjsp import raspar_leiloes_tjsp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper_leiloes.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

class AracatubaAuctionScraper:
    def __init__(self, db_connection_string: Optional[str] = None):
        self.db_conn_str = db_connection_string
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    @staticmethod
    def parse_date(date_str: str) -> Optional[str]:
        if not date_str:
            return None
        match = re.search(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}):(\d{2}))?", str(date_str))
        if match:
            day, month, year, hour, minute = match.groups()
            hour = hour if hour else "14"
            minute = minute if minute else "00"
            return f"{year}-{month}-{day} {hour}:{minute}:00"
        return str(date_str)

    @staticmethod
    def classify_property_type(title_or_desc: str) -> str:
        text = title_or_desc.upper()
        if "CASA" in text or "RESIDÊNCIA" in text or "SOBRADO" in text:
            return "CASA"
        elif "APARTAMENTO" in text or "APTO" in text or "CONDOMÍNIO" in text:
            return "APARTAMENTO"
        elif "TERRENO" in text or "LOTE" in text or "ÁREA URBANA" in text:
            return "TERRENO"
        elif "GALPÃO" in text or "BARRACÃO" in text or "PAVILHÃO" in text:
            return "GALPAO"
        elif "SÍTIO" in text or "FAZENDA" in text or "CHÁCARA" in text or "RURAL" in text:
            return "RURAL"
        elif "SALA" in text or "PREDIO" in text or "LOJA" in text or "COMERCIAL" in text:
            return "COMERCIAL"
        return "IMÓVEL"

    def fetch_aracatuba_lots(self) -> List[Dict]:
        logging.info("Iniciando varredura por leilões de Araçatuba/SP no TRT-15...")
        return []

    def normalizar_lotes_tjsp(self, imoveis_raw_tjsp: List[Dict]) -> List[Dict]:
        lotes_normalizados = []
        for item in imoveis_raw_tjsp:
            try:
                titulo = item.get("titulo", "Imóvel em Leilão em Araçatuba")
                bairro = item.get("bairro", "Araçatuba")
                
                hastas_normalizadas = []
                for h in item.get("hastas", []):
                    hastas_normalizadas.append({
                        "numero_hasta": h.get("numero_hasta", 2),
                        "data_inicio": self.parse_date(h.get("data_inicio")),
                        "data_fim": self.parse_date(h.get("data_fim")),
                        "valor_avaliacao": float(h.get("valor_avaliacao", 0.0)),
                        "valor_lance_minimo": float(h.get("valor_lance_minimo", 0.0)),
                        "percentual_desagio": float(h.get("percentual_desagio", 0.0))
                    })

                lote_dict = {
                    "imovel": {
                        "titulo": titulo,
                        "tipo_imovel": item.get("tipo_imovel") or self.classify_property_type(titulo),
                        "endereco": f"Araçatuba/SP - Bairro {bairro}",
                        "bairro": bairro,
                        "cidade": item.get("cidade", "Araçatuba"),
                        "uf": "SP",
                        "status_ocupacao": item.get("status_ocupacao", "DESCONHECIDO"),
                        "descricao_completa": titulo,
                    },
                    "leilao": {
                        "numero_processo": item.get("numero_processo", "Processo em Edital"),
                        "vara_origem": item.get("vara_origem", "Vara Cível / Trabalhista de Araçatuba"),
                        "tribunal": item.get("tribunal", "TJSP"),
                        "link_lote_leiloeiro": item.get("link_lote", ""),
                        "link_edital": item.get("link_edital"),
                        "link_laudo_avaliacao": item.get("link_laudo"),
                        "nome_leiloeiro": item.get("nome_leiloeiro", "Mega Leilões"),
                        "valor_debitos_iptu": float(item.get("valor_debitos_iptu", 0.0)),
                        "valor_debitos_condominio": float(item.get("valor_debitos_condominio", 0.0)),
                        "debitos_subrogados": bool(item.get("debitos_subrogados", True))
                    },
                    "hastas": hastas_normalizadas
                }
                lotes_normalizados.append(lote_dict)
            except Exception as e:
                logging.error(f"Erro ao normalizar lote: {e}")

        return lotes_normalizados

    def fetch_all_lots(self) -> List[Dict]:
        logging.info("🚀 Iniciando varredura geral de leilões reais em Araçatuba/SP...")
        lotes_trt15 = self.fetch_aracatuba_lots()
        
        try:
            raw_tjsp = raspar_leiloes_tjsp()
            lotes_tjsp = self.normalizar_lotes_tjsp(raw_tjsp)
            logging.info(f"Mega Leilões: {len(lotes_tjsp)} lotes reais processados para Araçatuba.")
        except Exception as e:
            logging.error(f"Falha ao executar raspagem da Mega Leilões: {e}")
            lotes_tjsp = []

        todos_os_lotes = lotes_trt15 + lotes_tjsp
        logging.info(f"📊 Total consolidado: {len(todos_os_lotes)} oportunidades reais em Araçatuba/SP.")
        return todos_os_lotes

    def export_to_json(self, data: List[Dict], filename: str = "leiloes_aracatuba.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"Dados exportados com sucesso para {filename}")

def salvar_no_banco(lotes: list):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.warning("⚠️ DATABASE_URL não configurada. Salvação em banco pulada.")
        return

    if not lotes:
        logging.info("ℹ️ Nenhum lote encontrado nesta execução para salvar.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        lotes_unicos = {}
        for item in lotes:
            proc_key = item["leilao"]["numero_processo"]
            lotes_unicos[proc_key] = item

        query = """
        INSERT INTO leiloes (
            numero_processo, tribunal, vara_origem, titulo, tipo_imovel,
            bairro, cidade, status_ocupacao, nome_leiloeiro,
            link_lote, link_edital, valor_debitos_iptu, valor_debitos_condominio,
            debitos_subrogados, hastas_json
        ) VALUES %s
        ON CONFLICT (numero_processo) DO UPDATE SET
            titulo = EXCLUDED.titulo,
            status_ocupacao = EXCLUDED.status_ocupacao,
            valor_debitos_iptu = EXCLUDED.valor_debitos_iptu,
            valor_debitos_condominio = EXCLUDED.valor_debitos_condominio,
            debitos_subrogados = EXCLUDED.debitos_subrogados,
            hastas_json = EXCLUDED.hastas_json,
            updated_at = NOW();
        """

        valores = []
        for item in lotes_unicos.values():
            imovel = item["imovel"]
            leilao = item["leilao"]
            valores.append((
                leilao["numero_processo"],
                leilao["tribunal"],
                leilao["vara_origem"],
                imovel["titulo"],
                imovel["tipo_imovel"],
                imovel["bairro"],
                imovel["cidade"],
                imovel["status_ocupacao"],
                leilao["nome_leiloeiro"],
                leilao["link_lote_leiloeiro"],
                leilao.get("link_edital"),
                leilao["valor_debitos_iptu"],
                leilao["valor_debitos_condominio"],
                leilao["debitos_subrogados"],
                json.dumps(item["hastas"])
            ))

        execute_values(cur, query, valores)
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"✅ {len(valores)} oportunidades reais salvas/atualizadas no Supabase com sucesso!")

    except Exception as e:
        logging.error(f"❌ Erro ao salvar dados no Supabase: {e}")

if __name__ == "__main__":
    scraper = AracatubaAuctionScraper()
    lotes = scraper.fetch_all_lots()
    scraper.export_to_json(lotes)
    salvar_no_banco(lotes)
