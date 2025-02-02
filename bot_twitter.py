import os
import time
import pickle
import datetime
import traceback

import openai

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===============================
# 1. Configuration & Variables
# ===============================

TWITTER_EMAIL = os.environ.get("TWITTER_EMAIL")
TWITTER_PASSWORD = os.environ.get("TWITTER_PASSWORD")
CHATGPT_API_TOKEN = os.environ.get("CHATGPT_API_TOKEN")

COOKIES_FILE = "twitter_cookies.pkl"

# Intervalle (en secondes) entre chaque cycle (ex: 1h = 3600)
PUBLISH_INTERVAL = 3600

# Période de non-publication (heure locale)
NO_POST_START = 2
NO_POST_END = 6

STOP_FILE = "stop_bot.txt"

# Configuration OpenAI
openai.api_key = CHATGPT_API_TOKEN


# ===============================
# 2. Fonctions Utilitaires
# ===============================

def is_bot_stopped():
    """
    Vérifie l'existence du fichier stop_bot.txt.
    S'il est présent, on stoppe les activités du bot.
    """
    return os.path.isfile(STOP_FILE)

def is_no_post_time():
    """
    Vérifie s'il est actuellement entre NO_POST_START et NO_POST_END (heure locale).
    Si oui, on ne publie pas.
    """
    now = datetime.datetime.now()
    return (NO_POST_START <= now.hour < NO_POST_END)

def init_selenium():
    """
    Initialise Chrome en mode headless pour Heroku, 
    en utilisant le buildpack `heroku-buildpack-chrome-for-testing`.
    Tente de charger les cookies si présents, sinon connecte le compte.
    """

    # Options Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    # Sur heroku-buildpack-chrome-for-testing, 
    # les variables par défaut sont CHROME_PATH et CHROMEDRIVER_PATH.
    chrome_bin = os.environ.get("CHROME_PATH", "/app/.apt/usr/bin/google-chrome")
    driver_path = os.environ.get("CHROMEDRIVER_PATH", "/app/.chromedriver/bin/chromedriver")

    # Spécifie le chemin binaire si nécessaire
    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    # Crée le service Selenium à partir du chemin chromedriver
    chrome_service = Service(driver_path)
    driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
    driver.implicitly_wait(10)

    # Réutiliser les cookies si possible
    if os.path.isfile(COOKIES_FILE):
        try:
            driver.get("https://twitter.com/")
            with open(COOKIES_FILE, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
            driver.refresh()
            # Vérifie si on est vraiment connecté
            if not check_if_logged_in(driver):
                login_twitter(driver)
        except Exception as e:
            print("Erreur lors du chargement des cookies :", e)
            login_twitter(driver)
    else:
        login_twitter(driver)

    return driver

def check_if_logged_in(driver):
    """
    Vérifie si l'utilisateur est déjà connecté (en cherchant un élément réservé aux comptes connectés).
    """
    try:
        driver.find_element(By.XPATH, "//a[@href='/home' and contains(@aria-label, 'Accueil')]")
        return True
    except NoSuchElementException:
        return False

def login_twitter(driver):
    """
    Authentification Twitter via Selenium.
    """
    print("Tentative de connexion à Twitter...")
    driver.get("https://twitter.com/login")
    time.sleep(3)

    # Champ email/nom d'utilisateur
    email_field = driver.find_element(By.NAME, "text")
    email_field.send_keys(TWITTER_EMAIL)
    email_field.submit()
    time.sleep(3)

    # Mot de passe
    try:
        password_field = driver.find_element(By.NAME, "password")
    except NoSuchElementException:
        time.sleep(3)
        password_field = driver.find_element(By.NAME, "password")

    password_field.send_keys(TWITTER_PASSWORD)
    password_field.submit()
    time.sleep(5)

    if not check_if_logged_in(driver):
        raise Exception("La connexion Twitter a échoué. Vérifiez vos identifiants.")

    # Sauvegarde les cookies pour les réutiliser plus tard
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("Connexion réussie et cookies sauvegardés.")

def generate_chatgpt_text(prompt_style="tweet"):
    """
    Appelle l’API OpenAI pour générer un texte en fonction du style (tweet, reply, dm...).
    """
    if prompt_style == "tweet":
        prompt = (
            "Génère un tweet original et accrocheur en français, sans mention directe, "
            "incluant un trait d'humour ou une pensée inspirante. Maximum 280 caractères."
        )
    elif prompt_style == "reply":
        prompt = (
            "Génère une réponse humoristique et pertinente en français à un tweet populaire. "
            "Sois engageant, pas trop long, et évite les mentions directes."
        )
    elif prompt_style == "dm":
        prompt = (
            "Génère un court message privé chaleureux et personnalisé en français pour remercier la personne "
            "de nous avoir suivi, en restant amical et succinct."
        )
    else:
        prompt = "Écris un texte court et intéressant en français."

    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=60,
            temperature=0.7
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print("Erreur lors de la génération OpenAI :", e)
        return None

def post_tweet(driver, text):
    """
    Publie un tweet via Selenium sur la page de composition.
    """
    try:
        driver.get("https://twitter.com/compose/tweet")
        time.sleep(3)

        # Champ de saisie
        textarea = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "br[data-text='true']"))
        )
        textarea.click()
        textarea.send_keys(text)
        time.sleep(1)

        # Bouton publier
        tweet_button = driver.find_element(By.XPATH, "//div[@data-testid='tweetButtonInline']")
        tweet_button.click()
        time.sleep(3)

        print(f"[{datetime.datetime.now()}] Tweet publié : {text}")
    except Exception as e:
        print("Erreur lors de la publication du tweet :", e)

def respond_to_popular_tweet(driver):
    """
    Va sur la page Explorer et répond au premier tweet trouvé (simplifié).
    """
    try:
        driver.get("https://twitter.com/explore")
        time.sleep(5)

        tweets = driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")
        if not tweets:
            print("Aucun tweet trouvé pour y répondre.")
            return

        # Clique sur le premier tweet
        tweets[0].click()
        time.sleep(3)

        reply_text = generate_chatgpt_text(prompt_style="reply")
        if not reply_text:
            return

        # Saisir la réponse
        reply_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[aria-label='Tweet text']"))
        )
        reply_box.click()
        reply_box.send_keys(reply_text)
        time.sleep(1)

        # Bouton envoyer
        send_reply_btn = driver.find_element(By.XPATH, "//div[@data-testid='replyButton']")
        send_reply_btn.click()
        time.sleep(3)

        print(f"[{datetime.datetime.now()}] Réponse envoyée : {reply_text}")
    except Exception as e:
        print("Erreur lors de la réponse à un tweet populaire :", e)

def respond_to_direct_messages(driver):
    """
    Parcourt quelques conversations DM et répond avec un texte généré.
    """
    try:
        driver.get("https://twitter.com/messages")
        time.sleep(5)

        conversations = driver.find_elements(By.XPATH, "//div[@data-testid='conversation']")
        for convo in conversations[:2]:
            convo.click()
            time.sleep(3)

            dm_text = generate_chatgpt_text(prompt_style="dm")
            if not dm_text:
                continue

            dm_box = driver.find_element(By.XPATH, "//div[@data-testid='dmComposerTextInput']")
            dm_box.click()
            dm_box.send_keys(dm_text)
            time.sleep(1)

            send_btn = driver.find_element(By.XPATH, "//div[@data-testid='dmComposerSendButton']")
            send_btn.click()
            time.sleep(2)

            print(f"[{datetime.datetime.now()}] DM envoyé : {dm_text}")
    except Exception as e:
        print("Erreur lors de la réponse aux messages privés :", e)

def thank_new_followers(driver):
    """
    Ex. de remerciement automatique pour les nouveaux abonnés (simplifié).
    """
    try:
        driver.get("https://twitter.com/notifications")
        time.sleep(5)

        follows = driver.find_elements(By.XPATH, "//span[contains(text(), 'vous suit')]/ancestor::div[@data-testid='UserCell']")
        for f in follows[:2]:
            try:
                profile_link = f.find_element(By.XPATH, ".//a[@role='link']")
                profile_url = profile_link.get_attribute("href")

                driver.get(profile_url)
                time.sleep(3)

                message_btn = driver.find_elements(By.XPATH, "//div[@data-testid='sendDMFromProfile']")
                if message_btn:
                    message_btn[0].click()
                    time.sleep(2)

                    dm_text = generate_chatgpt_text(prompt_style="dm")
                    if dm_text:
                        dm_box = driver.find_element(By.XPATH, "//div[@data-testid='dmComposerTextInput']")
                        dm_box.click()
                        dm_box.send_keys(dm_text)
                        time.sleep(1)

                        send_btn = driver.find_element(By.XPATH, "//div[@data-testid='dmComposerSendButton']")
                        send_btn.click()
                        time.sleep(2)

                        print(f"[{datetime.datetime.now()}] Message de remerciement envoyé à {profile_url}")
            except Exception as ex:
                print("Erreur lors de l'envoi du DM de remerciement :", ex)

    except Exception as e:
        print("Erreur lors de la consultation des nouveaux followers :", e)


# ===============================
# 3. Main : Enchaînement des tâches
# ===============================

def main():
    # Vérifie si un fichier stop_bot.txt existe
    if is_bot_stopped():
        print("Le fichier stop_bot.txt est présent. Arrêt du bot.")
        return

    # Vérifie si on est dans la plage horaire de non-publication (2h-6h)
    if is_no_post_time():
        print("Entre 2h et 6h du matin, aucune publication. Le script s'arrête.")
        return

    driver = None
    try:
        driver = init_selenium()

        # 1) Générer et publier un tweet
        tweet_text = generate_chatgpt_text(prompt_style="tweet")
        if tweet_text:
            post_tweet(driver, tweet_text)

        # 2) Répondre à un tweet populaire
        respond_to_popular_tweet(driver)

        # 3) Répondre aux DMs
        respond_to_direct_messages(driver)

        # 4) Remercier les nouveaux abonnés
        thank_new_followers(driver)

    except Exception as e:
        print("Erreur dans main() :", e)
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    # Boucle continue : exécute main() toutes les X secondes.
    while True:
        main()
        print(f"Prochaine exécution dans {PUBLISH_INTERVAL} secondes...")
        time.sleep(PUBLISH_INTERVAL)
