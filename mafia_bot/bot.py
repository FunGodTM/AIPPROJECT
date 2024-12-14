import random
import logging
import time
from threading import Timer
import asyncio  # Для задержек
from asyncio import sleep  # Для асинхронных задержек
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from config import BOT_TOKEN

# Настройка логирования

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище данных игры

game_data = {
    "players": [],
    "started": False,
    "mafia_target": None,
    "commissioner_target": None,
    "doctor_target": None,
    "phase": "day"  # Текущая фаза: "day" или "night"
}


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:


    logger.info("Команда /start вызвана.")
    await update.message.reply_text(
        "Добро пожаловать в игру 'Мафия'! Используйте команды для взаимодействия:\n"
        "/join - Присоединиться к игре\n"
        "/players - Посмотреть список игроков\n"
        "/start_game - Начать игру\n"
        "/end_game - Завершить игру\n"
        "/end_night - Завершить ночь\n"
        "/start_discussion - Начать обсуждение\n"
        "/end_day - Завершить дневную фазу"

    )

# Команда /join
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    user = update.message.from_user
    command_args = update.message.text.split(maxsplit=1)
    logger.info(f"Команда /join вызвана пользователем {user.full_name}.")

    if game_data["started"]:
        logger.warning("Попытка присоединиться после начала игры.")
        await update.message.reply_text("Игра уже началась, вы не можете присоединиться.")
        return

    if len(command_args) > 1:
        bot_name = command_args[1]
        if any(player["name"] == bot_name for player in game_data["players"]):
            logger.warning(f"Фиктивный игрок с именем {bot_name} уже зарегистрирован.")
            await update.message.reply_text(f"Игрок с именем {bot_name} уже зарегистрирован.")
            return
        game_data["players"].append({"id": None, "name": bot_name})
        logger.info(f"Добавлен фиктивный игрок {bot_name}.")
        await update.message.reply_text(f"Фиктивный игрок {bot_name} добавлен!")
        return

    if user.id in [player["id"] for player in game_data["players"]]:
        logger.warning(f"Игрок {user.full_name} уже зарегистрирован.")
        await update.message.reply_text("Вы уже зарегистрированы.")
        return

    game_data["players"].append({"id": user.id, "name": user.full_name})
    logger.info(f"Игрок {user.full_name} успешно добавлен.")

    for player in game_data["players"]:
        if player["id"] and player["id"] != user.id:
            try:
                await context.bot.send_message(chat_id=player["id"],
                                               text=f"Игрок {user.full_name} присоединился к игре!")
            except Exception as e:
                logger.error(f"Ошибка при уведомлении игрока {player['name']}: {e}")

    await update.message.reply_text(f"{user.full_name} присоединился к игре!")


# Действия ботов
def bot_choose_target(exclude_names):

    possible_targets = [player["name"] for player in game_data["players"] if player["name"] not in exclude_names]
    return random.choice(possible_targets) if possible_targets else None


# Функция отправки сообщения всем игрокам
async def notify_all_players(context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    

    for player in game_data["players"]:
        if player["id"]:  # Проверяем, что ID игрока существует
            try:
                await context.bot.send_message(chat_id=player["id"], text=message)
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения игроку {player['name']}: {e}")


# Команда /players
async def players(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not game_data["players"]:
        await update.message.reply_text("В игре пока нет игроков.")
    else:
        player_list = "\n".join([player["name"] for player in game_data["players"]])
        await update.message.reply_text(f"Список игроков:\n{player_list}")


# Команда /start_game
async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    logger.info("Команда /start_game вызвана.")
    if len(game_data["players"]) < 5:
        logger.warning("Недостаточно игроков для начала игры.")
        await update.message.reply_text("Недостаточно игроков. Для начала игры нужно минимум 5 участников.")
        return

    if game_data["started"]:
        logger.warning("Попытка начать игру, которая уже началась.")
        await update.message.reply_text("Игра уже началась!")
        return

    num_players = len(game_data["players"])
    num_mafia = max(1, num_players // 3)
    roles = ["Мафия"] * num_mafia + ["Комиссар", "Доктор"] + ["Мирный житель"] * (num_players - num_mafia - 2)
    random.shuffle(roles)

    for player, role in zip(game_data["players"], roles):
        player["role"] = role
        if player["id"]:
            try:
                await context.bot.send_message(chat_id=player["id"], text=f"Ваша роль: {role}")
            except Exception as e:
                logger.error(f"Ошибка при отправке роли игроку {player['name']}: {e}")

    game_data["started"] = True
    logger.info(f"Игра началась. Роли распределены: {[(p['name'], p['role']) for p in game_data['players']]}")

    # Рассылка сообщения всем игрокам
    for player in game_data["players"]:
        if player["id"]:
            await context.bot.send_message(chat_id=player["id"],
                                           text="Игра началась! Роли распределены, переход к ночной фазе.")

    await start_night_phase(update, context)


# Команда /end_game
async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    logger.info("Команда /end_game вызвана. Игра будет завершена.")

    # Логируем отправку сообщений игрокам
    for player in game_data["players"]:
        if player["id"]:
            try:
                logger.info(f"Отправляем сообщение о завершении игроку {player['name']}.")
                await context.bot.send_message(chat_id=player["id"], text="Игра завершена. Спасибо за участие!")
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения игроку {player['name']}: {e}")

    # Логируем очистку данных
    game_data.clear()
    game_data.update({
        "players": [],
        "started": False,
        "mafia_target": None,
        "commissioner_target": None,
        "doctor_target": None,
        "phase": "day"
    })
    logger.info("Данные игры очищены. Текущее состояние game_data:")
    logger.debug(game_data)

    await update.message.reply_text("Игра завершена. Вы можете начать новую игру.")


# Ночная фаза
async def start_night_phase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    game_data["phase"] = "night"
    game_data["mafia_target"] = None
    game_data["commissioner_target"] = None
    game_data["doctor_target"] = None

    mafia = [p for p in game_data["players"] if p["role"] == "Мафия"]
    commissioner = next((p for p in game_data["players"] if p["role"] == "Комиссар"), None)
    doctor = next((p for p in game_data["players"] if p["role"] == "Доктор"), None)

    # Уведомление мафии
    for member in mafia:
        if member["id"]:  # Реальный игрок
            await context.bot.send_message(
                chat_id=member["id"],
                text="Наступила ночь. Выберите жертву.",
                reply_markup=get_player_selection_keyboard(member["name"])
            )
        else:  # Фиктивный игрок
            game_data["mafia_target"] = bot_choose_target([member["name"]])
            logger.info(f"Мафия-бот выбрал жертву: {game_data['mafia_target']}")

    # Уведомление комиссара
    if commissioner:
        if commissioner["id"]:  # Реальный игрок
            await context.bot.send_message(
                chat_id=commissioner["id"],
                text="Наступила ночь. Кого проверить?",
                reply_markup=get_player_selection_keyboard(commissioner["name"])
            )
        else:  # Фиктивный игрок
            game_data["commissioner_target"] = bot_choose_target([commissioner["name"]])
            logger.info(f"Комиссар-бот выбрал цель для проверки: {game_data['commissioner_target']}")

    # Уведомление доктора
    if doctor:
        if doctor["id"]:  # Реальный игрок
            await context.bot.send_message(
                chat_id=doctor["id"],
                text="Наступила ночь. Кого лечить?",
                reply_markup=get_player_selection_keyboard(doctor["name"])
            )
        else:  # Фиктивный игрок
            game_data["doctor_target"] = bot_choose_target([])
            logger.info(f"Доктор-бот выбрал цель для лечения: {game_data['doctor_target']}")


# Клавиатура для выбора игрока
def get_player_selection_keyboard(current_player_name):
    buttons = [
        [InlineKeyboardButton(player["name"], callback_data=f"target_{player['name']}")]
        for player in game_data["players"] if player["name"] != current_player_name
    ]
    return InlineKeyboardMarkup(buttons)


# Обработка действий ночью
async def handle_night_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user

    action, target_name = query.data.split("_", 1)

    player = next((p for p in game_data["players"] if p["id"] == user.id), None)
    if not player:
        await query.answer("Вы не участвуете в игре.")
        return

    if game_data["phase"] != "night":
        await query.answer("Сейчас не ночь. Ждите своей очереди.")
        return

    # Действия в зависимости от роли
    if player["role"] == "Мафия":
        game_data["mafia_target"] = target_name
        await query.answer(f"Вы выбрали жертву: {target_name}.")
    elif player["role"] == "Комиссар":
        game_data["commissioner_target"] = target_name
        await query.answer(f"Вы проверяете: {target_name}.")
    elif player["role"] == "Доктор":
        game_data["doctor_target"] = target_name
        await query.answer(f"Вы лечите: {target_name}.")

    await query.message.edit_reply_markup(reply_markup=None)

# Завершение ночной фазы
async def end_night(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if game_data["phase"] != "night":
        await update.message.reply_text("Сейчас не ночь. Завершение ночи невозможно.")
        return

    victim = game_data["mafia_target"]
    saved = game_data["doctor_target"]
    checked_player_name = game_data["commissioner_target"]
    checked_player = next((p for p in game_data["players"] if p["name"] == checked_player_name), None)

    # Формируем сообщение о результатах ночных действий
    result_message = "Ночь завершилась.\n"

    if victim:
        if victim == saved:
            result_message += f"Доктор спас {victim} от убийства!\n"
        else:
            # Уведомляем убитого игрока
            killed_player = next((p for p in game_data["players"] if p["name"] == victim), None)
            if killed_player and killed_player["id"]:
                await context.bot.send_message(chat_id=killed_player["id"],
                                               text="Вы были убиты ночью. Спасибо за участие!")

            game_data["players"] = [p for p in game_data["players"] if p["name"] != victim]
            result_message += f"{victim} был убит мафией.\n"

    # Отправляем сообщение о проверке только комиссару
    if checked_player:
        commissioner = next((p for p in game_data["players"] if p["role"] == "Комиссар"), None)
        if commissioner and commissioner["id"]:
            try:
                await context.bot.send_message(
                    chat_id=commissioner["id"],
                    text=f"Вы проверили {checked_player_name}: {'Мафия' if checked_player['role'] == 'Мафия' else 'Не Мафия'}."
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке результата проверки комиссару: {e}")

    # Проверяем завершение игры перед переходом к дневной фазе
    game_end_message = check_game_end()
    if game_end_message:
        # Уведомляем всех игроков о завершении игры
        for player in game_data["players"]:
            if player["id"]:
                await context.bot.send_message(chat_id=player["id"], text=f"{result_message}\n{game_end_message}")
        reset_game_data()
        return

    # Переход к дневной фазе
    game_data["phase"] = "day"
    result_message += "\nПереход к дневной фазе. Обсуждайте и голосуйте!"
    for player in game_data["players"]:
        if player["id"]:
            await context.bot.send_message(chat_id=player["id"], text=result_message)


# Проверка завершения игры
def check_game_end() -> str:

    mafia_count = sum(1 for player in game_data["players"] if player["role"] == "Мафия")
    non_mafia_count = len(game_data["players"]) - mafia_count

    if mafia_count == 0:
        return "Игра завершена. Победили мирные жители!"
    if mafia_count >= non_mafia_count:
        return "Игра завершена. Победила мафия!"
    return ""


# Сброс данных игры
def reset_game_data():

    game_data.clear()
    game_data.update({
        "players": [],
        "started": False,
        "mafia_target": None,
        "commissioner_target": None,
        "doctor_target": None,
        "votes": {},
        "phase": "day"
    })


# Начало обсуждения
async def start_discussion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not game_data["started"]:
        await update.message.reply_text("Игра не создана или не начата.")
        return

    if game_data["phase"] != "day":
        await update.message.reply_text("Сейчас не день, обсуждение невозможно.")
        return

    game_data["phase"] = "discussion"  # Устанавливаем фазу обсуждения
    game_data["current_speaker_index"] = 0  # Инициализируем индекс текущего говорящего

    await update.message.reply_text("Обсуждение начинается! У каждого игрока 5 секунд.")
    await notify_current_speaker(context)


# Уведомление текущего говорящего
async def notify_current_speaker(context: ContextTypes.DEFAULT_TYPE) -> None:
    if game_data.get("discussion_skipped"):
        await end_discussion(context)  # Досрочное завершение
        return

    current_index = game_data["current_speaker_index"]
    if current_index >= len(game_data["players"]):  # Если все игроки высказались
        await end_discussion(context)  # Завершаем обсуждение
        return

    current_player = game_data["players"][current_index]
    game_data["current_player"] = current_player["name"]  # Сохраняем имя текущего говорящего

    # Уведомляем всех игроков о том, кто говорит
    for player in game_data["players"]:
        if player["id"]:
            await context.bot.send_message(
                chat_id=player["id"],
                text=f"Сейчас говорит {current_player['name']}. У него 5 секунд."
            )

    # Ждём 5 секунд перед переключением на следующего
    await asyncio.sleep(5)
    game_data["current_speaker_index"] += 1
    await notify_current_speaker(context)


# Завершение обсуждения
async def end_discussion(context: ContextTypes.DEFAULT_TYPE) -> None:

    game_data["phase"] = "voting"
    game_data.pop("current_speaker", None)  # Удаляем текущего говорящего
    game_data.pop("current_speaker_index", None)  # Удаляем индекс говорящего

    # Уведомляем всех игроков о завершении обсуждения
    for player in game_data["players"]:
        if player["id"]:
            await context.bot.send_message(
                chat_id=player["id"],
                text="Обсуждение завершено. Переход к голосованию."
            )

    # Запускаем голосование
    await start_voting(context)


# Функция запуска голосования
async def start_voting(context: ContextTypes.DEFAULT_TYPE) -> None:
    alive_players = [player for player in game_data["players"]]
    if len(alive_players) <= 1:
        await context.bot.send_message(chat_id=context.effective_chat.id, text="Недостаточно игроков для голосования.")
        return

    # Создаём клавиатуру для голосования
    keyboard = [
        [InlineKeyboardButton(player["name"], callback_data=f"vote_{player['name']}")]
        for player in alive_players
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Рассылаем сообщение о голосовании всем реальным игрокам
    for player in alive_players:
        if player["id"]:  # Если это реальный игрок
            await context.bot.send_message(
                chat_id=player["id"],
                text="Голосуйте за исключение:",
                reply_markup=reply_markup
            )

    # Случайное голосование ботов
    if "votes" not in game_data:
        game_data["votes"] = {}

    for bot in alive_players:
        if bot["id"] is None:  # Если это бот
            target = bot_choose_target([bot["name"]])  # Выбираем случайную цель
            game_data["votes"][bot["name"]] = target
            logger.info(f"Бот {bot['name']} проголосовал за {target}.")


# Функция выбора случайного игрока ботом
def bot_choose_target(exclude_names):

    possible_targets = [player["name"] for player in game_data["players"] if player["name"] not in exclude_names]
    return random.choice(possible_targets) if possible_targets else None


# Обработка голосования
async def handle_vote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    voter = query.from_user
    _, voted_player_name = query.data.split("_", 1)

    alive_players = [player for player in game_data["players"]]
    if voter.id not in [player["id"] for player in alive_players]:
        await query.answer("Вы не участвуете в игре.")
        return

    if "votes" not in game_data:
        game_data["votes"] = {}

    game_data["votes"][voter.id] = voted_player_name
    await query.answer(f"Ваш голос за {voted_player_name}.")
    await query.message.edit_reply_markup(reply_markup=None)


# Завершение дневной фазы
async def end_day(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if game_data["phase"] != "voting":
        await update.message.reply_text("Сейчас не голосование. Завершение дня невозможно.")
        return

    if "votes" not in game_data or not game_data["votes"]:
        message = "Голосов нет. Никто не исключён. Переход к ночной фазе."
        await notify_all_players(context, message)
        game_data["phase"] = "night"
        await start_night_phase(update, context)
        return

    # Подсчёт голосов
    vote_counts = {}
    for voted_player in game_data["votes"].values():
        vote_counts[voted_player] = vote_counts.get(voted_player, 0) + 1

    max_votes = max(vote_counts.values())
    voted_out_players = [player for player, votes in vote_counts.items() if votes == max_votes]

    if len(voted_out_players) > 1:
        message = "Голоса распределились равномерно. Никто не исключён. Переход к ночной фазе."
        await notify_all_players(context, message)
    else:
        voted_out = voted_out_players[0]
        excluded_player = next((p for p in game_data["players"] if p["name"] == voted_out), None)
        if excluded_player and excluded_player["id"]:
            await context.bot.send_message(chat_id=excluded_player["id"],
                                           text="Вы были исключены из игры. Спасибо за участие!")
        game_data["players"] = [p for p in game_data["players"] if p["name"] != voted_out]
        message = f"{voted_out} исключён из игры."

    # Проверка завершения игры
    game_end_message = check_game_end()
    if game_end_message:
        await notify_all_players(context, f"{message}\n{game_end_message}")
        reset_game_data()
        return

    # Если игра не завершена, продолжаем
    message += " Переход к ночной фазе."
    await notify_all_players(context, message)
    game_data["phase"] = "night"
    await start_night_phase(update, context)


def check_game_end() -> str:
    mafia_count = sum(1 for player in game_data["players"] if player["role"] == "Мафия")
    non_mafia_count = len(game_data["players"]) - mafia_count

    if mafia_count == 0:
        return "Игра завершена. Победили мирные жители!"
    if mafia_count >= non_mafia_count:
        return "Игра завершена. Победила мафия!"
    return ""


# Настройка приложения
def main():
    logger.info("Запуск бота...")
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("players", players))
    application.add_handler(CommandHandler("start_game", start_game))
    application.add_handler(CommandHandler("end_game", end_game))
    application.add_handler(CommandHandler("end_night", end_night))
    application.add_handler(CommandHandler("end_day", end_day))
    application.add_handler(CommandHandler("start_discussion", start_discussion))

    # Регистрация обработчиков коллбеков
    application.add_handler(CallbackQueryHandler(handle_vote, pattern=r"vote_.*"))
    application.add_handler(CallbackQueryHandler(handle_night_action, pattern=r"target_.*"))

    # Запуск бота
    application.run_polling()


if __name__ == "__main__":
    main()