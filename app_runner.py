"""
EXECUTOR UNIFICADO - LEILÕES ARAÇATUBA (TRT-15)
-----------------------------------------------
Inicia a API FastAPI e o Bot do Telegram com limpeza de conexões presas.
"""

import os
import threading
import uvicorn
from main import app as api_app
from telegram_bot import app as bot_app

def iniciar_api():
    """Roda a API FastAPI em uma thread separada."""
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(api_app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("🚀 Iniciando o Sistema de Leilões de Araçatuba...")
    
    # 1. Inicia a API FastAPI em segundo plano
    api_thread = threading.Thread(target=iniciar_api, daemon=True)
    api_thread.start()
    print("✅ API Backend online!")

    # 2. Inicia o Bot limpando qualquer conexão pendente anterior
    print("🤖 Bot @LeiloesATA_bot conectado e aguardando comandos...")
    bot_app.run_polling(drop_pending_updates=True)
