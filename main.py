"""
API RESTFUL - SISTEMA DE LEILÕES DE ARAÇATUBA (TJSP / TRT-15)
--------------------------------------------------------------
Consulta diretamente a tabela 'leiloes' do Supabase, processa o
JSON das hastas e entrega a estrutura completa para o Bot Telegram.
"""

import os
import json
from typing import List, Optional
from fastapi import FastAPI, Query
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="API Leilões Araçatuba",
    description="Serviço de consulta e filtragem de leilões reais em Araçatuba/SP."
)

DATABASE_URL = os.getenv("DATABASE_URL")

def parse_float(val) -> float:
    """Converte valores com segurança para float."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0

# ------------------------------------------------------------------------------
# ROTA DE HEALTH CHECK (PINGS AUTOMÁTICOS DO RENDER)
# ------------------------------------------------------------------------------
@app.get("/")
@app.head("/")
def status_api():
    return {
        "status": "online",
        "sistema": "Monitor de Leilões de Araçatuba/SP",
        "cidade_alvo": "Araçatuba/SP"
    }

# ------------------------------------------------------------------------------
# MODELOS DE DADOS (PYDANTIC)
# ------------------------------------------------------------------------------
class HastaResponse(BaseModel):
    numero_hasta: int
    data_inicio: Optional[str] = None
    data_fim: str
    valor_avaliacao: float
    valor_lance_minimo: float
    percentual_desagio: float

class OportunidadeImovel(BaseModel):
    id: str
    titulo: str
    tipo_imovel: Optional[str] = "IMÓVEL"
    bairro: Optional[str] = "Araçatuba"
    cidade: Optional[str] = "Araçatuba"
    status_ocupacao: Optional[str] = "DESCONHECIDO"
    numero_processo: Optional[str] = "Não informado"
    vara_origem: Optional[str] = "Vara Cível / Trabalhista"
    nome_leiloeiro: Optional[str] = "Mega Leilões"
    link_lote: Optional[str] = None
    link_edital: Optional[str] = None
    valor_debitos_iptu: float = 0.0
    valor_debitos_condominio: float = 0.0
    debitos_subrogados: bool = True
    observacoes_debitos: Optional[str] = None
    hastas: List[HastaResponse] = []

# ------------------------------------------------------------------------------
# ENDPOINT DE CONSULTA DE OPORTUNIDADES
# ------------------------------------------------------------------------------
@app.get("/oportunidades", response_model=List[OportunidadeImovel], tags=["Leilões"])
def listar_oportunidades(
    valor_maximo_lance: Optional[float] = Query(None),
    desagio_minimo_pct: float = Query(0.0),
    apenas_desocupado: bool = Query(False),
    bairro: Optional[str] = Query(None)
):
    if not DATABASE_URL:
        return []

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Consulta direta na tabela principal
        query = "SELECT * FROM leiloes ORDER BY created_at DESC"
        cursor.execute(query)
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        resultados = []

        for row in rows:
            # 1. Desserialização do campo 'hastas_json'
            hastas_raw = row.get("hastas_json")
            hastas_list = []
            
            if isinstance(hastas_raw, str):
                try:
                    hastas_list = json.loads(hastas_raw)
                except Exception:
                    hastas_list = []
            elif isinstance(hastas_raw, list):
                hastas_list = hastas_raw

            # 2. Avaliação de Filtros
            desagio_max = 0.0
            lance_minimo_atual = 0.0

            if hastas_list:
                hasta_alvo = hastas_list[-1]  # Pega a 2ª hasta
                desagio_max = parse_float(hasta_alvo.get("percentual_desagio", 0.0))
                lance_minimo_atual = parse_float(hasta_alvo.get("valor_lance_minimo", 0.0))

            # Filtro de deságio mínimo
            if desagio_max < desagio_minimo_pct:
                continue

            # Filtro de valor máximo do lance
            if valor_maximo_lance and lance_minimo_atual > valor_maximo_lance:
                continue

            # Filtro por bairro
            bairro_row = str(row.get("bairro") or "")
            if bairro and bairro.lower() not in bairro_row.lower():
                continue

            # Filtro por ocupação
            if apenas_desocupado and str(row.get("status_ocupacao")).upper() != "DESOCUPADO":
                continue

            # 3. Montagem do objeto formatado
            item_formatado = {
                "id": str(row.get("id")),
                "titulo": row.get("titulo") or "Imóvel em Leilão",
                "tipo_imovel": row.get("tipo_imovel") or "IMÓVEL",
                "bairro": row.get("bairro") or "Araçatuba",
                "cidade": row.get("cidade") or "Araçatuba",
                "status_ocupacao": row.get("status_ocupacao") or "DESCONHECIDO",
                "numero_processo": row.get("numero_processo") or "Não informado",
                "vara_origem": row.get("vara_origem") or "Vara Cível / Trabalhista",
                "nome_leiloeiro": row.get("nome_leiloeiro") or "Mega Leilões",
                "link_lote": row.get("link_lote"),
                "link_edital": row.get("link_edital"),
                "valor_debitos_iptu": parse_float(row.get("valor_debitos_iptu")),
                "valor_debitos_condominio": parse_float(row.get("valor_debitos_condominio")),
                "debitos_subrogados": bool(row.get("debitos_subrogados", True)),
                "observacoes_debitos": row.get("observacoes_debitos"),
                "hastas": hastas_list
            }

            resultados.append(item_formatado)

        return resultados

    except Exception as e:
        print(f"❌ Erro ao consultar o banco de dados: {e}")
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
