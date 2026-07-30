"""
API RESTFUL - SISTEMA DE LEILÕES DE ARAÇATUBA (TRT-15)
------------------------------------------------------
API desenvolvida em FastAPI para consultar, filtrar e servir dados
de leilões de imóveis para o Bot do Telegram e Painel Web.
"""

from typing import List, Optional
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn

# Inicialização da API
app = FastAPI(
    title="API Leilões TRT-15 Araçatuba",
    description="Serviço para consulta e filtragem de oportunidades em leilões judiciais da Justiça do Trabalho de Araçatuba/SP.",
    version="1.0.0"
)

# ------------------------------------------------------------------------------
# MODELOS DE DADOS (SCHEMAS)
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
    nome_leiloeiro: Optional[str] = "Não informado"
    link_lote: str
    link_edital: Optional[str] = None
    link_laudo: Optional[str] = None
    hastas: List[HastaResponse]

# ------------------------------------------------------------------------------
# ROTAS DA API
# ------------------------------------------------------------------------------
@app.get("/", tags=["Status"])
def status_api():
    """Verifica se a API está online e pronta para responder."""
    return {
        "status": "online",
        "sistema": "Leilões TRT-15 Araçatuba",
        "cidade_alvo": "Araçatuba/SP"
    }

@app.get("/oportunidades", response_model=List[OportunidadeImovel], tags=["Leilões"])
def listar_oportunidades(
    valor_maximo_lance: Optional[float] = Query(None, description="Valor máximo aceito para o lance de 2ª hasta"),
    desagio_minimo_pct: float = Query(40.0, description="Percentual mínimo de desconto em relação à avaliação (ex: 50.0 para 50%)"),
    apenas_desocupado: bool = Query(False, description="Se True, filtra apenas imóveis com status 'DESOCUPADO'"),
    tipo_imovel: Optional[str] = Query(None, description="Filtrar por tipo: CASA, APARTAMENTO, TERRENO, GALPAO, COMERCIAL, RURAL"),
    bairro: Optional[str] = Query(None, description="Filtrar por bairro em Araçatuba (ex: Ipanema, Centro)")
):
    """
    Retorna as melhores oportunidades da 2ª hasta em Araçatuba/SP com base nos filtros configurados.
    """
    # Em produção, esta função executa a SQL 'vw_oportunidades_aracatuba' no PostgreSQL/Supabase
    # Exemplo de resposta estruturada servida pela API:
    resultados_simulados = [
        {
            "imovel_id": "c1a2b3c4-1111-2222-3333-444455556666",
            "titulo": "Casa Residencial 250m² - Jardim Ipanema",
            "tipo_imovel": "CASA",
            "bairro": "Jardim Ipanema",
            "cidade": "Araçatuba",
            "status_ocupacao": "DESOCUPADO",
            "numero_processo": "0010452-18.2024.5.15.0011",
            "vara_origem": "1ª Vara do Trabalho / Divisão de Execução",
            "nome_leiloeiro": "Cida Fixer Leilões",
            "link_lote": "https://www.leiloeiroexemplo.com.br/lote/aracatuba-casa-ipanema-102",
            "link_edital": "https://www.leiloeiroexemplo.com.br/editais/edital_0010452.pdf",
            "link_laudo": "https://www.leiloeiroexemplo.com.br/laudos/laudo_0010452.pdf",
            "hastas": [
                {
                    "numero_hasta": 1,
                    "data_fim": "2026-08-15 13:00:00",
                    "valor_avaliacao": 380000.00,
                    "valor_lance_minimo": 380000.00,
                    "percentual_desagio": 0.0
                },
                {
                    "numero_hasta": 2,
                    "data_fim": "2026-08-29 13:00:00",
                    "valor_avaliacao": 380000.00,
                    "valor_lance_minimo": 190000.00,
                    "percentual_desagio": 50.0
                }
            ]
        }
    ]

    # Aplicação dos filtros em memória (no banco real, a própria query SQL filtra)
    filtrados = []
    for item in resultados_simulados:
        hasta2 = item["hastas"][1]
        
        if valor_maximo_lance and hasta2["valor_lance_minimo"] > valor_maximo_lance:
            continue
        if hasta2["percentual_desagio"] < desagio_minimo_pct:
            continue
        if apenas_desocupado and item["status_ocupacao"] != "DESOCUPADO":
            continue
        if tipo_imovel and item["tipo_imovel"].upper() != tipo_imovel.upper():
            continue
        if bairro and bairro.lower() not in item["bairro"].lower():
            continue
            
        filtrados.append(item)

    return filtrados

@app.post("/executar-varredura", tags=["Automação"])
def disparar_varredura(background_tasks: BackgroundTasks):
    """
    Aciona o robô raspador em segundo plano para varrer os leiloeiros do TRT-15 em busca de novos lotes.
    """
    # Adiciona a tarefa de raspagem para rodar sem travar a resposta da API
    # background_tasks.add_task(executar_scraper_aracatuba)
    return {"mensagem": "Varredura iniciada em segundo plano. Novos leilões de Araçatuba serão cadastrados em breve."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)