"""
BOT TELEGRAM - MONITOR DE LEILÕES DE ARAÇATUBA/SP (TJSP / TRT-15)
------------------------------------------------------------------
Consome a API pública no Render e gera fichas de inteligência 
imobiliária detalhadas para todos os imóveis em 2ª Hasta.
"""

import os
import html
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL = "https://leiloes-ATA.onrender.com/oportunidades"

def fmt_brl(valor) -> str:
    """Converte um número float para o formato de moeda brasileiro (R$ X.XXX,XX)."""
    try:
        v = float(valor)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"

def fmt_data(data_str: str) -> str:
    """Converte datas no formato ISO (YYYY-MM-DD HH:MM:SS) para o formato legível BR."""
    if not data_str:
        return "Não informada"
    try:
        # Trata strings de data ISO
        data_clean = data_str.replace("T", " ")[:19]
        dt = datetime.strptime(data_clean, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return data_str

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exibe a nova tela inicial do bot com apresentação geral dos leilões de Araçatuba/SP."""
    mensagem_boas_vindas = (
        "🏛️ <b>Monitor de Leilões Judiciais — Araçatuba/SP</b>\n\n"
        "Bem-vindo ao assistente de inteligência imobiliária!\n"
        "Este robô varre e consolida as oportunidades de imóveis em <b>2ª Hasta</b> "
        "na cidade de Araçatuba (Justiça Comum e Trabalhista).\n\n"
        "Clique no botão abaixo para consultar os leilões ativos:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Consultar Imóveis em 2ª Hasta", callback_data="buscar_oportunidades")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text=mensagem_boas_vindas,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa a requisição e renderiza cada imóvel no novo layout detalhado."""
    query = update.callback_query
    await query.answer()

    if query.data == "buscar_oportunidades":
        try:
            # Enviamos desagio_minimo_pct=0.0 para retornar todos os leilões ativos em 2ª hasta
            response = requests.get(API_URL, params={"desagio_minimo_pct": 0.0}, timeout=15)
            
            if response.status_code == 200:
                imoveis = response.json()

                if not imoveis:
                    await query.edit_message_text("ℹ️ Nenhum leilão em 2ª hasta encontrado no momento.")
                    return

                await query.edit_message_text(
                    f"🎯 <b>{len(imoveis)} oportunidade(s) disponível(is) em Araçatuba/SP:</b>",
                    parse_mode="HTML"
                )

                for item in imoveis:
                    # Captura os dados da 2ª hasta
                    hastas = item.get("hastas", [])
                    hasta2 = hastas[-1] if hastas else {}

                    val_av = fmt_brl(hasta2.get("valor_avaliacao", 0.0))
                    val_min = fmt_brl(hasta2.get("valor_lance_minimo", 0.0))
                    desagio = hasta2.get("percentual_desagio", 0.0)
                    data_fim = fmt_data(hasta2.get("data_fim"))

                    # Cálculo de débitos e sub-rogação
                    iptu = float(item.get("valor_debitos_iptu") or 0.0)
                    condo = float(item.get("valor_debitos_condominio") or 0.0)
                    debitos_totais = iptu + condo
                    
                    subrogados = item.get("debitos_subrogados", True)
                    if subrogados:
                        regra_debitos = "✅ Sub-rogados no preço (Art. 130 CTN)"
                    else:
                        regra_debitos = "⚠️ <b>ATENÇÃO:</b> Débitos por conta do ARREMATANTE"

                    # Sanitização de textos
                    titulo = html.escape(item.get("titulo", "Imóvel em Leilão"))
                    bairro = html.escape(str(item.get("bairro", "Araçatuba")))
                    processo = html.escape(item.get("numero_processo", "Não informado"))
                    vara = html.escape(item.get("vara_origem", "Vara Cível / Trabalhista"))
                    leiloeiro = html.escape(item.get("nome_leiloeiro", "Mega Leilões"))

                    # Montagem da mensagem formatada em HTML
                    mensagem = (
                        f"🏠 <b>{titulo}</b>\n"
                        f"📍 <b>Bairro:</b> {bairro} — Araçatuba/SP\n\n"
                        f"💰 <b>RESUMO FINANCEIRO</b>\n"
                        f"• <b>Avaliação:</b> {val_av}\n"
                        f"• <b>Lance Mínimo (2ª Hasta):</b> {val_min}\n"
                        f"• <b>Deságio:</b> {desagio:.2f}%\n"
                        f"• <b>Débitos (IPTU/Cond.):</b> {fmt_brl(debitos_totais)}\n"
                        f"• <b>Regra Fiscais:</b> {regra_debitos}\n\n"
                        f"📅 <b>PRAZO DA 2ª HASTA</b>\n"
                        f"• <b>Encerramento:</b> {data_fim}\n\n"
                        f"⚖️ <b>DADOS PROCESSUAIS</b>\n"
                        f"• <b>Processo:</b> <code>{processo}</code> <i>(toque p/ copiar)</i>\n"
                        f"• <b>Juízo:</b> {vara}\n"
                        f"• <b>Leiloeiro:</b> {leiloeiro}"
                    )

                    # Botões de link inline
                    keyboard = []
                    if item.get("link_lote"):
                        keyboard.append([InlineKeyboardButton("🌐 Abrir Lote no Leiloeiro", url=item["link_lote"])])
                    if item.get("link_edital"):
                        keyboard.append([InlineKeyboardButton("📄 Baixar Edital em PDF", url=item["link_edital"])])

                    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=mensagem,
                        parse_mode="HTML",
                        reply_markup=reply_markup
                    )
            else:
                await query.edit_message_text(f"⚠️ Erro ao consultar a API (Status: {response.status_code}).")

        except Exception as e:
            print(f"❌ Erro na comunicação com o servidor: {e}")
            await query.edit_message_text("⚠️ Ocorreu um erro ao buscar as informações dos leilões.")

# Inicialização da aplicação Telegram
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callback_handler))
