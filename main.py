import datetime
import os
import json
import logging
import pandas as pd
from aiogram import Bot, Dispatcher
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup

from keyboards import admin_keyboard, user_keyboard

# Уровень логирования
logging.basicConfig(level=logging.INFO)


class AdminStates(StatesGroup):
    PASSWORD = State()
    MENU = State()


# Состояния конечного автомата для сборщика
class CollectorStates(StatesGroup):
    PASSWORD = State()
    MENU = State()
    TASK_NUMBER = State()
    PASSWORD_ATTEMPTS = State()


TOKEN = os.getenv('TOKEN')
PASSWORD_FILE = 'password.txt'
CONFIG_FILE = 'config.json'

# Загрузка конфигурации
config = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

# Загрузка пароля
admin_password = '555'
if os.path.exists(PASSWORD_FILE):
    with open(PASSWORD_FILE, 'r') as f:
        admin_password = f.read().strip()
        print(admin_password)

# Словарь с данными о сборочных заданиях
with open(os.getenv('work_path'), 'r', encoding='utf-8') as file:
    json_data = json.load(file)


# Словарь для отслеживания, какие задания взяты
taken_jobs = {}
current_task_skip = {}

bot = Bot(token=TOKEN)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())


@dp.message_handler(Command("start"))
async def start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)

    if int(user_id) == config.get("admin_id"):
        await message.reply("Вы администратор. Введите пароль:", reply_markup=admin_keyboard)
        await AdminStates.PASSWORD.set()
    else:
        await message.reply("Введите пароль для доступа к функционалу:")

        # await CollectorStates.PASSWORD.set()
        await state.set_state(CollectorStates.PASSWORD.state)


# Обработка нажатия кнопок администратора
@dp.callback_query_handler(state=AdminStates.MENU)
async def admin_menu(query: types.CallbackQuery, state: FSMContext):
    user_id = int(query.from_user.id)

    if query.data == "change_password":
        await query.message.reply("Введите новый пароль:")
        await AdminStates.PASSWORD.set()
    elif query.data == "get_job":
        await send_assembly_job(query.message.chat.id, 0)
        await AdminStates.MENU.set()


@dp.message_handler(state=CollectorStates.PASSWORD)
async def collector_password_handler(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    MAX_PASSWORD_ATTEMPTS = 3
    # Получаем текущее количество попыток ввода пароля
    password_attempts = await state.get_data() or {'attempts': 0}
    password_attempts_count = password_attempts.get('attempts', 0)

    collector_password_file = 'password.txt'
    if os.path.exists(collector_password_file):
        with open(collector_password_file, 'r') as f:
            collector_password = f.read().strip()
            if message.text == collector_password:
                await message.reply("Пароль верный. Вы можете пользоваться функционалом.", reply_markup=user_keyboard)
                await state.finish()  # Завершаем состояние после успешного ввода пароля
                await CollectorStates.MENU.set()
            else:
                password_attempts_count += 1
                if password_attempts_count >= MAX_PASSWORD_ATTEMPTS:
                    await message.reply("Достигнуто максимальное количество попыток ввода пароля. Попробуйте позже.")
                    await state.finish()  # Завершаем состояние после трех неверных попыток
                else:
                    # Сохраняем количество попыток в состоянии
                    await state.update_data(attempts=password_attempts_count)
                    await message.reply(f"Неверный пароль. Попытка {password_attempts_count}. Попробуйте еще раз.")


# Обработка пароля от админа
@dp.message_handler(state=AdminStates.PASSWORD)
async def admin_password_handler(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)

    if int(user_id) == config.get("admin_id") and message.text == admin_password:
        await message.reply("Пароль верный. Вы администратор. Выберите действие:", reply_markup=admin_keyboard)
        await AdminStates.MENU.set()
    else:
        await message.reply("Неверный пароль. Попробуйте еще раз.")

    # Переход в состояние AdminStates.MENU после завершения обработки пароля
    await state.finish()


# Обработка ввода нового пароля администратором
@dp.message_handler(state=AdminStates.MENU)
async def admin_change_password_handler(message: types.Message, state: FSMContext):
    global admin_password
    admin_password = message.text
    with open(PASSWORD_FILE, 'w') as f:
        f.write(admin_password)
    await message.reply("Пароль успешно изменен. Выберите действие:", reply_markup=admin_keyboard)
    await AdminStates.MENU.set()


# Отправка сборочного задания
async def send_assembly_job(chat_id, index):
    job = json_data[index]  # Взяли первую задачу
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("Принять", callback_data='accept_job'),
                 InlineKeyboardButton("Пропустить", callback_data='skip_job'))

    message = f"Баркод: {job['barcode']}\nБренд: {job['brand']}\nНазвание: {job['subject_name']}\n" \
              f"Размер: {job['size']}\nЦвет: {job['color']}\nКоличество: {job['quantity']}\n" \
              f"Выберите действие:"
    await bot.send_message(chat_id=chat_id, text=message, reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'accept_job', state=CollectorStates.MENU)
async def handle_job_response(query: types.CallbackQuery, state: FSMContext):
    user_id = int(query.from_user.id)

    if query.data == 'accept_job':
        job = json_data.pop(0)  # Взяли первую задачу
        job_quantity = job["quantity"]
        taken_jobs[user_id] = job

        # Запись в лог
        log_message = f"Пользователь {query.from_user.username} ({user_id}) взял задачу {job['barcode']} " \
                      f"в количестве {job_quantity} в {query.message.date.strftime('%Y-%m-%d %H:%M:%S')}"
        logging.info(log_message)

        # Создание и отправка Excel файла
        df = pd.DataFrame([job] * 1)
        df.to_excel(f"job_{job['barcode']}_{user_id}.xlsx", index=False)
        with open(f"job_{job['barcode']}_{user_id}.xlsx", "rb") as job_file:
            await bot.send_document(chat_id=query.message.chat.id, document=job_file)
        os.remove(f"job_{job['barcode']}_{user_id}.xlsx")

        await query.message.delete()
        await CollectorStates.MENU.set()  # Устанавливаем состояние для сборщика
    elif query.data == 'decline_job':
        await query.message.delete()
        await CollectorStates.MENU.set()  # Устанавливаем состояние для сборщика


@dp.callback_query_handler(lambda c: c.data == 'skip_job', state=CollectorStates.MENU)
async def handle_skip_job(query: types.CallbackQuery, state: FSMContext):
    user_id = int(query.from_user.id)
    number = current_task_skip[user_id]

    await query.message.delete()
    current_task_skip[user_id] = number + 1
    print(len(json_data))
    print(number + 1)
    # Проверяем, есть ли новые задания в списке json_data
    if number + 1 < len(json_data):
        next_job = json_data[0]
        taken_jobs[user_id] = next_job
        await send_assembly_job(user_id, number + 1)  # Отправляем следующее задание
    elif number + 1 == len(json_data):
        print('я пидор')
        next_job = json_data[0]
        current_task_skip[user_id] = 0
        taken_jobs[user_id] = next_job
        await send_assembly_job(user_id, 0)  # Отправляем следующее задание
    else:
        await query.message.reply("Извините, задания закончились. Пожалуйста, попробуйте позже.")
        await CollectorStates.MENU.set()



# @dp.message_handler(state=MyStates.some_state)
# async def process_text(message: types.Message, state: MyStates):
@dp.message_handler(Command("menu"), state=CollectorStates.MENU)
async def collector_menu_state(message: types.Message):
    user_id = int(message.from_user.id)

    if not json_data:
        await message.reply("Извините, задания закончились. Пожалуйста, попробуйте позже.")
        await CollectorStates.MENU.set()
        return

    if user_id not in taken_jobs:
        current_task_skip[user_id] = 0
        await send_assembly_job(user_id, 0)
        await CollectorStates.MENU.set()
    else:
        await message.reply("У вас уже есть активное сборочное задание. Завершите его, прежде чем взять новое. /finish")
        await CollectorStates.MENU.set()


@dp.message_handler(Command("finish"), state=CollectorStates.MENU)
async def finish_job(message: types.Message, state: FSMContext):
    user_id = int(message.from_user.id)

    if user_id in taken_jobs:
        # Ваша логика для завершения сборочного задания
        finished_job = taken_jobs.pop(user_id)
        await message.reply(f"Сборочное задание {finished_job['barcode']} завершено. Вы можете взять новое. /menu")
        await CollectorStates.MENU.set()  # Установка состояния для сборщика
    else:
        await message.reply("У вас нет активного сборочного задания.")



# Запуск бота
if __name__ == '__main__':
    from aiogram import executor

    executor.start_polling(dp, skip_updates=True)
