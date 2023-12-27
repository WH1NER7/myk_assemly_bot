from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

admin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
admin_keyboard.add(KeyboardButton("Установить пароль"))
admin_keyboard.add(KeyboardButton("Изменить пароль"))

user_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
user_keyboard.add(KeyboardButton('/menu'))
user_keyboard.add(KeyboardButton('/finish'))