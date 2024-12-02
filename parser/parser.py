import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import csv
import psycopg2
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
print(sys.executable)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../db')))  # Добавляем путь к db
from db.dbconnect import DB_CONFIG

# URL страницы магазина
URL = config.TARGET_URL  # Замените на URL вашего магазина

# Путь к вашему драйверу Chrome
CHROME_DRIVER_PATH = r"D:\chromedriver\chromedriver-win64\chromedriver.exe"
# Убедитесь, что путь к chromedriver указан правильно

# Настройки для Selenium
chrome_options = Options()
#chrome_options.add_argument("--headless")  # Запуск в фоновом режиме, без открытия браузера

# Функция для получения данных через Selenium
def get_page_with_selenium(url):
    driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=chrome_options)
    driver.get(url)

    prev_product_count = 0
    while True:
        try:
            # Считаем количество товаров перед кликом
            product_elements = driver.find_elements(By.CSS_SELECTOR, '.col-12.col-sm-6.col-md-6.col-lg-4.col-xl-3.g-mb-35.g-card.in-stock')
            curr_product_count = len(product_elements)

            if curr_product_count == prev_product_count:
                # Если количество товаров не изменилось, выходим
                print("Все товары загружены.")
                break

            # Обновляем счетчик товаров
            prev_product_count = curr_product_count

            # Ожидаем и кликаем на кнопку
            load_more_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div[2]/section/div/div[2]/div[2]/div/div[3]/div[2]/div[1]/span'))
            )
            driver.execute_script("arguments[0].scrollIntoView();", load_more_button)
            driver.execute_script("arguments[0].click();", load_more_button)
            time.sleep(3)  # Ждем загрузки
        except Exception as e:
            print("Ошибка или кнопка 'Показать еще' больше не доступна:", e)
            break

    page_html = driver.page_source
    driver.quit()
    return page_html


# Функция для парсинга данных о товарах
def parse_product_data(page_html):
    """Парсит данные товаров из HTML страницы"""
    soup = BeautifulSoup(page_html, 'html.parser')
    products = []

    # Найдем все элементы с товарами
    product_items = soup.find_all('div', class_='col-12 col-sm-6 col-md-6 col-lg-4 col-xl-3 g-mb-35 g-card in-stock')

    for item in product_items:
        # Извлекаем название товара
        name_tag = item.find('div', class_='h3')
        name = name_tag.get_text(strip=True) if name_tag else 'Без названия'

        # Извлекаем ссылку на товар
        link_tag = item.find('a', href=True)
        link = link_tag['href'] if link_tag else 'Без ссылки'

        # Извлекаем цену товара
        price_tag = item.find('div', class_='price g-div')
        price = price_tag.get_text(strip=True) if price_tag else 'Без цены'

        # Извлекаем изображение товара
        img_tag = item.find('div', class_='product')
        image = img_tag['style'].split('url(')[1].split(')')[0] if img_tag and 'url(' in img_tag[
            'style'] else 'Без изображения'

        # Добавляем товар в список
        products.append({
            'name': name,
            'link': link,
            'price': price,
            'image': image
        })

    return products

# Функция для сохранения данных в CSV
def save_to_csv(data, filename='products.csv'):
    """Сохраняем данные в CSV файл"""
    if data:
        keys = data[0].keys()  # Заголовки для CSV файла
        with open(filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
    else:
        print("Нет данных для сохранения.")


# Функция для загрузки данных в базу данных PostgreSQL
def load_data_to_db(csv_filename='products.csv'):
    """Загружает данные из CSV в базу данных PostgreSQL"""
    try:
        # Подключаемся к базе данных с использованием DB_CONFIG
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Открываем CSV и загружаем данные в базу
        with open(csv_filename, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                # Проверяем, существует ли товар с таким же link
                cursor.execute("SELECT 1 FROM products WHERE link = %s LIMIT 1", (row['link'],))
                if cursor.fetchone() is None:
                    # Если товар с таким link не найден, вставляем его в базу
                    cursor.execute(
                        "INSERT INTO products (name, link, price, image) VALUES (%s, %s, %s, %s)",
                        (row['name'], row['link'], row['price'], row['image'])
                    )
                else:
                    # Если товар уже существует, можно обновить его данные
                    cursor.execute(
                        """
                        UPDATE products
                        SET name = %s, price = %s, image = %s
                        WHERE link = %s
                        """,
                        (row['name'], row['price'], row['image'], row['link'])
                    )

        conn.commit()
        print(f"Данные из {csv_filename} успешно загружены в базу данных!")

    except psycopg2.Error as e:
        print("Ошибка при загрузке данных в БД:", e)
    finally:
        cursor.close()
        conn.close()

def main():
    # Получаем страницу через Selenium
    page_html = get_page_with_selenium(URL)
    if page_html:
        # Парсим данные товаров
        products = parse_product_data(page_html)
        if products:
            # Сохраняем данные в CSV
            save_to_csv(products)
            print(f'Данные о {len(products)} товарах сохранены в файл products.csv')

            # Загружаем данные в базу данных
            load_data_to_db()
        else:
            print("Не удалось найти товары на странице.")
    else:
        print("Не удалось загрузить страницу.")

if __name__ == "__main__":
    main()
