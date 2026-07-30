"""
EXECUTOR UNIFICADO - LEILÕES ARAÇATUBA (TRT-15)
-----------------------------------------------
Inicia a API FastAPI em segundo plano e o Bot do Telegram
de forma simultânea em um único processo.
"""

import os
import asyncio
import threading
import uvicorn
from main import app as api_app
from telegram_bot import app as bot_app

def iniciar_api():
    """Roda a API em uma thread separada."""
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(api_app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("🚀 Iniciando o Sistema de Leilões de Araçatuba...")
    
    # 1. Inicia a API FastAPI
    api_thread = threading.Thread(target=iniciar_api, daemon=True)
    api_thread.start()
    print("✅ API Backend online!")

    # 2. Inicia o Bot do Telegram
    print("🤖 Bot @LeiloesATA_bot conectado e aguardando comandos...")
    bot_app.run_polling()