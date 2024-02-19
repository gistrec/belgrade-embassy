import asyncio
import base64
import random
import sys
import os
import time
import tempfile
import traceback

from anticaptchaofficial.imagecaptcha import *

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from telegram import Bot
from telegram.constants import ParseMode


CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/home/akovalko/Downloads/chromedriver-linux64/chromedriver")

APPLICATION_NUMBER = os.getenv("APPLICATION_NUMBER", "71742")
SECURITY_CODE = os.getenv("SECURITY_CODE", "FFFF9EF5")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "394190148")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

CAPTCHA_KEY = os.getenv("CAPTCHA_KEY")

TIMEOUT = 600


def wait_until_page_loaded(driver):
    while True:
        page_state = driver.execute_script('return document.readyState;')
        if page_state == 'complete':
            return


def wait_until_element_loaded(driver, selector, value):
    try:
        element_present = EC.presence_of_element_located((selector, value))
        WebDriverWait(driver, TIMEOUT).until(element_present)
    except TimeoutException:
        print("Timed out waiting for page to load")
        raise


def resize_page(driver):
    width = driver.execute_script('return document.body.parentNode.scrollWidth')
    height = driver.execute_script('return document.body.parentNode.scrollHeight')
    driver.set_window_size(width, height)


def send_text_to_telegram(text):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
    ))


def send_image_to_telegram(img, caption):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot.send_photo(
        chat_id=TELEGRAM_CHAT_ID,
        photo=img,
        caption=caption,
    ))


def send_page_to_telegram(driver, caption):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    with tempfile.NamedTemporaryFile(suffix='.png') as fp:
        resize_page(driver)
        driver.save_screenshot(fp.name)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=open(fp.name, 'rb'),
            caption=caption,
        ))


service = Service(executable_path=CHROMEDRIVER_PATH)
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
driver = webdriver.Chrome(service=service, options=options)


try:
    # Load embassy site
    print("[1/5] Загружаем страницу с капчей")
    driver.get(f'https://belgrad.kdmid.ru/queue/orderinfo.aspx?id={APPLICATION_NUMBER}&cd={SECURITY_CODE}')
    wait_until_element_loaded(driver, "id", "ctl00_MainContent_imgSecNum")
    resize_page(driver)
    print("[1/5] Станица загружена")

    # Save captcha image
    print("[2/5] Отправляем капчу на решение")
    captcha_img_element = driver.find_element(By.ID, 'ctl00_MainContent_imgSecNum')
    captcha_img = captcha_img_element.screenshot_as_png

    # Get captcha text
    captcha_solver = imagecaptcha()
    captcha_solver.set_key(CAPTCHA_KEY)

    captcha_text = captcha_solver.solve_and_return_solution(None, body=captcha_img)
    if not captcha_text:
        print("Task finished with error: " + captcha_solver.error_code)
        send_page_to_telegram(driver, "Task finished with error: " + captcha_solver.error_code)
        driver.quit()
        exit(0)

    # Write captcha
    driver.find_element(By.ID, "ctl00_MainContent_txtCode").send_keys(captcha_text)
    time.sleep(1)
    driver.find_element(By.ID, "ctl00_MainContent_ButtonA").click()
    time.sleep(1)
    print("[2/5] Капча решена: " + captcha_text)

    print("[3/5] Загружаем страницу с промежуточной кнопкой записи на приём")
    wait_until_page_loaded(driver)
    print("[3/5] Страница загружена")

    text = "Символы с картинки введены не правильно"
    if text in driver.page_source:
        print("[3/5] Капча решена не правильно")
        send_image_to_telegram(captcha_img, "Капча решена не правильно: " + captcha_text)
        send_page_to_telegram(driver, "Капча решена не правильно")
        captcha_solver.report_incorrect_image_captcha()
        driver.quit()
        exit(0)

    print("[4/5] Нажимаем на промежуточную кнопку записи на приём")
    driver.find_element(By.ID, "ctl00_MainContent_ButtonB").click()
    time.sleep(1)

    print("[4/5] Загружаем страницу со свободными слотами")
    wait_until_page_loaded(driver)
    print("[4/5] Страница загружена")

    text = "настоящий момент на интересующее Вас консульское действие в системе предварительной записи нет свободного времени"
    if text in driver.page_source:
        print("[5/5] Свободных слотов нет")
        send_page_to_telegram(driver, "Свободных слотов нет")
        driver.quit()
        exit(0)

    # Выбираем случайную дату
    dates = driver.find_element(By.Name, "ctl00$MainContent$RadioButtonList1")
    date = random.choice(dates)

    # Кликаем на кнопку "Записаться на приём"
    print("[5/5] Нажмаем на кнопку записи на свободный слот")
    driver.find_element(By.ID, "ctl00_MainContent_Button1").click()
    time.sleep(1)

    print("[5/5] Загружаем страницу с результатом записи")
    wait_until_page_loaded(driver)
    print("[5/5] Страница загружена")

    text = "Вы получили подтверждение о записи на приём"
    if text in driver.page_source:
        print("[5/5] Записались на приём")
        send_page_to_telegram(driver, "Записались на приём")
    else:
        print("[5/5] Ошибка во время записи на приём")
        send_page_to_telegram(driver, "Ошибка во время записи на приём")

except Exception as e:
    send_page_to_telegram(driver, "Ошибка во время выполнения скрипта")
    send_text_to_telegram(traceback.format_exc())
finally:
    driver.quit()
    exit(0)
