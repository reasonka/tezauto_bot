import asyncio
import os
from pathlib import Path
from typing import Optional

import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatType

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from diagnostics import extract_text_and_codes
from llm import analyze_report


def _max_file_bytes() -> int:
    mb = int(os.environ.get("MAX_FILE_MB", "10"))
    return max(1, mb) * 1024 * 1024


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Отправьте файл диагностики (PDF/TXT/CSV) — я извлеку коды OBD2 и объясню результаты и дальнейшие шаги."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Загрузите в чат файл отчёта диагностики (PDF/TXT/CSV).\n"
        "Подсказка: укажите марку/модель/год/двигатель — так расшифровка кодов будет точнее."
    )


def _is_group(update: Update) -> bool:
    if not update.effective_chat:
        return False
    return update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.document:
        return

    if not _is_group(update):
        await msg.reply_text("Добавьте меня в группу для анализа файлов (работает и в личке).")

    doc = msg.document
    if doc.file_size and doc.file_size > _max_file_bytes():
        await msg.reply_text(
            f"Файл слишком большой ({doc.file_size} байт). Увеличьте MAX_FILE_MB или загрузите меньший отчёт."
        )
        return

    await msg.reply_text("Принято. Скачиваю и анализирую отчёт…")

    tg_file = await context.bot.get_file(doc.file_id)
    data = await tg_file.download_as_bytearray()

    report = extract_text_and_codes(
        filename=doc.file_name or "report",
        content_type=doc.mime_type,
        data=bytes(data),
    )

    # Provide minimal context from chat, without trying to reconstruct everything.
    chat_context: Optional[str] = None
    if msg.caption:
        chat_context = f"User caption: {msg.caption}"

    try:
        analysis = await asyncio.to_thread(
            analyze_report,
            filename=report.filename,
            extracted_text=report.text,
            extracted_codes=report.codes,
            chat_context=chat_context,
        )
    except Exception as e:
        await msg.reply_text(f"Ошибка анализа: {type(e).__name__}: {e}")
        return

    # Telegram message limits: keep reasonably sized.
    if len(analysis) > 3500:
        analysis = analysis[:3500] + "\n\n[Ответ обрезан — задайте уточняющие вопросы.]"

    if report.notes:
        notes = "\n".join(f"- {n}" for n in report.notes)
        analysis = f"{analysis}\n\nЗаметки по извлечению:\n{notes}"

    # Save last report + analysis for this chat to support follow-up questions.
    context.chat_data["last_report"] = {
        "filename": report.filename,
        "text": report.text,
        "codes": report.codes,
        "analysis": analysis,
    }

    await msg.reply_text(analysis)

    # Кнопка: дать пошаговый подробный план действий
    keyboard = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("Да", callback_data="step_plan_yes")
    )
    await msg.reply_text(
        "Дать пошаговый подробный план действий?",
        reply_markup=keyboard,
    )


async def handle_step_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатия «Да» — отдать пошаговый подробный план по последнему отчёту."""
    query = update.callback_query
    if not query or query.data != "step_plan_yes":
        return
    await query.answer()

    last = context.chat_data.get("last_report")
    if not last:
        await query.message.reply_text(
            "Контекст отчёта потерян. Отправьте файл диагностики заново, затем нажмите кнопку."
        )
        return

    await query.message.reply_text("Готовлю пошаговый план…")

    chat_context = (
        "Пользователь нажал «Да» на предложение дать пошаговый план. "
        "На основе предыдущего анализа и отчёта дай пошаговый подробный план действий по ремонту/диагностике. "
        "Нумеруй шаги, пиши чётко и по-русски. Предыдущий ответ ассистента:\n\n"
        f"{last['analysis']}"
    )
    try:
        plan = await asyncio.to_thread(
            analyze_report,
            filename=last["filename"],
            extracted_text=last["text"],
            extracted_codes=last["codes"],
            chat_context=chat_context,
        )
    except Exception as e:
        await query.message.reply_text(f"Ошибка: {type(e).__name__}: {e}")
        return

    if len(plan) > 3500:
        plan = plan[:3500] + "\n\n[План обрезан.]"
    await query.message.reply_text(plan)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle follow-up questions in chat.
    If there is a previous report in this chat, answer in the context of that report.
    Otherwise, treat the text as a standalone question about OBD2 / diagnostics.
    """
    msg = update.message
    if not msg or not msg.text:
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    # Try to use last diagnostic report as context if available.
    last = context.chat_data.get("last_report")

    if last:
        chat_context = (
            "Предыдущий ответ ассистента по последнему диагностическому отчёту:\n"
            f"{last['analysis']}\n\n"
            "Новый уточняющий вопрос пользователя:\n"
            f"{user_text}"
        )
        filename = last["filename"]
        extracted_text = last["text"]
        extracted_codes = last["codes"]
    else:
        # Нет сохранённого отчёта — отвечаем по самому вопросу.
        chat_context = None
        filename = "followup"
        extracted_text = user_text
        extracted_codes = []

    try:
        analysis = await asyncio.to_thread(
            analyze_report,
            filename=filename,
            extracted_text=extracted_text,
            extracted_codes=extracted_codes,
            chat_context=chat_context,
        )
    except Exception as e:
        await msg.reply_text(f"Ошибка анализа вопроса: {type(e).__name__}: {e}")
        return

    if len(analysis) > 3500:
        analysis = analysis[:3500] + "\n\n[Ответ обрезан — задайте дополнительные уточняющие вопросы.]"

    await msg.reply_text(analysis)

def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} is not set.")
    return val


def main() -> None:
    load_dotenv()

    token = _require_env("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(handle_step_plan_callback, pattern="^step_plan_yes$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

