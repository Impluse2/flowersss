import logging
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import pandas as pd
import psycopg2
import re

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../db')))  # Добавляем путь к db
from db.dbconnect import DB_CONFIG
# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Константы
PRODUCTS_CSV = 'parser/products.csv'
BASE_URL = config.IMAGE_URL  # Базовый URL сайта
ITEMS_PER_PAGE = 10  # Количество товаров на одной странице

# Глобальная переменная для хранения корзин пользователей
user_carts = {}

def load_products():
    """Загружает товары из базы данных PostgreSQL и преобразует относительные пути в абсолютные."""
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Извлекаем данные о товарах из базы данных
        cursor.execute("SELECT id, name, link, price, image FROM products")
        products = cursor.fetchall()

        # Закрытие соединения с базой данных
        cursor.close()
        conn.close()

        # Преобразуем данные в DataFrame
        products_df = pd.DataFrame(products, columns=['id', 'name', 'link', 'price', 'image'])

        # Преобразуем относительные пути в абсолютные
        products_df['link'] = BASE_URL + products_df['link']
        products_df['image'] = BASE_URL + products_df['image']
        return products_df
    except psycopg2.Error as e:
        logging.error(f"Ошибка загрузки данных из базы данных: {e}")
        return pd.DataFrame()

products_df = load_products()

def extract_price(price_str: str):
    """Извлекает числовую часть из строки цены (например, 'от 3500 ₽' -> 3500)."""
    # Убираем все ненужные символы (пробелы, 'от' и ₽)
    price_str = re.sub(r'[^\d]', '', price_str)
    # Если есть цифры, преобразуем в число
    if price_str:
        return float(price_str)
    return 0

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение с кнопками для навигации."""

    # Получаем информацию о пользователе
    telegram_user_id = update.message.from_user.id
    username = update.message.from_user.username  # Имя пользователя (если оно есть)

    # Добавляем пользователя в базу данных
    add_user_to_db(telegram_user_id, username)

    # Кнопки для взаимодействия
    keyboard = [
        [InlineKeyboardButton("Посмотреть товары", callback_data='show_products')],
        [InlineKeyboardButton("Сортировать по алфавиту", callback_data='sort_products')],
        [InlineKeyboardButton("Сортировать по цене", callback_data='sort_products_price')],
        [InlineKeyboardButton("Показать корзину", callback_data='show_cart')],
        [InlineKeyboardButton("Получить помощь", callback_data='help')],
        [InlineKeyboardButton("Обновить список товаров", callback_data='update_products')],
        [InlineKeyboardButton("Перейти на главную страницу", url=config.TARGET_URL)]  # Кнопка с URL
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = "Добро пожаловать! Выберите действие:"
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

# Функция возврата в главное меню
async def return_to_main_menu(update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Посмотреть товары", callback_data='show_products')],
        [InlineKeyboardButton("Сортировать по алфавиту", callback_data='sort_products')],
        [InlineKeyboardButton("Сортировать по цене", callback_data='sort_products_price')],
        [InlineKeyboardButton("Показать корзину", callback_data='show_cart')],
        [InlineKeyboardButton("Получить помощь", callback_data='help')],
        [InlineKeyboardButton("Обновить список товаров", callback_data='update_products')],
        [InlineKeyboardButton("Перейти на главную страницу", url=config.TARGET_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "Вы вернулись в главное меню. Выберите действие:"
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.reply_text(text=message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)


# Обработчик команды /products
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE, products_data: pd.DataFrame = None):
    """Отображает список товаров с кнопками для просмотра."""
    # Если products_data не передан, используем глобальный products_df
    if products_data is None:
        products_data = products_df

    if products_data.empty:
        await update.message.reply_text("Список товаров пуст.")
        return

    # Показываем первую страницу товаров
    await show_products_page(update, products_data, 0)


# Функция для отображения товаров на странице
async def show_products_page(update: Update, products_data: pd.DataFrame, page: int):
    """Отображает товары на странице с кнопками пагинации."""
    start_index = page * ITEMS_PER_PAGE
    end_index = (page + 1) * ITEMS_PER_PAGE
    products_page = products_data.iloc[start_index:end_index]

    # Генерация кнопок с товарами
    keyboard = [
        [InlineKeyboardButton(product["name"], callback_data=f"product_{index}")]
        for index, product in products_page.iterrows()
    ]

    # Добавляем кнопку "Показать еще" для следующей страницы
    next_page_button = InlineKeyboardButton('Показать еще', callback_data=f"next_{page + 1}")
    keyboard.append([next_page_button])
    keyboard.append([InlineKeyboardButton("Главное меню", callback_data='main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем новое сообщение с товарами (или редактируем старое, если сообщение уже существует)
    if update.message:
        await update.message.reply_text("Выберите товар:", reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text("Выберите товар:", reply_markup=reply_markup)


# Обработчик нажатий на кнопки
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки и выполняет соответствующие действия."""
    query = update.callback_query
    await query.answer()

    # Проверяем тип callback_data
    callback_data = query.data

    if callback_data == 'show_products':
        # Если нажата кнопка "Посмотреть товары"
        await show_products(update, context)
    elif callback_data == 'show_cart':
        # Если нажата кнопка "Показать корзину"
        await show_cart(update, context)  # Отображаем корзину
    elif callback_data == 'sort_products':
        # Если нажата кнопка "Сортировать по алфавиту"
        await show_sort_options(update, context)
    elif callback_data == 'sort_products_price':
        # Если нажата кнопка "Сортировать по цене"
       await show_sort_options_price(update, context)
    elif callback_data == 'help':
        # Если нажата кнопка "Получить помощь"
        await show_help(update, context)
    elif callback_data == 'update_products':
        # Если нажата кнопка "Обновить список товаров"
        await update_products(update, context)
    elif callback_data.startswith('product'):
        # Если нажата кнопка с товаром
        product_index = int(callback_data.split('_')[1])
        product = products_df.iloc[product_index]

        # Формируем сообщение о товаре
        message = (
            f"*{product['name']}*\n"
            f"Цена: {product['price']}\n"
            f"[Ссылка на товар]({product['link']})"
        )

        keyboard = [
            [InlineKeyboardButton("Добавить в корзину", callback_data=f"add_to_cart_{product_index}")],
            [InlineKeyboardButton("Назад к товарам", callback_data='show_products')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if product.get('image', 'Без изображения') != 'Без изображения':
            await query.message.reply_photo(
                photo=product['image'],
                caption=message,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        else:
            await query.message.reply_text(
                text=message,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

    elif callback_data.startswith('next_'):
        # Получаем номер следующей страницы из callback_data
        next_page = int(callback_data.split('_')[1])

        # Отображаем товары для следующей страницы
        await show_products_page(update, products_df, next_page)


    elif callback_data.startswith('main_menu'):
        await return_to_main_menu(update, context)

    elif callback_data == 'sort_asc':
        # Сортировка по алфавиту (A-Z)
        await sort_products(update, context, ascending=True)

    elif callback_data == 'sort_desc':
        # Сортировка по алфавиту (Z-A)
        await sort_products(update, context, ascending=False)

    elif callback_data == 'sort_price_asc':
        # Сортировка по цене (от низкой к высокой)
        await sort_products_price(update, context, by_price=True)

    elif callback_data == 'sort_price_desc':
        # Сортировка по цене (от высокой к низкой)
        await sort_products_price(update, context, by_price=False)

    elif callback_data.startswith('add_to_cart'):
        # Получаем индекс товара из callback_data
        match = re.match(r"add_to_cart_(\d+)", callback_data)
        if match:
            product_index = int(match.group(1))
            # В данном месте вызов add_to_cart будет синхронным, так как сама функция не асинхронная
            product = products_df.iloc[product_index]
            user_id = update.callback_query.from_user.id  # Получаем ID пользователя
            success = add_to_cart(user_id, product['id'], quantity=1)

            if success:
                await query.message.reply_text(f"Товар '{product['name']}' был добавлен в вашу корзину!")
            else:
                await query.message.reply_text(f"Произошла ошибка при добавлении товара '{product['name']}' в корзину.")
        else:
            logging.error(f"Ошибка извлечения индекса товара из callback_data: {callback_data}")

    elif callback_data == 'clear_cart':
        # Очистка корзины пользователя
        user_id = update.callback_query.from_user.id  # Получаем ID пользователя
        success = clear_cart(user_id)

        if success:
            await query.message.reply_text("Ваша корзина была успешно очищена!")
        else:
            await query.message.reply_text("Произошла ошибка при очистке корзины.")

def add_to_cart(telegram_user_id: int, product_id: int, quantity: int = 1):
    """Добавляет товар в корзину для конкретного пользователя. Если товар уже есть, увеличиваем количество."""
    try:
        # Преобразуем product_id и quantity в обычные типы int, если они являются numpy.int64
        telegram_user_id = int(telegram_user_id)
        product_id = int(product_id)
        quantity = int(quantity)

        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Проверяем, существует ли пользователь в таблице users по telegram_user_id
        cursor.execute("SELECT id FROM users WHERE telegram_user_id = %s", (telegram_user_id,))
        user_record = cursor.fetchone()
        if user_record is None:
            logging.error(f"Пользователь с telegram_user_id {telegram_user_id} не найден в таблице users.")
            return False  # Возвращаем False, если пользователь не найден

        # Получаем id пользователя, чтобы использовать его в таблице cart
        user_id = user_record[0]

        # Проверяем, есть ли товар в корзине пользователя
        cursor.execute("""
            SELECT quantity FROM cart WHERE telegram_user_id = %s AND product_id = %s
        """, (telegram_user_id, product_id))
        existing_item = cursor.fetchone()

        if existing_item:
            # Если товар уже есть, увеличиваем количество
            new_quantity = existing_item[0] + quantity
            cursor.execute("""
                UPDATE cart SET quantity = %s WHERE telegram_user_id = %s AND product_id = %s
            """, (new_quantity, telegram_user_id, product_id))
        else:
            # Если товара нет, добавляем его с указанным количеством
            cursor.execute("""
                INSERT INTO cart (telegram_user_id, product_id, quantity) VALUES (%s, %s, %s)
            """, (telegram_user_id, product_id, quantity))

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        cursor.close()
        conn.close()

        return True

    except psycopg2.Error as e:
        logging.error(f"Ошибка при добавлении товара в корзину: {e}")
        return False


def get_user_cart(telegram_user_id: int):
    """Возвращает товары из корзины для конкретного пользователя."""
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Получаем товары из корзины пользователя
        cursor.execute("""
            SELECT p.name, p.price, c.quantity 
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.telegram_user_id = %s
        """, (telegram_user_id,))
        cart_items = cursor.fetchall()

        cursor.close()
        conn.close()

        return cart_items

    except psycopg2.Error as e:
        logging.error(f"Ошибка при получении корзины пользователя: {e}")
        return []

# Функция для отображения корзины пользователя
async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает содержимое корзины пользователя."""

    # Получаем ID пользователя
    telegram_user_id = update.callback_query.from_user.id

    # Получаем товары из корзины пользователя
    cart_items = get_user_cart(telegram_user_id)

    if not cart_items:
        await update.callback_query.message.reply_text("Ваша корзина пуста.")
        return

    # Формируем сообщение с товарами в корзине
    cart_message = "*Ваша корзина:*\n\n"
    total_price = 0  # Переменная для подсчета общей стоимости

    for item in cart_items:
        name, price, quantity = item
        item_total = extract_price(price) * quantity
        total_price += item_total
        cart_message += f"{name} - {price} ₽ x {quantity} = {item_total} ₽\n"

    # Добавляем общую стоимость в корзину
    cart_message += f"\n*Итого: {total_price} ₽*"

    # Кнопки для управления корзиной
    keyboard = [
        [InlineKeyboardButton("Назад к товарам", callback_data='show_products')],
        [InlineKeyboardButton("Главное меню", callback_data='main_menu')]
    ]

    # Добавляем кнопку "Очистить корзину", только если корзина не пуста
    if cart_items:
        keyboard.insert(0, [InlineKeyboardButton("Очистить корзину", callback_data='clear_cart')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text(cart_message, parse_mode="Markdown", reply_markup=reply_markup)

# Функция для очистки корзины пользователя
def clear_cart(telegram_user_id: int):
    """Очищает корзину пользователя."""
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Логирование запроса
        logging.debug(f"SQL-запрос: DELETE FROM cart WHERE telegram_user_id = {telegram_user_id}")

        # Удаляем все товары из корзины пользователя
        cursor.execute("DELETE FROM cart WHERE telegram_user_id = %s", (telegram_user_id,))

        # Проверяем количество затронутых строк
        rows_deleted = cursor.rowcount
        if rows_deleted == 0:
            logging.warning(f"Не удалено ни одной записи для telegram_user_id {telegram_user_id}")
        else:
            logging.info(f"Удалено {rows_deleted} записей из корзины для пользователя {telegram_user_id}")

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        cursor.close()
        conn.close()

        logging.info(f"Корзина пользователя с telegram_user_id {telegram_user_id} была очищена.")
        return True
    except psycopg2.Error as e:
        logging.error(f"Ошибка при очистке корзины: {e}")
        # Дополнительная информация о ошибки
        logging.error(f"Текст ошибки: {e.pgcode} - {e.pgerror}")
        return False


async def show_sort_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает две опции сортировки: A-Z и Z-A"""
    keyboard = [
        [InlineKeyboardButton("Сортировать по алфавиту (А-Я)", callback_data='sort_asc')],
        [InlineKeyboardButton("Сортировать по алфавиту (Я-А)", callback_data='sort_desc')],
        [InlineKeyboardButton("Вернуться к продуктам", callback_data='show_products')],
        [InlineKeyboardButton("Главное меню", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("Выберите порядок сортировки:", reply_markup=reply_markup)

async def show_sort_options_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает две опции сортировки: A-Z и Z-A"""
    keyboard = [
        [InlineKeyboardButton("Сортировать по цене (от низкой к высокой)", callback_data='sort_price_asc')],
        [InlineKeyboardButton("Сортировать по цене (от высокой к низкой)", callback_data='sort_price_desc')],
        [InlineKeyboardButton("Вернуться к продуктам", callback_data='show_products')],
        [InlineKeyboardButton("Главное меню", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("Выберите порядок сортировки:", reply_markup=reply_markup)

async def sort_products(update: Update, context: ContextTypes.DEFAULT_TYPE, ascending: bool):
    """Сортирует товары по алфавиту и отображает их."""
    global products_df  # Это глобальная переменная для продуктов

    if not products_df.empty:
        # Создаем копию DataFrame для сортировки
        sorted_products_df = products_df.copy()

        # Сортируем копию по имени товара
        sorted_products_df = sorted_products_df.sort_values(by='name', ascending=ascending)
        # Сбрасываем индексы после сортировки
        sorted_products_df = sorted_products_df.reset_index(drop=True)
        # Показать товары после сортировки
        await show_products(update, context, sorted_products_df)  # Передаем отсортированные данные
    else:
        await update.message.reply_text("Нет товаров для сортировки.")

async def sort_products_price(update: Update, context: ContextTypes.DEFAULT_TYPE, by_price: bool):
    """Сортирует товары по цене и отображает их."""
    global products_df  # Это глобальная переменная для продуктов

    if not products_df.empty:
        # Создаем копию DataFrame для сортировки
        sorted_products_df = products_df.copy()

        # Преобразуем строковые цены в числовые для сортировки
        sorted_products_df['price_numeric'] = sorted_products_df['price'].apply(extract_price)

        # Сортируем копию по цене
        sorted_products_df = sorted_products_df.sort_values(by='price_numeric', ascending=by_price)

        # Удаляем временную колонку с числовыми ценами
        sorted_products_df = sorted_products_df.drop(columns=['price_numeric'])

        # Показать товары после сортировки
        await show_products(update, context, sorted_products_df)  # Передаем отсортированные данные
    else:
        await update.message.reply_text("Нет товаров для сортировки.")

async def update_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновляет список товаров, вызывая парсер и перезагружая данные."""
    try:
        # Сообщаем пользователю, что обновление началось
        await update.callback_query.message.reply_text("Обновление списка товаров началось. Пожалуйста, подождите...")

        # Предположим, что парсер - это внешний скрипт, который нужно запустить
        # Можно использовать subprocess для вызова вашего парсера, если это отдельный файл
        result = subprocess.run([r"D:\flowers\.venv\Scripts\python.exe", r"D:\flowers\parser\parser.py"],
        capture_output=True, text=True
        )

        if result.returncode == 0:
            # Если парсер успешно завершился, очищаем и перезагружаем список товаров
            global products_df

            # Очищаем текущие данные
            products_df = pd.DataFrame()

            # Загружаем обновленные данные
            products_df = load_products()

            # Отправляем сообщение об успешном обновлении
            await update.callback_query.message.reply_text("Данные успешно обновлены!")
        else:
            # Если произошла ошибка в парсере
            logging.error(f"Ошибка при запуске парсера: {result.stderr}")
            await update.callback_query.message.reply_text("Произошла ошибка при обновлении данных. Пожалуйста, попробуйте снова позже.")

    except Exception as e:
        # Если ошибка в процессе
        logging.error(f"Ошибка при обновлении списка товаров: {e}")
        await update.callback_query.message.reply_text("Произошла ошибка при обновлении данных. Пожалуйста, попробуйте снова позже.")

# Функция для отображения помощи
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет информацию о доступных командах."""
    help_message = (
        "Вот доступные действия, которые вы можете выполнить:\n"
        "- Нажмите на кнопку 'Посмотреть товары', чтобы увидеть товары.\n"
        "- Нажмите на кнопку 'Сортировать по алфавиту', чтобы увидеть отсортированные товары.\n"
        "- Нажмите на кнопку 'Сортировать по цене', чтобы увидеть отсортированные товары.\n"
        "- Нажмите на кнопку 'Показать корзину', чтобы посмотреть товары добавленные в корзину.\n"
        "- Нажмите на кнопку 'Получить помощь', чтобы получить помощь.\n"
        "- Нажмите на кнопку 'Обновить список товаров', чтобы обновить данные.\n"
        "- Нажмите на кнопку 'Перейти на главную страницу', чтобы перейти на сайт."
    )
    await update.callback_query.message.reply_text(help_message)

def add_user_to_db(telegram_user_id: int, username: str = None):
    """Добавляет нового пользователя в базу данных, если его там нет."""
    try:
        # Подключаемся к базе данных
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Проверяем, существует ли пользователь с таким Telegram ID
        cursor.execute("SELECT id FROM users WHERE telegram_user_id = %s", (telegram_user_id,))
        existing_user = cursor.fetchone()

        if existing_user is None:
            # Если пользователя нет, добавляем нового
            cursor.execute(
                "INSERT INTO users (telegram_user_id, username) VALUES (%s, %s)",
                (telegram_user_id, username)
            )
            conn.commit()  # Подтверждаем изменения
            logging.info(f"Пользователь с Telegram ID {telegram_user_id} был добавлен в базу данных.")
        else:
            logging.info(f"Пользователь с Telegram ID {telegram_user_id} уже существует в базе данных.")

        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        logging.error(f"Ошибка при добавлении пользователя в базу данных: {e}")

# Основная функция для запуска бота
def main():
    # Вставьте сюда токен вашего бота
    TOKEN = config.BOT_TOKEN

    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))

    # Запускаем бота
    application.run_polling()


if __name__ == "__main__":
    main()