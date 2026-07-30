"""
BOT DO TELEGRAM - ALERTAS DE LEILÕES DE ARAÇATUBA/SP
---------------------------------------------------
Bot interativo que envia alertas e permite filtrar imóveis
diretamente pela conversa no Telegram.
"""

import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Configurações do Bot e detecção dinâmica da porta do Render
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "SEU_TOKEN_AQUI")
PORT = os.getenv("PORT", "8000")
API_BASE_URL = os.getenv("API_URL", f"http://127.0.0.1:{PORT}")

# ------------------------------------------------------------------------------
# COMANDOS E INTERAÇÕES
# ------------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas e menu principal."""
    texto = (
        "🏠 *Monitor de Leilões TRT-15 - Araçatuba/SP*\n\n"
        "Bem-vindo! Eu sou o seu assistente de investimentos em leilões judiciais.\n"
        "Selecione uma opção abaixo para consultar as oportunidades vigentes:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Ver Oportunidades (2ª Hasta)", callback_data="buscar_2hasta")],
        [InlineKeyboardButton("🟢 Apenas Imóveis Desocupados", callback_data="buscar_desocupados")],
        [InlineKeyboardButton("🏡 Filtrar por Casas", callback_data="tipo_CASA"),
         InlineKeyboardButton("🏢 Filtrar por Aptos", callback_data="tipo_APARTAMENTO")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(texto, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(texto, reply_markup=reply_markup, parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa os cliques nos botões do menu."""
    query = update.callback_query
    await query.answer()

    if query.data in ["buscar_2hasta", "buscar_desocupados", "tipo_CASA", "tipo_APARTAMENTO"]:
        # Define os parâmetros de busca de acordo com o botão clicado
        params = {"desagio_minimo_pct": 40.0}
        
        if query.data == "buscar_desocupados":
            params["apenas_desocupado"] = True
        elif query.data == "tipo_CASA":
            params["tipo_imovel"] = "CASA"
        elif query.data == "tipo_APARTAMENTO":
            params["tipo_imovel"] = "APARTAMENTO"

        try:
            resposta = requests.get(f"{API_BASE_URL}/oportunidades", params=params)
            imoveis = resposta.json()
            
            if not imoveis:
                await query.edit_message_text("Nenhum leilão encontrado com estes critérios no momento.")
                return

            for item in imoveis:
                hasta2 = item["hastas"][-1]
                status_emoji = "🟢" if item["status_ocupacao"] == "DESOCUPADO" else "🔴"
                
                mensagem_card = (
                    f"📌 *{item['titulo']}*\n"
                    f"📍 *Bairro:* {item['bairro']} ({item['cidade']}/SP)\n"
                    f"{status_emoji} *Status:* {item['status_ocupacao']}\n"
                    f"⚖️ *Processo:* `{item['numero_processo']}`\n\n"
                    f"💰 *Avaliação Judicial:* R$ {hasta2['valor_avaliacao']:,.2f}\n"
                    f"🔥 *Lance Mínimo 2ª Hasta:* R$ {hasta2['valor_lance_minimo']:,.2f}\n"
                    f"📉 *Desconto (Deságio):* {hasta2['percentual_desagio']}% OFF\n"
                    f"📅 *Data Limite 2ª Hasta:* {hasta2['data_fim']}\n"
                )
                
                botoes_card = [
                    [InlineKeyboardButton("🔗 Abrir Lote no Leiloeiro", url=item["link_lote"])],
                    [InlineKeyboardButton("📄 Ver Edital (PDF)", url=item["link_edital"])]
                ]
                reply_markup = InlineKeyboardMarkup(botoes_card)
                
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=mensagem_card,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        except Exception as e:
            await query.edit_message_text(f"Erro ao conectar com a API: {str(e)}")

# ------------------------------------------------------------------------------
# INICIALIZAÇÃO GLOBAL DO BOT
# ------------------------------------------------------------------------------
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callback_handler))

if __name__ == "__main__":
    print("Bot do Telegram de Leilões rodando...")
    app.run_polling()
