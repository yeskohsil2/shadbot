import os
import json
import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram.constants import ParseMode

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [8255927158, 6025818386]
ADMIN_CHAT_ID = 1003594449373

if ADMIN_CHAT_ID:
    ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)

contests = {}
payment_requests = {}
contest_id_counter = 1

MAX_PARTICIPANTS, PRIZES, ENTRY_FEE, BANNED_BRAWLERS, TEAM_CODE, CONFIRM = range(6)
WAITING_PROOF = 0

def save_contest(contest_id, contest_data):
    contests[contest_id] = contest_data

def get_contest(contest_id):
    return contests.get(contest_id)

def delete_contest(contest_id):
    if contest_id in contests:
        del contests[contest_id]

def format_prizes(prizes_list):
    return "\n".join([f"{i+1}) {prize}" for i, prize in enumerate(prizes_list)])

async def setadm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав на выполнение этой команды.")
        return

    chat_id = update.effective_chat.id
    os.environ["ADMIN_CHAT_ID"] = str(chat_id)
    global ADMIN_CHAT_ID
    ADMIN_CHAT_ID = chat_id

    await update.message.reply_text(f"✅ Чат для заявок установлен: {chat_id}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        contest_id = args[0]
        contest = get_contest(contest_id)
        if not contest or contest.get("deleted", False):
            await update.message.reply_text("⚠️ Конкурс удалён!")
            return
        if contest["current_participants"] >= contest["max_participants"]:
            text = f"ℹ Информация о конкурсе\n\nМаксимальное количество участников набрано - [✔️✖️]\n\nЦена за вход — {contest['entry_fee']}₽\n\nПризовые места:\n{format_prizes(contest['prizes'])}"
            await update.message.reply_text(text)
            return
        text = f"ℹ Информация о конкурсе\n\nМаксимальное количество участников - {contest['max_participants']}\n\nЦена за вход — {contest['entry_fee']}₽\n\nПризовые места:\n{format_prizes(contest['prizes'])}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text="🙋‍♂️ Участвовать", callback_data=f"join_{contest_id}")]])
        await update.message.reply_text(text, reply_markup=keyboard)
    else:
        user_name = update.effective_user.first_name or update.effective_user.username or "пользователь"
        text = f"🙋‍♂️ *{user_name}*, добро пожаловать в **Shadow Stars**!\n\nℹ️ Данный бот создан для конкурсов по игре Brawl Stars."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text="📜 Список активных розыгрышей", callback_data="list_contests")]])
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def adm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="➕ Создать конкурс", callback_data="create_contest")],
        [InlineKeyboardButton(text="🗑️ Удалить конкурс", callback_data="delete_contest")],
        [InlineKeyboardButton(text="💾 Обновить реквизиты", callback_data="update_details")]
    ])
    await update.message.reply_text("🛡️ Настройки бота", reply_markup=keyboard)

async def list_contests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or query.from_user.username or "пользователь"
    active_contests = [c for c in contests.values() if not c.get("deleted", False)]

    if not active_contests:
        await query.edit_message_text(f"📜 *{user_name}*, список активных розыгрышей:\n\nНет активных розыгрышей", parse_mode=ParseMode.MARKDOWN)
        return

    context.user_data["contests_page"] = 0
    await show_contests_page(query, context, user_name, active_contests, 0)

async def show_contests_page(query, context, user_name, active_contests, page):
    contests_per_page = 7
    total_pages = (len(active_contests) + contests_per_page - 1) // contests_per_page

    start_idx = page * contests_per_page
    end_idx = start_idx + contests_per_page
    page_contests = active_contests[start_idx:end_idx]

    text = f"📜 *{user_name}*, список активных розыгрышей:\n\n"
    for contest in page_contests:
        text += f"🆔 {contest['id']} — приз {contest['prizes'][0] if contest['prizes'] else 'Не указан'} (участников {contest['current_participants']}/{contest['max_participants']})\n"

    buttons = []
    row = []
    for i, contest in enumerate(page_contests):
        row.append(InlineKeyboardButton(text=f"🆔 {contest['id']}", callback_data=f"view_{contest['id']}"))
        if len(row) == 3 or i == len(page_contests) - 1:
            buttons.append(row)
            row = []

    nav_row = []
    nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_prev_{page}"))
    nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop"))
    nav_row.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"page_next_{page}"))
    buttons.append(nav_row)

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

async def page_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    page = int(parts[2])
    if page == 0:
        await query.answer("Вы уже на минимальной странице.")
        return
    user_name = query.from_user.first_name or query.from_user.username or "пользователь"
    active_contests = [c for c in contests.values() if not c.get("deleted", False)]
    await show_contests_page(query, context, user_name, active_contests, page - 1)

async def page_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    page = int(parts[2])
    active_contests = [c for c in contests.values() if not c.get("deleted", False)]
    contests_per_page = 7
    total_pages = (len(active_contests) + contests_per_page - 1) // contests_per_page
    if page + 1 >= total_pages:
        await query.answer("Вы уже на максимальной странице.")
        return
    user_name = query.from_user.first_name or query.from_user.username or "пользователь"
    await show_contests_page(query, context, user_name, active_contests, page + 1)

async def noop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

async def view_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contest_id = query.data.split("_")[1]
    contest = get_contest(contest_id)
    if not contest or contest.get("deleted", False):
        await query.edit_message_text("⚠️ Конкурс удалён!")
        return
    if contest["current_participants"] >= contest["max_participants"]:
        text = f"ℹ Информация о конкурсе\n\nМаксимальное количество участников набрано - [✔️✖️]\n\nЦена за вход — {contest['entry_fee']}₽\n\nПризовые места:\n{format_prizes(contest['prizes'])}"
        await query.edit_message_text(text)
        return
    text = f"ℹ Информация о конкурсе\n\nМаксимальное количество участников - {contest['max_participants']}\n\nЦена за вход — {contest['entry_fee']}₽\n\nПризовые места:\n{format_prizes(contest['prizes'])}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text=" 🙋‍♂️ Участвовать", callback_data=f"join_{contest_id}")]])
    await query.edit_message_text(text, reply_markup=keyboard)

async def create_contest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("У вас нет прав на выполнение этого действия.")
        return ConversationHandler.END
    await query.edit_message_text("Для создания конкурса напишите количество участников:")
    return MAX_PARTICIPANTS

async def create_contest_max_participants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        max_participants = int(update.message.text)
        if max_participants <= 0:
            await update.message.reply_text("Количество участников должно быть положительным числом.")
            return MAX_PARTICIPANTS
        context.user_data["new_contest"] = {"max_participants": max_participants, "current_participants": 0, "participants": []}
        await update.message.reply_text(f"ℹ️ Вы указали {max_participants} участников конкурса.\n\nТеперь введите призовые места в таком формате:\n1) 250₽\n2) 150₽\n3) 100₽\nи т.д")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="✔️ Продолжить", callback_data="prizes_done")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel_create")]
        ])
        await update.message.reply_text("Введите призовые места:", reply_markup=keyboard)
        return PRIZES
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите число.")
        return MAX_PARTICIPANTS

async def create_contest_prizes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    lines = text.strip().split("\n")
    prizes = []
    for line in lines:
        parts = line.split(")")
        if len(parts) > 1:
            prizes.append(parts[1].strip())
    if not prizes:
        await update.message.reply_text("Пожалуйста, введите призовые места в правильном формате.")
        return PRIZES
    context.user_data["new_contest"]["prizes"] = prizes
    await update.message.reply_text("📲 Принято! Теперь введите сумму за вход на розыгрыш, если конкурс бесплатный напишите null.")
    return ENTRY_FEE

async def prizes_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "prizes" not in context.user_data["new_contest"]:
        await query.edit_message_text("Пожалуйста, введите призовые места.")
        return PRIZES
    await query.edit_message_text("📲 Принято! Теперь введите сумму за вход на розыгрыш, если конкурс бесплатный напишите null.")
    return ENTRY_FEE

async def create_contest_entry_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "null":
        entry_fee = 0
    else:
        try:
            entry_fee = int(text)
            if entry_fee < 0:
                await update.message.reply_text("Сумма за вход не может быть отрицательной.")
                return ENTRY_FEE
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите число или null.")
            return ENTRY_FEE
    context.user_data["new_contest"]["entry_fee"] = entry_fee
    await update.message.reply_text("🤡 Напишите запрещённых бойцов через запятую\nФормат: Шелли, Базз, Эмз, Глоуберт")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text="✖️ Нет запрещённых бойцов", callback_data="no_banned")]])
    await update.message.reply_text("Введите запрещённых бойцов:", reply_markup=keyboard)
    return BANNED_BRAWLERS

async def no_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["new_contest"]["banned_brawlers"] = []
    await query.edit_message_text("🔗 Отправьте ссылку или код команды для входа:")
    return TEAM_CODE

async def create_contest_banned_brawlers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    banned = [b.strip() for b in text.split(",")]
    context.user_data["new_contest"]["banned_brawlers"] = banned
    await update.message.reply_text("🔗 Отправьте ссылку или код команды для входа:")
    return TEAM_CODE

async def create_contest_team_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_contest"]["team_code"] = update.message.text
    contest_data = context.user_data["new_contest"]

    text = f"⚠️ Перед созданием конкурса убедитесь в правильности формата.\nℹ Вы заполнили \nМаксимальное кол-во участников - {contest_data['max_participants']}\nЗапрещенные бойцы: {', '.join(contest_data['banned_brawlers']) if contest_data['banned_brawlers'] else 'нет'}\nКод команды: {contest_data['team_code']}\nЦена за вход: {contest_data['entry_fee']}₽\nПризовые места: {', '.join([f'{i+1}) {p}' for i, p in enumerate(contest_data['prizes'])])}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(text="✅ Формат верный", callback_data="confirm_contest")],
        [InlineKeyboardButton(text="🙈 Заполнить анкету заново", callback_data="restart_contest")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard)
    return CONFIRM

async def confirm_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global contest_id_counter
    contest_id = str(contest_id_counter)
    contest_id_counter += 1

    contest_data = context.user_data["new_contest"]
    contest_data["id"] = contest_id
    contest_data["deleted"] = False
    contest_data["current_participants"] = 0
    contest_data["participants"] = []

    save_contest(contest_id, contest_data)

    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={contest_id}"

    await query.edit_message_text(f"✔️ Конкурс успешно создан!\n\n 🔗 Ссылка для конкурса {link}")

    context.user_data.pop("new_contest", None)
    return ConversationHandler.END

async def restart_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("new_contest", None)
    await query.edit_message_text("Для создания конкурса напишите количество участников:")
    return MAX_PARTICIPANTS

async def cancel_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("new_contest", None)
    await query.edit_message_text("Создание конкурса отменено.")
    return ConversationHandler.END

async def join_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contest_id = query.data.split("_")[1]
    contest = get_contest(contest_id)
    user_id = query.from_user.id

    if not contest or contest.get("deleted", False):
        await query.edit_message_text("⚠️ Конкурс удалён!")
        return

    if contest["current_participants"] >= contest["max_participants"]:
        await query.edit_message_text("⚠️ Максимальное количество участников набрано!")
        return

    if user_id in contest["participants"]:
        await query.edit_message_text("❌ Вы уже участвуете в этом конкурсе!")
        return

    context.user_data["pending_join"] = contest_id

    if contest["entry_fee"] == 0:
        contest["current_participants"] += 1
        contest["participants"].append(user_id)
        await query.edit_message_text(f"✔️ Вы успешно приняли участие в конкурсе!\nКод команды: {contest['team_code']}")
        context.user_data.pop("pending_join", None)
    else:
        text = f"ℹ️ Для продолжения внесите оплату в размере {contest['entry_fee']}₽\n\nРеквизиты:\nСбербанк\n89069755249\nРоман П."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(text="🙋‍♂️ Я отправил оплату", callback_data=f"paid_{contest_id}")]])
        await query.edit_message_text(text, reply_markup=keyboard)

async def paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contest_id = query.data.split("_")[1]
    context.user_data["paid_contest"] = contest_id
    await query.edit_message_text("ℹ️ Отправьте фото чека или документ в этот чат")
    return WAITING_PROOF

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contest_id = context.user_data.get("paid_contest")
    if not contest_id:
        return ConversationHandler.END

    contest = get_contest(contest_id)
    if not contest:
        await update.message.reply_text("Конкурс не найден.")
        context.user_data.pop("paid_contest", None)
        return ConversationHandler.END

    if not ADMIN_CHAT_ID:
        await update.message.reply_text("Ошибка: административный чат не установлен. Администратор должен выполнить команду /setadm в нужном чате.")
        context.user_data.pop("paid_contest", None)
        return ConversationHandler.END

    payment_id = str(uuid.uuid4())[:8]
    payment_requests[payment_id] = {
        "user_id": update.effective_user.id,
        "contest_id": contest_id,
        "message_id": update.message.message_id
    }

    user = update.effective_user
    user_identifier = f"@{user.username}" if user.username else str(user.id)

    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(text="✔️ Оплачено", callback_data=f"approve_{payment_id}")],
            [InlineKeyboardButton(text="✖️ Отказ", callback_data=f"reject_{payment_id}")]
        ])

        if update.message.photo:
            caption = f"🔥 Создана заявка на вход!\n\nОплатил {user_identifier}."
            await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=update.message.photo[-1].file_id, caption=caption, reply_markup=keyboard)
        elif update.message.document:
            caption = f"🔥 Создана заявка на вход!\n\nОплатил {user_identifier}."
            await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=update.message.document.file_id, caption=caption, reply_markup=keyboard)

        await update.message.reply_text("✔️ Ваша заявка создана! Ожидайте ответа администрации.")
    except Exception as e:
        await update.message.reply_text("Ошибка отправки заявки. Попробуйте позже.")
        del payment_requests[payment_id]

    context.user_data.pop("paid_contest", None)
    return ConversationHandler.END

async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("approve_"):
        return

    payment_id = query.data.split("_")[1]
    payment_data = payment_requests.get(payment_id)

    if not payment_data:
        await query.edit_message_text("Заявка не найдена.")
        return

    contest = get_contest(payment_data["contest_id"])
    if not contest:
        await query.edit_message_text("Конкурс не найден.")
        del payment_requests[payment_id]
        return

    user_id = payment_data["user_id"]

    if user_id in contest["participants"]:
        await query.edit_message_text("Пользователь уже участвует в конкурсе.")
        del payment_requests[payment_id]
        return

    contest["current_participants"] += 1
    contest["participants"].append(user_id)

    banned_text = ', '.join(contest['banned_brawlers']) if contest['banned_brawlers'] else 'нет'
    prizes_text = format_prizes(contest['prizes'])

    user_text = f"✔️ Ваша заявка успешно принята!\n\nℹ️ ОБЯЗАТЕЛЬНО К ПРОЧТЕНИЮ!\n\n— Запрещённые бойцы: {banned_text}\n\n— Код команды: {contest['team_code']}\n\n— Призовые места: {prizes_text}"

    try:
        await context.bot.send_message(chat_id=user_id, text=user_text)
    except:
        pass

    await query.edit_message_text("ℹ️ Заявка принята!")

    del payment_requests[payment_id]

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("reject_"):
        return

    payment_id = query.data.split("_")[1]
    payment_data = payment_requests.get(payment_id)

    if not payment_data:
        await query.edit_message_text("Заявка не найдена.")
        return

    user_id = payment_data["user_id"]

    try:
        await context.bot.send_message(chat_id=user_id, text="😪 Ваша заявка была отклонена.")
    except:
        pass

    await query.edit_message_text("ℹ️ Заявка отклонена!")

    del payment_requests[payment_id]

async def delete_contest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("У вас нет прав на выполнение этого действия.")
        return

    active_contests = [c for c in contests.values() if not c.get("deleted", False)]
    if not active_contests:
        await query.edit_message_text("Нет активных конкурсов для удаления.")
        return

    buttons = []
    for contest in active_contests[:10]:
        buttons.append([InlineKeyboardButton(text=f"🆔 {contest['id']} — {contest['prizes'][0] if contest['prizes'] else 'Без приза'}", callback_data=f"delete_confirm_{contest['id']}")])

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")])
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("Выберите конкурс для удаления:", reply_markup=keyboard)

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    contest_id = query.data.split("_")[2]
    contest = get_contest(contest_id)
    if contest:
        contest["deleted"] = True
    await query.edit_message_text(f"✔️ Конкурс {contest_id} удалён!")

async def cancel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Удаление отменено.")

async def update_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("У вас нет прав на выполнение этого действия.")
        return
    await query.edit_message_text("Функция обновления реквизитов будет добавлена позже.")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("setadm", setadm))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("adm", adm))

    create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_contest_start, pattern="^create_contest$")],
        states={
            MAX_PARTICIPANTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_max_participants)],
            PRIZES: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_prizes), CallbackQueryHandler(prizes_done, pattern="^prizes_done$")],
            ENTRY_FEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_entry_fee)],
            BANNED_BRAWLERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_banned_brawlers), CallbackQueryHandler(no_banned, pattern="^no_banned$")],
            TEAM_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_contest_team_code)],
            CONFIRM: [CallbackQueryHandler(confirm_contest, pattern="^confirm_contest$"), CallbackQueryHandler(restart_contest, pattern="^restart_contest$")],
        },
        fallbacks=[CallbackQueryHandler(cancel_create, pattern="^cancel_create$")],
    )

    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(paid, pattern="^paid_")],
        states={WAITING_PROOF: [MessageHandler(filters.PHOTO | filters.Document.ALL, receive_proof)]},
        fallbacks=[],
    )

    application.add_handler(create_conv)
    application.add_handler(payment_conv)

    application.add_handler(CallbackQueryHandler(list_contests_callback, pattern="^list_contests$"))
    application.add_handler(CallbackQueryHandler(page_prev, pattern="^page_prev_"))
    application.add_handler(CallbackQueryHandler(page_next, pattern="^page_next_"))
    application.add_handler(CallbackQueryHandler(noop, pattern="^noop$"))
    application.add_handler(CallbackQueryHandler(view_contest, pattern="^view_"))
    application.add_handler(CallbackQueryHandler(join_contest, pattern="^join_"))
    application.add_handler(CallbackQueryHandler(delete_contest_start, pattern="^delete_contest$"))
    application.add_handler(CallbackQueryHandler(delete_confirm, pattern="^delete_confirm_"))
    application.add_handler(CallbackQueryHandler(cancel_delete, pattern="^cancel_delete$"))
    application.add_handler(CallbackQueryHandler(update_details, pattern="^update_details$"))
    application.add_handler(CallbackQueryHandler(approve_payment, pattern="^approve_"))
    application.add_handler(CallbackQueryHandler(reject_payment, pattern="^reject_"))

    application.run_polling()

if __name__ == "__main__":
    main()
