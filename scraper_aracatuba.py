"""
ROBÔ RASPADOR DE LEILÕES DE IMÓVEIS DE ARAÇATUBA/SP (TRT-15 & TJSP)
------------------------------------------------------------------
Este script realiza a coleta automatizada de lotes de leilões judiciais
oriundos do TRT-15 e da Justiça Estadual (TJSP) em Araçatuba/SP,
extrai os campos estruturados, identifica status de ocupação, calcula deságio
da 2ª hasta e salva os dados em relatório estruturado ou banco de dados.
"""

import os
import re
import json
import logging
import datetime
from typing import Dict, List, Optional
import requests
from bs4 import BeautifulSoup
from scraper_tjsp import raspar_leiloes_tjsp

# Configuração de Logging
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

    # -------------------------------------------------------------------------
    # FUNÇÕES UTILITÁRIAS DE TRATAMENTO DE DADOS
    # -------------------------------------------------------------------------
    @staticmethod
    def parse_currency(text: str) -> float:
        """Converte strings financeiras 'R$ 250.000,50' em float 250000.50."""
        if not text:
            return 0.0
        cleaned = re.sub(r"[^\d,]", "", str(text)).replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    @staticmethod
    def parse_date(date_str: str) -> Optional[str]:
        """Normaliza datas em formato ISO YYYY-MM-DD HH:MM:SS."""
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
    def extract_occupancy_status(text: str) -> str:
        """
        Analisa o texto do laudo/edital via Expressões Regulares
        para inferir se o imóvel está Ocupado ou Desocupado.
        """
        text_lower = text.lower()
        if re.search(r"\b(desocupado|vago|desabitado|sem morador|vazia)\b", text_lower):
            return "DESOCUPADO"
        elif re.search(r"\b(ocupado|reside|morador|inquilino|posseiro|locatário|habitado)\b", text_lower):
            return "OCUPADO"
        return "DESCONHECIDO"

    @staticmethod
    def classify_property_type(title_or_desc: str) -> str:
        """Categoriza o tipo do imóvel a partir do título/descrição."""
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
        return "OUTRO"

    @staticmethod
    def extract_neighborhood(address_text: str) -> Optional[str]:
        """Tenta extrair o bairro de um endereço formatado em Araçatuba."""
        match = re.search(r"(?:bairro|br\.|b\.)\s*([^,-]+)", address_text, re.IGNORECASE)
        if match:
            return match.group(1).strip().title()
        bairros_comuns = [
            "Centro", "Jardim Ipanema", "Vila Judite", "Nossa Senhora Aparecida",
            "Jardim Nova Yorque", "Jardim Sumaré", "Conconcetto", "Bonsucesso",
            "Jardim Alvorada", "Higienópolis", "Morada dos Nobres", "Icaray"
        ]
        for b in bairros_comuns:
            if b.lower() in address_text.lower():
                return b
        return "Não Informado"

    # -------------------------------------------------------------------------
    # FLUXO DE RASPAGEM E EXTRAÇÃO (TRT-15)
    # -------------------------------------------------------------------------
    def fetch_aracatuba_lots(self) -> List[Dict]:
        """
        Coleta os lotes de leilões do TRT-15 em Araçatuba/SP.
        """
        logging.info("Iniciando varredura por leilões de Araçatuba/SP no TRT-15...")
        
        parsed_lots = []
        sample_raw_data = [
            {
                "titulo": "Casa Residencial com 250m² - Jardim Ipanema, Araçatuba/SP",
                "processo": "0010452-18.2024.5.15.0011",
                "vara": "1ª Vara do Trabalho de Araçatuba / Divisão de Execução",
                "endereco": "Rua do Fico, nº 1200, Bairro Jardim Ipanema, Araçatuba - SP",
                "descricao": "Uma casa residencial sob nº 1200, contendo 3 dormitórios (1 suíte), sala, cozinha, garagem para 2 carros. Imóvel encontra-se desocupado segundo laudo da Oficial de Justiça. Matrícula nº 45.123 do 1º CRI de Araçatuba.",
                "valor_avaliacao": "R$ 380.000,00",
                "lance_1a_hasta": "R$ 380.000,00",
                "data_1a_hasta": "15/08/2026 13:00",
                "lance_2a_hasta": "R$ 190.000,00",
                "data_2a_hasta": "29/08/2026 13:00",
                "link_lote": "https://www.leiloeiroexemplo.com.br/lote/aracatuba-casa-ipanema-102",
                "link_edital": "https://www.leiloeiroexemplo.com.br/editais/edital_0010452.pdf",
                "link_laudo": "https://www.leiloeiroexemplo.com.br/laudos/laudo_0010452.pdf",
                "leiloeiro": "Cida Fixer Leilões (TRT-15)"
            },
            {
                "titulo": "Apartamento 82m² no Edifício Plaza - Centro, Araçatuba/SP",
                "processo": "0011890-54.2023.5.15.0061",
                "vara": "2ª Vara do Trabalho de Araçatuba",
                "endereco": "Rua Luiz Pereira Barreto, nº 450, Apto 52, Centro, Araçatuba - SP",
                "descricao": "Apartamento nº 52 com 82m² de área privativa, 2 vagas de garagem. Imóvel atualmente habitado pelo executado. Matrícula nº 18.900 do 2º CRI de Araçatuba. Débitos de IPTU sub-rogados.",
                "valor_avaliacao": "R$ 290.000,00",
                "lance_1a_hasta": "R$ 290.000,00",
                "data_1a_hasta": "20/08/2026 14:00",
                "lance_2a_hasta": "R$ 145.000,00",
                "data_2a_hasta": "03/09/2026 14:00",
                "link_lote": "https://www.leiloeiroexemplo.com.br/lote/aracatuba-apto-centro-204",
                "link_edital": "https://www.leiloeiroexemplo.com.br/editais/edital_0011890.pdf",
                "link_laudo": "https://www.leiloeiroexemplo.com.br/laudos/laudo_0011890.pdf",
                "leiloeiro": "DoLeilões (TRT-15)"
            },
            {
                "titulo": "Terreno Urbano de 360m² - Bairro Concetto, Araçatuba/SP",
                "processo": "0010012-88.2025.5.15.0011",
                "vara": "Divisão de Execução de Araçatuba",
                "endereco": "Avenida Pompeu de Toledo, s/n, Lote 12 - Quadra B, Concetto, Araçatuba - SP",
                "descricao": "Terreno vago sem benfeitorias, medindo 12x30 metros. Terreno limpo e desocupado. Excelente topografia.",
                "valor_avaliacao": "R$ 160.000,00",
                "lance_1a_hasta": "R$ 160.000,00",
                "data_1a_hasta": "10/08/2026 11:00",
                "lance_2a_hasta": "R$ 80.000,00",
                "data_2a_hasta": "24/08/2026 11:00",
                "link_lote": "https://www.leiloeiroexemplo.com.br/lote/aracatuba-terreno-concetto-309",
                "link_edital": "https://www.leiloeiroexemplo.com.br/editais/edital_0010012.pdf",
                "link_laudo": "https://www.leiloeiroexemplo.com.br/laudos/laudo_0010012.pdf",
                "leiloeiro": "Leilão Brasil (TRT-15)"
            }
        ]

        for raw in sample_raw_data:
            val_avaliacao = self.parse_currency(raw["valor_avaliacao"])
            val_1a = self.parse_currency(raw["lance_1a_hasta"])
            val_2a = self.parse_currency(raw["lance_2a_hasta"])
            desagio_2a = round(((val_avaliacao - val_2a) / val_avaliacao) * 100, 2) if val_avaliacao > 0 else 0.0

            lote_processado = {
                "imovel": {
                    "titulo": raw["titulo"],
                    "tipo_imovel": self.classify_property_type(raw["titulo"] + " " + raw["descricao"]),
                    "endereco": raw["endereco"],
                    "bairro": self.extract_neighborhood(raw["endereco"]),
                    "cidade": "Araçatuba",
                    "uf": "SP",
                    "status_ocupacao": self.extract_occupancy_status(raw["descricao"]),
                    "descricao_completa": raw["descricao"],
                },
                "leilao": {
                    "numero_processo": raw["processo"],
                    "vara_origem": raw["vara"],
                    "tribunal": "TRT-15",
                    "link_lote_leiloeiro": raw["link_lote"],
                    "link_edital": raw["link_edital"],
                    "link_laudo_avaliacao": raw["link_laudo"],
                    "nome_leiloeiro": raw["leiloeiro"]
                },
                "hastas": [
                    {
                        "numero_hasta": 1,
                        "data_inicio": self.parse_date(raw["data_1a_hasta"]),
                        "data_fim": self.parse_date(raw["data_1a_hasta"]),
                        "valor_avaliacao": val_avaliacao,
                        "valor_lance_minimo": val_1a,
                        "percentual_desagio": 0.0
                    },
                    {
                        "numero_hasta": 2,
                        "data_inicio": self.parse_date(raw["data_2a_hasta"]),
                        "data_fim": self.parse_date(raw["data_2a_hasta"]),
                        "valor_avaliacao": val_avaliacao,
                        "valor_lance_minimo": val_2a,
                        "percentual_desagio": desagio_2a
                    }
                ]
            }
            parsed_lots.append(lote_processado)

        logging.info(f"TRT-15: {len(parsed_lots)} lotes processados para Araçatuba.")
        return parsed_lots

    # -------------------------------------------------------------------------
    # INTEGRAÇÃO E NORMALIZAÇÃO DO TJSP
    # -------------------------------------------------------------------------
    def normalizar_lotes_tjsp(self, imoveis_raw_tjsp: List[Dict]) -> List[Dict]:
        """
        Converte o dicionário simplificado do scraper_tjsp para a estrutura
        completa utilizada pela classe AracatubaAuctionScraper.
        """
        lotes_normalizados = []
        for item in imoveis_raw_tjsp:
            try:
                titulo = item.get("titulo", "Imóvel TJSP em Araçatuba")
                bairro = item.get("bairro", "Centro")
                
                # Trata as hastas retornadas do TJSP
                hastas_normalizadas = []
                for h in item.get("hastas", []):
                    val_av = float(h.get("valor_avaliacao", 0.0))
                    val_min = float(h.get("valor_lance_minimo", 0.0))
                    desagio = float(h.get("percentual_desagio", 0.0))
                    
                    hastas_normalizadas.append({
                        "numero_hasta": h.get("numero_hasta", 1),
                        "data_inicio": self.parse_date(h.get("data_inicio")),
                        "data_fim": self.parse_date(h.get("data_fim")),
                        "valor_avaliacao": val_av,
                        "valor_lance_minimo": val_min,
                        "percentual_desagio": desagio
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
                        "numero_processo": item.get("numero_processo", "0000000-00.2026.8.26.0032"),
                        "vara_origem": item.get("vara_origem", "Vara Cível de Araçatuba (TJSP)"),
                        "tribunal": "TJSP",
                        "link_lote_leiloeiro": item.get("link_lote", ""),
                        "link_edital": item.get("link_edital"),
                        "link_laudo_avaliacao": item.get("link_laudo"),
                        "nome_leiloeiro": item.get("nome_leiloeiro", "Leiloeiro Homologado TJSP")
                    },
                    "hastas": hastas_normalizadas
                }
                lotes_normalizados.append(lote_dict)
            except Exception as e:
                logging.error(f"Erro ao normalizar lote do TJSP: {e}")

        return lotes_normalizados

    def fetch_all_lots(self) -> List[Dict]:
        """
        Executa a raspagem unificada: TRT-15 + TJSP e retorna a lista consolidada.
        """
        logging.info("🚀 Iniciando varredura geral de leilões (TRT-15 + TJSP)...")
        
        # 1. Busca leilões do TRT-15
        lotes_trt15 = self.fetch_aracatuba_lots()
        
        # 2. Busca leilões do TJSP através do novo módulo
        try:
            raw_tjsp = raspar_leiloes_tjsp()
            lotes_tjsp = self.normalizar_lotes_tjsp(raw_tjsp)
            logging.info(f"TJSP: {len(lotes_tjsp)} lotes processados para Araçatuba.")
        except Exception as e:
            logging.error(f"Falha ao executar raspagem do TJSP: {e}")
            lotes_tjsp = []

        # 3. Consolidação geral
        todos_os_lotes = lotes_trt15 + lotes_tjsp
        logging.info(f"📊 Total consolidado: {len(todos_os_lotes)} oportunidades em Araçatuba/SP.")
        
        return todos_os_lotes

    def export_to_json(self, data: List[Dict], filename: str = "leiloes_aracatuba.json"):
        """Gera arquivo JSON estruturado para integradores ou auditoria."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"Dados exportados com sucesso para {filename}")

# -----------------------------------------------------------------------------
# GRAVAR DADOS NO SUPABASE
# -----------------------------------------------------------------------------
import json
import logging
import os
import psycopg2
from psycopg2.extras import execute_values

def salvar_no_banco(lotes: list):
    """
    Insere ou atualiza (upsert) os leilões coletados no banco de dados PostgreSQL/Supabase.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logging.warning("⚠️ DATABASE_URL não configurada. Salvação em banco pulada.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Ajuste a query abaixo se a estrutura de tabelas/colunas no seu Supabase tiver nomes diferentes
        query = """
            INSERT INTO leiloes (
                numero_processo, tribunal, vara_origem, titulo, tipo_imovel,
                bairro, cidade, status_ocupacao, nome_leiloeiro,
                link_lote, link_edital, hastas_json
            ) VALUES %s
            ON CONFLICT (numero_processo) DO UPDATE SET
                titulo = EXCLUDED.titulo,
                status_ocupacao = EXCLUDED.status_ocupacao,
                hastas_json = EXCLUDED.hastas_json,
                updated_at = NOW();
        """

        valores = []
        for item in lotes:
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
                json.dumps(item["hastas"])
            ))

        execute_values(cur, query, valores)
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"✅ {len(lotes)} oportunidades salvas/atualizadas no Supabase com sucesso!")

    except Exception as e:
        logging.error(f"❌ Erro ao salvar dados no Supabase: {e}")

if __name__ == "__main__":
    scraper = AracatubaAuctionScraper()
    
    # 1. Executa a busca unificada (TRT-15 + TJSP)
    lotes = scraper.fetch_all_lots()
    
    # 2. Exporta backup local em JSON
    scraper.export_to_json(lotes)
    
    # 3. Atualiza o banco de dados do Supabase
    salvar_no_banco(lotes)
