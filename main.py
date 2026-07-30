"""
API RESTFUL - SISTEMA DE LEILÕES DE ARAÇATUBA (TRT-15)
------------------------------------------------------
Conecta diretamente ao banco PostgreSQL (Supabase) e retorna
oportunidades reais capturadas do TRT-15.
"""

import os
from typing import List, Optional
from fastapi import FastAPI, Query
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="API Leilões TRT-15 Araçatuba",
    description="Serviço de consulta e filtragem de leilões reais em Araçatuba/SP."
)

DATABASE_URL = os.getenv("DATABASE_URL")

# ------------------------------------------------------------------------------
# ROTA DE CHECAGEM DE SAÚDE (HEALTH CHECK PARA O RENDER)
# ------------------------------------------------------------------------------
@app.get("/")
@app.head("/")
def status_api():
    """Responde aos pings automáticos do Render para confirmar que a API está online."""
    return {
        "status": "online",
        "sistema": "Leilões TRT-15 Araçatuba",
        "cidade_alvo": "Araçatuba/SP"
    }

# ------------------------------------------------------------------------------
# MODELOS DE DADOS
# ------------------------------------------------------------------------------
class HastaResponse(BaseModel):
    numero_hasta: int
    data_fim: str
    valor_avaliacao: float
    valor_lance_minimo: float
    percentual_desagio: float

class OportunidadeImovel(BaseModel):
    imovel_id: str
    titulo: str
    tipo_imovel: str
    bairro: str
    cidade: str
    status_ocupacao: str
    numero_processo: str
    vara_origem: str
    nome_leiloeiro: Optional[str] = "Leiloeiro Oficial TRT-15"
    link_lote: str
    link_edital: Optional[str] = None
    link_laudo: Optional[str] = None
    hastas: List[HastaResponse]

# ------------------------------------------------------------------------------
# CONSULTA AO BANCO DE DADOS REAL (SUPABASE)
# ------------------------------------------------------------------------------
@app.get("/oportunidades", response_model=List[OportunidadeImovel], tags=["Leilões"])
def listar_oportunidades(
    valor_maximo_lance: Optional[float] = Query(None),
    desagio_minimo_pct: float = Query(40.0),
    apenas_desocupado: bool = Query(False),
    tipo_imovel: Optional[str] = Query(None),
    bairro: Optional[str] = Query(None)
):
    if not DATABASE_URL:
        return []

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = "SELECT * FROM vw_oportunidades_aracatuba WHERE percentual_desagio >= %s"
        params = [desagio_minimo_pct]

        if apenas_desocupado:
            query += " AND status_ocupacao = 'DESOCUPADO'"
        if tipo_imovel:
            query += " AND tipo_imovel = %s"
            params.append(tipo_imovel.upper())
        if bairro:
            query += " AND bairro ILIKE %s"
            params.append(f"%{bairro}%")
        if valor_maximo_lance:
            query += " AND valor_lance_minimo <= %s"
            params.append(valor_maximo_lance)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        imoveis_map = {}

        for row in rows:
            imovel_id = str(row["imovel_id"])
            if imovel_id not in imoveis_map:
                imoveis_map[imovel_id] = {
                    "imovel_id": imovel_id,
                    "titulo": row["titulo"],
                    "tipo_imovel": row["tipo_imovel"],
                    "bairro": row["bairro"] or "Não informado",
                    "cidade": row["cidade"],
                    "status_ocupacao": row["status_ocupacao"],
                    "numero_processo": row["numero_processo"],
                    "vara_origem": row["vara_origem"],
                    "nome_leiloeiro": row["nome_leiloeiro"] or "Leiloeiro Oficial TRT-15",
                    "link_lote": row["link_lote_leiloeiro"],
                    "link_edital": row["link_edital"],
                    "link_laudo": row["link_laudo_avaliacao"],
                    "hastas": []
                }
            
            imoveis_map[imovel_id]["hastas"].append({
                "numero_hasta": row["numero_hasta"],
                "data_fim": str(row["data_fim"]),
                "valor_avaliacao": float(row["valor_avaliacao"]),
                "valor_lance_minimo": float(row["valor_lance_minimo"]),
                "percentual_desagio": float(row["percentual_desagio"])
            })

        cursor.close()
        conn.close()

        return list(imoveis_map.values())

    except Exception as e:
        print(f"Erro de conexão com o Supabase: {e}")
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
