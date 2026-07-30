"""
BOT TELEGRAM - SISTEMA DE LEILÕES DE ARAÇATUBA (TRT-15)
-------------------------------------------------------
Interage com o usuário via Telegram consumindo a função de consulta
diretamente, sem depender de requisições HTTP de rede interna.
"""

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from main import listar_oportunidades

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

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
            # Chama a consulta do banco diretamente via Python (100% confiável)
            imoveis = listar_oportunidades(desagio_minimo_pct=40.0)

            if not imoveis:
                await query.edit_message_text("Nenhum leilão encontrado com estes critérios no momento.")
                return

            await query.edit_message_text(f"🎯 Encontrada(s) {len(imoveis)} oportunidade(s) em Araçatuba/SP:")

            for item in imoveis:
                # Captura a última hasta (2ª Hasta com maior deságio)
                hasta2 = item["hastas"][-1]

                valor_av = f"R$ {hasta2['valor_avaliacao']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                valor_min = f"R$ {hasta2['valor_lance_minimo']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                mensagem = (
                    f"🏡 <b>{item['titulo']}</b>\n\n"
                    f"📍 <b>Bairro:</b> {item['bairro']} - {item['cidade']}/SP\n"
                    f"🚪 <b>Status:</b> {item['status_ocupacao']}\n"
                    f"⚖️ <b>Processo:</b> <code>{item['numero_processo']}</code> ({item['vara_origem']})\n"
                    f"🔨 <b>Leiloeiro:</b> {item['nome_leiloeiro']}\n\n"
                    f"💰 <b>Avaliação:</b> {valor_av}\n"
                    f"🔥 <b>Lance Mínimo (2ª Hasta):</b> {valor_min}\n"
                    f"📉 <b>Deságio:</b> {hasta2['percentual_desagio']:.0f}%\n"
                    f"📅 <b>Término:</b> {hasta2['data_fim'][:10]}"
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
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )

        except Exception as e:
            print(f"❌ Erro ao consultar oportunidades: {e}")
            await query.edit_message_text("⚠️ Erro ao consultar o banco de dados de leilões.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callback_handler))
