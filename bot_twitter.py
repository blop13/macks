import os
import time
import pickle
import datetime
import traceback

import openai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===============================
# 1. Configuration & Variables
# ===============================

# Récupération des variables d'environnement sur Heroku
TWITTER_EMAIL = os.environ.get("TWITTER_EMAIL")
TWITTER_PASSWORD = os.environ.get("TWITTER_PASSWORD")
CHATGPT_API_TOKEN = os.environ.get("CHATGPT_API_TOKEN")

# Fichier local où seront stockés/rechargés les cookies Twitter
COOKIES_FILE = "twitter_cookies.pkl"

# Intervalle (en secondes) entre les cycles d’exécution (ex: 1h)
PUBLISH_INTERVAL = 3600

# Heures locales auxquelles on NE publie pas (ex: de 2h à 6h)
NO_POST_START = 2
NO_POST_END = 6

# Nom du fichier permettant de stopper temporairement le bot
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
    if NO_POST_START <= now.hour < NO_POST_END:
        return True
    return False

def init_selenium():
    """
    Initialise le driver Chrome (mode headless), 
    avec configuration adaptée à Heroku (binary_location, executable_path).
    Tente de charger les cookies si présents, sinon procède à la connexion.
    """

    # Options du navigateur
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    # Configuration spécifique pour Heroku
    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN", "/app/.apt/usr/bin/google-chrome")
    chrome_options.binary_location = chrome_bin
    driver_path = os.environ.get("CHROMEDRIVER_PATH", "/app/.chromedriver/bin/chromedriver")

    # Initialisation du driver
    driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)
    driver.implicitly_wait(10)

    # Tente de charger les cookies si le fichier existe
    if os.path.isfile(COOKIES_FILE):
        try:
            driver.get("https://twitter.com/")
            with open(COOKIES_FILE, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
            driver.refresh()
            # Vérifie si on est connecté
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
    Vérifie si l'utilisateur est connecté à Twitter.
    Cherche un élément présent seulement pour les comptes connectés.
    """
    try:
        driver.find_element(By.XPATH, "//a[@href='/home' and contains(@aria-label, 'Accueil')]")
        return True
    except NoSuchElementException:
        return False

def login_twitter(driver):
    """
    Procède à l'authentification Twitter via Selenium.
    """
    print("Tentative de connexion à Twitter...")
    driver.get("https://twitter.com/login")
    time.sleep(3)

    # Remplir l'email ou username
    email_field = driver.find_element(By.NAME, "text")
    email_field.send_keys(TWITTER_EMAIL)
    email_field.submit()
    time.sleep(3)

    # Remplir le mot de passe (Twitter peut présenter différents écrans intermédiaires)
    try:
        password_field = driver.find_element(By.NAME, "password")
    except NoSuchElementException:
        time.sleep(3)
        password_field = driver.find_element(By.NAME, "password")

    password_field.send_keys(TWITTER_PASSWORD)
    password_field.submit()
    time.sleep(5)

    # Vérifie si la connexion a réussi
    if not check_if_logged_in(driver):
        raise Exception("La connexion Twitter a échoué. Vérifiez vos identifiants.")

    # Sauvegarde des cookies
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("Connexion réussie et cookies sauvegardés.")

def generate_chatgpt_text(prompt_style="tweet"):
    """
    Utilise l'API OpenAI pour générer du texte (tweet, réponse, DM, etc.)
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
            temperature=0.7,
            n=1,
            stop=None
        )
        text = response.choices[0].text.strip()
        return text
    except Exception as e:
        print("Erreur lors de la génération OpenAI :", e)
        return None

def post_tweet(driver, text):
    """
    Publie un tweet avec Selenium (depuis la page de composition).
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

        # Bouton pour publier
        tweet_button = driver.find_element(By.XPATH, "//div[@data-testid='tweetButtonInline']")
        tweet_button.click()
        time.sleep(3)

        print(f"[{datetime.datetime.now()}] Tweet publié : {text}")
    except Exception as e:
        print("Erreur lors de la publication du tweet :", e)

def respond_to_popular_tweet(driver):
    """
    Exemple minimaliste : ouvre la page "Explorer" et répond au premier tweet trouvé.
    """
    try:
        driver.get("https://twitter.com/explore")
        time.sleep(5)

        tweets = driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")
        if not tweets:
            print("Aucun tweet trouvé pour y répondre.")
            return

        # Clique sur le premier tweet pour l'ouvrir
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

        # Bouton "Répondre"
        send_reply_btn = driver.find_element(By.XPATH, "//div[@data-testid='replyButton']")
        send_reply_btn.click()
        time.sleep(3)

        print(f"[{datetime.datetime.now()}] Réponse envoyée : {reply_text}")
    except Exception as e:
        print("Erreur lors de la réponse à un tweet populaire :", e)

def respond_to_direct_messages(driver):
    """
    Ouvre la page des messages et répond à quelques DMs de manière automatisée.
    """
    try:
        driver.get("https://twitter.com/messages")
        time.sleep(5)

        conversations = driver.find_elements(By.XPATH, "//div[@data-testid='conversation']")
        for convo in conversations[:2]:  # Limite à 2 pour l'exemple
            convo.click()
            time.sleep(3)

            dm_text = generate_chatgpt_text(prompt_style="dm")
            if not dm_text:
                continue

            # Saisir le message
            dm_box = driver.find_element(By.XPATH, "//div[@data-testid='dmComposerTextInput']")
            dm_box.click()
            dm_box.send_keys(dm_text)
            time.sleep(1)

            # Envoyer
            send_btn = driver.find_element(By.XPATH, "//div[@data-testid='dmComposerSendButton']")
            send_btn.click()
            time.sleep(2)

            print(f"[{datetime.datetime.now()}] DM envoyé : {dm_text}")
    except Exception as e:
        print("Erreur lors de la réponse aux messages privés :", e)

def thank_new_followers(driver):
    """
    Exemple de remerciement des nouveaux abonnés via DM (simplifié).
    """
    try:
        driver.get("https://twitter.com/notifications")
        time.sleep(5)

        # Recherche "vous suit"
        follows = driver.find_elements(By.XPATH, "//span[contains(text(), 'vous suit')]/ancestor::div[@data-testid='UserCell']")
        for f in follows[:2]:  # on limite pour l'exemple
            try:
                profile_link = f.find_element(By.XPATH, ".//a[@role='link']")
                profile_url = profile_link.get_attribute("href")
                driver.get(profile_url)
                time.sleep(3)

                # Bouton "Message"
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
    # Vérifie si l'on doit arrêter le bot
    if is_bot_stopped():
        print("Le fichier stop_bot.txt est présent. Arrêt du bot.")
        return

    # Vérifie la plage horaire 2h-6h
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
    # Boucle pour exécuter la logique en continu si souhaité.
    # Sur Heroku, on peut simplement exécuter main() une fois,
    # puis utiliser un Scheduler pour lancer le script toutes les heures.
    while True:
        main()
        print(f"Prochaine exécution dans {PUBLISH_INTERVAL} secondes...")
        time.sleep(PUBLISH_INTERVAL)
