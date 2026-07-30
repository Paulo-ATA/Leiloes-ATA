"""
BOT TELEGRAM - SISTEMA DE LEILÕES DE ARAÇATUBA (TRT-15)
-------------------------------------------------------
Módulo de interação com o usuário via Telegram, consumindo a API FastAPI.
"""

import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Obtém a porta dinâmica configurada pelo Render (ou usa 8000 como padrão local)
PORT = os.getenv("PORT", "8000")
API_URL = f"http://127.0.0.1:{PORT}/oportunidades"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando /start com o menu principal."""
    keyboard = [
        [InlineKeyboardButton("🔍 Ver Oportunidades (2ª Hasta)", callback_data="buscar_oportunidades")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Bem-vindo ao Bot de Leilões do TRT-15 (Araçatuba/SP)!\n\n"
        "Clique no botão abaixo para consultar os imóveis disponíveis com deságio:",
        reply_markup=reply_markup
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa o clique nos botões do Telegram."""
    query = update.callback_query
    await query.answer()

    if query.data == "buscar_oportunidades":
        try:
            # Consulta a API interna passando os parâmetros de busca
            response = requests.get(API_URL, params={"desagio_minimo_pct": 40.0}, timeout=10)
            
            if response.status_code == 200:
                imoveis = response.json()

                if not imoveis:
                    await query.edit_message_text("Nenhum leilão encontrado com estes critérios no momento.")
                    return

                await query.edit_message_text(f"🎯 Encontrada(s) {len(imoveis)} oportunidade(s) em Araçatuba/SP:")

                for item in imoveis:
                    # Captura a última hasta retornada (2ª Hasta)
                    hasta2 = item["hastas"][-1]

                    valor_av = f"R$ {hasta2['valor_avaliacao']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    valor_min = f"R$ {hasta2['valor_lance_minimo']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    mensagem = (
                        f"🏡 *{item['titulo']}*\n\n"
                        f"📍 *Bairro:* {item['bairro']} - {item['cidade']}/SP\n"
                        f"🚪 *Status:* {item['status_ocupacao']}\n"
                        f"⚖️ *Processo:* `{item['numero_processo']}` ({item['vara_origem']})\n"
                        f"🔨 *Leiloeiro:* {item['nome_leiloeiro']}\n\n"
                        f"💰 *Avaliação:* {valor_av}\n"
                        f"🔥 *Lance Mínimo (2ª Hasta):* {valor_min}\n"
                        f"📉 *Deságio:* {hasta2['percentual_desagio']:.0f}%\n"
                        f"📅 *Término:* {hasta2['data_fim'][:10]}"
                    )

                    keyboard = []
                    if item.get("link_lote"):
                        keyboard.append([InlineKeyboardButton("🌐 Abrir Lote no Leiloeiro", url=item["link_lote"])])
                    if item.get("link_edital"):
                        keyboard.append([InlineKeyboardButton("📄 Ver Edital (PDF)", url=item["link_edital"])])

                    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=mensagem,
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
            else:
                await query.edit_message_text(f"⚠️ Erro ao consultar a API (Status: {response.status_code}).")

        except Exception as e:
            print(f"Erro na requisição para a API: {e}")
            await query.edit_message_text("⚠️ Erro de comunicação interna com o servidor de leilões.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callback_handler))
