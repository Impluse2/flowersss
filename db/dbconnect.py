import psycopg2

# Параметры подключения
DB_CONFIG = {
    'dbname': 'flowers',          # Имя базы данных
    'user': 'postgres',       # Ваше имя пользователя PostgreSQL
    'password': ' ',               # Если пароль не установлен, оставьте пустым
    'host': 'localhost',          # Локальный сервер
    'port': 5432                  # Стандартный порт PostgreSQL
}

try:
    # Установление соединения
    conn = psycopg2.connect(**DB_CONFIG)
    print("Подключение к базе данных установлено!")

    # Создаем курсор для выполнения SQL-запросов
    cursor = conn.cursor()

    # Проверим подключение
    cursor.execute("SELECT version();")
    print(f"Версия PostgreSQL: {cursor.fetchone()[0]}")

    # Закрываем курсор и соединение
    cursor.close()
    conn.close()

except psycopg2.Error as e:
    print("Ошибка подключения:", e)
