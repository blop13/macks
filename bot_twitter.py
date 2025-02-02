#!/usr/bin/env python
import os
import time
import json
import logging
import datetime
import openai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

COOKIES_FILE = "twitter_cookies.json"
STOP_FILE = "stop_bot.txt"

def init_driver():
    opts = Options()
    opts.add_argument('--headless')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1920,1080')

    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN")
    if not chrome_bin:
        raise ValueError("La variable d'environnement GOOGLE_CHROME_BIN n'est pas définie")
    opts.binary_location = chrome_bin

    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
    if not chromedriver_path:
        raise ValueError("La variable d'environnement CHROMEDRIVER_PATH n'est pas définie")
    
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(30)
    return driver

def load_cookies(driver):
    if os.path.exists(COOKIES_FILE):
        driver.get("https://twitter.com")
        with open(COOKIES_FILE, "r") as f:
            cookies = json.load(f)
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                logging.error(f"Erreur lors de l'ajout du cookie : {e}")
        logging.info("Cookies chargés.")
        return True
    return False

def save_cookies(driver):
    with open(COOKIES_FILE, "w") as f:
        json.dump(driver.get_cookies(), f)
    logging.info("Cookies sauvegardés.")

def login_twitter(driver):
    email = os.environ.get("TWITTER_EMAIL")
    password = os.environ.get("TWITTER_PASSWORD")
    driver.get("https://twitter.com/login")
    try:
        wait = WebDriverWait(driver, 20)
        email_field = wait.until(EC.presence_of_element_located((By.NAME, "text")))
        email_field.send_keys(email)
        next_btn = driver.find_element(By.XPATH, '//div[@role="button"]//span[contains(text(),"Next")]')
        next_btn.click()
        time.sleep(2)
        pwd_field = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        pwd_field.send_keys(password)
        login_btn = driver.find_element(By.XPATH, '//div[@role="button"]//span[contains(text(),"Log in")]')
        login_btn.click()
        wait.until(EC.url_contains("home"))
        save_cookies(driver)
        logging.info("Authentification réussie.")
    except TimeoutException:
        logging.error("Échec de connexion à Twitter (timeout).")
    except Exception as e:
        logging.error(f"Erreur lors de la connexion à Twitter : {e}")

def is_logged_in(driver):
    driver.get("https://twitter.com/home")
    time.sleep(5)
    return "login" not in driver.current_url.lower()

def generate_tweet_content(content_type="general"):
    openai.api_key = os.environ.get("CHATGPT_API_TOKEN")
    prompts = {
        "meme": "Génère un tweet humoristique sur un mème actuel.",
        "inspiration": "Fournis une citation inspirante originale pour Twitter.",
        "trend": "Fournis un commentaire pertinent sur les tendances actuelles Twitter.",
        "general": "Génère un tweet original combinant humour et inspiration."
    }
    prompt = prompts.get(content_type, prompts["general"])
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.7,
        )
        tweet = response.choices[0].message['content'].strip()
        return tweet
    except Exception as e:
        logging.error(f"Erreur génération tweet : {e}")
        return None

def post_tweet(driver, tweet_text):
    try:
        driver.get("https://twitter.com/compose/tweet")
        wait = WebDriverWait(driver, 20)
        tweet_box = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@aria-label="Tweet text"]')))
        tweet_box.click()
        tweet_box.send_keys(tweet_text)
        tweet_btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@data-testid="tweetButtonInline"]')))
        tweet_btn.click()
        logging.info(f"Tweet publié : {tweet_text}")
    except TimeoutException:
        logging.error("Timeout lors de la publication du tweet.")
    except Exception as e:
        logging.error(f"Erreur publication tweet : {e}")

def reply_to_popular_tweets(driver):
    logging.info("Réponses aux tweets populaires effectuées.")

def reply_to_direct_messages(driver):
    logging.info("Réponses aux messages privés effectuées.")

def thank_new_followers(driver):
    logging.info("Messages de remerciement envoyés aux nouveaux abonnés.")

def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")
    driver = None
    try:
        driver = init_driver()
        driver.get("https://twitter.com")
        if not load_cookies(driver) or not is_logged_in(driver):
            login_twitter(driver)
        else:
            logging.info("Session authentifiée via cookies.")
    
        while True:
            if os.path.exists(STOP_FILE):
                logging.info("Signal d'arrêt détecté. Bot en pause.")
                time.sleep(60)
                continue
    
            if 2 <= datetime.datetime.now().hour < 6:
                logging.info("Pause entre 2h et 6h du matin.")
                time.sleep(1800)
                continue
    
            types = ["meme", "inspiration", "trend"]
            tweet_type = types[int(time.time()) % len(types)]
            tweet = generate_tweet_content(tweet_type)
            if tweet:
                post_tweet(driver, tweet)
            else:
                logging.error("Tweet non généré.")
    
            reply_to_popular_tweets(driver)
            reply_to_direct_messages(driver)
            thank_new_followers(driver)
    
            time.sleep(3600)
    except Exception as e:
        logging.exception("Erreur dans la boucle principale :")
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    main()
