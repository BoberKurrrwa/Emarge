import time
import os
import logging
import stat
import time
import pytz
import schedule
import datetime
import random
import requests
import json
import re
from datetime import datetime, timedelta

# Set the timezone and allowed days
PARIS_TZ = pytz.timezone("Europe/Paris")

# Set color for better printing
GREEN = "\033[32m"
RED = "\033[31m"
BLUE = "\033[34m"
RESET = "\033[0m"

# Set variable with env from docker-compose
FORMATION = os.getenv("FORMATION")
A = os.getenv("ANNEE")
TP = os.getenv("TP")
blacklist = os.getenv("blacklist")
TOPIC = os.getenv("TOPIC")
MODE = os.getenv("MODE")
RECAP = os.getenv("RECAP")

if A == "X" or TP == "X" or FORMATION == "X":
    print(f"[{RED}-{RESET}] Vous devez d'abord définir les variables d'environnement A, TP et FORMATION dans le docker-compose.yml")
    time.sleep(5)
    quit()

if MODE == "EMARGEMENT":
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import NoSuchElementException
    from fake_useragent import UserAgent
    from bs4 import BeautifulSoup

    USERNAME = os.getenv("Us")
    PASSWORD = os.getenv("Pa")

    # Set options for selenium
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument('--lang=fr-FR')

    service = Service("/usr/local/bin/chromedriver")

    if USERNAME == 'USER' or PASSWORD == 'PASS':
        print(f"[{RED}-{RESET}] Vous devez d'abord définir les variables d'environnement USER et PASS dans le docker-compose.yml")
        time.sleep(5)
        quit()

elif MODE == "NOTIFICATION":
    if TOPIC is None and TOPIC == "XXXXXXXXXXX":
        print(f"[{RED}-{RESET}] Utiliser le mode notification sans renseigner de topic est inutile")
        time.sleep(5)
        quit()

TP = int(TP)
if not 1 <= TP <= 6:
    print(f"[{RED}-{RESET}] Votre TP doit être compris entre 1 et 6")
    time.sleep(5)
    quit()

if FORMATION not in {"cyberdefense", "cyberdata", "cyberlog"}:
    print(f"[{RED}-{RESET}] Votre FORMATION doit être cyberdefense, cyberdata ou cyberlog")
    time.sleep(5)
    quit()

API_URL = "https://planningsup.app/api/v1/calendars"
if A == "3":
    S = 5
    URL_PLANNING =  f"{API_URL}?p=ensibs.{FORMATION}.{A}emeannee.semestre{S}s{S}.tp{TP}"
    URL_PLANNING += f",ensibs.{FORMATION}.{A}emeannee.semestre{S+1}s{S+1}.tp{TP}"
elif A == "4":
    S = 7
    URL_PLANNING =  f"{API_URL}?p=ensibs.{FORMATION}.{A}emeannee.semestre{S}s{S}.tp{TP}"
    URL_PLANNING += f",ensibs.{FORMATION}.{A}emeannee.semestre{S+1}s{S+1}.tp{TP}"
elif A == "5":
    URL_PLANNING =  f"{API_URL}?p=ensibs.{FORMATION}.{A}emeannee.tp{TP}"
else:
    print(f"[{RED}-{RESET}] Votre ANNEE doit être 3, 4 ou 5")
    time.sleep(5)
    quit()

if blacklist:
    blacklists = blacklist.split(", ")
else:
    blacklists = []

logging.basicConfig(
    filename='emargement.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a'
)

def get_latest_releases_name():
    """
    Fetch the latest releases from the GitHub repo
    """
    url = f"https://api.github.com/repos/MTlyx/Emarge/releases/latest"
    response = requests.get(url)

    if response.status_code == 200:
        return response.json()["name"]

    log_print("Error fetching latest releases")
    return None

def check_for_updates(LAST_RELEASE_NAME):
    """
    Check if the git repo is up to date
    """
    latest_name = get_latest_releases_name()

    if latest_name:
        if latest_name != LAST_RELEASE_NAME:
            log_print(f"La nouvelle mise à jour {latest_name} est disponible sur github", "update")
            LAST_RELEASE_NAME = latest_name

def log_print(message, warning="info"):
    """
    Print a message with a specific color, log it and send a notification is needed.
    """
    current_time = datetime.now(PARIS_TZ).strftime("%H:%M")

    if warning == "info":
        print(f"[{BLUE}+{RESET}] {message}")
        logging.info(message)
    elif warning == "warning":
        print(f"[{RED}-{RESET}] {message}")
        logging.warning(message)
        send_notification(f"❌ {message} à {current_time}")
    elif warning == "success":
        print(f"[{GREEN}*{RESET}] {message}")
        logging.info(message)
        send_notification(f"✅ {message} à {current_time}")
    elif warning == "first":
        print(f"[{GREEN}*{RESET}] {message}")
        send_notification(f"⭐ Le programme d'émargement c'est bien lancé pour la premiere fois avec ntfy à {current_time} en mode {MODE}")
    elif warning == "update":
        print(f"[{BLUE}+{RESET}] {message}")
        send_notification(f"🆕 {message}")

# Set the last github commit hash
LAST_RELEASE_NAME = get_latest_releases_name()

def send_notification(message):
    """
    Send a notification with ntfy.sh if the TOPIC is set
    """
    if TOPIC is not None and TOPIC != "XXXXXXXXXXX":
        requests.post(f"https://ntfy.sh/{TOPIC}", data=message.encode())

def ensure_minimum_gap(events):
    """
    Ensure events are mapped to predefined time slots and only one emargement per slot.
    Time slots: 8h-9h30, 9h45-11h15, 11h30-13h00, 13h00-14h30, 14h45-16h15, 16h30-18h00, 18h15-19h45
    """
    if not events:
        return []

    # Define the predefined time slots
    TIME_SLOTS = [
        ("08:00", "09:30"),
        ("09:45", "11:15"),
        ("11:30", "13:00"),
        ("13:00", "14:30"),
        ("14:45", "16:15"),
        ("16:30", "18:00"),
        ("18:15", "19:45")
    ]

    # Sort events by start time
    sorted_events = sorted(events, key=lambda x: x["start"])

    result = []
    used_slots = set()  # Track which slots have been used for emargement

    for event in sorted_events:
        event_start = event["start"]
        event_end = event["end"]

        # Find which time slot(s) this event overlaps with
        overlapping_slots = []

        for i, (slot_start, slot_end) in enumerate(TIME_SLOTS):
            # Convert slot times to datetime objects for comparison
            slot_start_dt = event_start.replace(
                hour=int(slot_start.split(':')[0]),
                minute=int(slot_start.split(':')[1]),
                second=0,
                microsecond=0
            )
            slot_end_dt = event_start.replace(
                hour=int(slot_end.split(':')[0]),
                minute=int(slot_end.split(':')[1]),
                second=0,
                microsecond=0
            )

            # Check if event overlaps with this slot
            if (event_start < slot_end_dt and event_end > slot_start_dt):
                overlapping_slots.append(i)

        # Create emargement events for each overlapping slot that hasn't been used
        for slot_index in overlapping_slots:
            if slot_index not in used_slots:
                slot_start, slot_end = TIME_SLOTS[slot_index]

                # Create new event for this slot
                slot_start_dt = event_start.replace(
                    hour=int(slot_start.split(':')[0]),
                    minute=int(slot_start.split(':')[1]),
                    second=0,
                    microsecond=0
                )
                slot_end_dt = event_start.replace(
                    hour=int(slot_end.split(':')[0]),
                    minute=int(slot_end.split(':')[1]),
                    second=0,
                    microsecond=0
                )

                # Create new event for emargement
                emarge_event = event.copy()
                emarge_event["start"] = slot_start_dt
                emarge_event["end"] = slot_end_dt

                result.append(emarge_event)
                used_slots.add(slot_index)

    return result

def filter_events(events):
    """
    Filter the events to only keep the ones we want to emerge
    """
    filtered_events = []
    for event in events:
        if not any(blacklist in event["name"] for blacklist in blacklists):
            filtered_events.append(event)
    return filtered_events


def recup_emargement():
    """
    Perform all the process like a normal student to emerge
    """
#    options.add_argument(f"--user-agent={UserAgent(os='Linux').random}")
    driver = webdriver.Chrome()
    log_print(f"Ouverture du navigateur Selenium pour récupérer les émargements")

    driver.get("https://moodle.univ-ubs.fr/")
    time.sleep(10)

    # Select UBS on the mir
    select_element = driver.find_element(By.ID, "idp")
    dropdown = Select(select_element)
    dropdown.select_by_visible_text("Université Bretagne Sud - UBS")
    select_button = driver.find_element(By.XPATH, "//button[@type='submit' and contains(@class, 'btn-primary')]")
    select_button.click()
    time.sleep(10)

    # Enter USERNAME / PASSWORD and submit them
    username_input = driver.find_element(By.ID, "username")
    username_input.send_keys(USERNAME)
    password_input = driver.find_element(By.ID, "password")
    password_input.send_keys(PASSWORD)
    login_button = driver.find_element(By.XPATH, "//button[@type='submit' and contains(@class, 'btn-primary')]")
    login_button.click()

    # Check if the mir accepted our credentials
    try:
        driver.find_element(By.ID, "loginErrorsPanel")
        log_print(f"Identifiant ou mot de passe incorrect", "warning")
        driver.quit()
        quit()
    except NoSuchElementException:
        logging.info("Connexion réussie")
    time.sleep(10)

    # Click on the first result that contains "ENSIBS : Émargement"
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        target_span = soup.find('span', class_='sr-only', string='ENSIBS : Émargement')
        link = target_span.find_next('a')
        href = link.get('href')
        driver.get(href)
        time.sleep(10)

    except Exception as e:
        log_print(f"Impossible de trouver le lien d'émargement : {e}", "warning")
        driver.quit()
        quit()

    # Click on the Présence link on the bottom of the page
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        activity_divs = soup.find_all('div', class_='activityname')
        for div in activity_divs:
            if "Présence" in div.text:
                link = div.find('a')['href']
                driver.get(link)
                time.sleep(5)
                break
    except Exception as e:
        log_print(f"Impossible de trouver le lien d'émargement pour : {e}", "warning")
        driver.close()
        driver.quit()
        quit()

    try:
        soup = BeautifulSoup(driver.page_source, "html.parser")

        attendance_link = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"https://moodle\.univ-ubs\.fr/mod/attendance/view\.php\?id=\d+&view=2", href):
                attendance_link = href
                break

        if not attendance_link:
            raise RuntimeError("Lien vers les émargements de la semaine introuvable")

        driver.get(attendance_link)
        time.sleep(10)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        table = soup.find("table", class_="generaltable attwidth boxaligncenter")
        if not table:
            raise RuntimeError("Table 'generaltable' introuvable")

        validated = []

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # cellule points
            points_cell = row.find("td", class_="pointscol cell c3")
            if not points_cell:
                continue

            points_text = points_cell.get_text(strip=True)

            if points_text == "2 / 2":
                validated.append({
                    "raw_row": row.get_text(" ", strip=True),
                    "date": cells[0].get_text(strip=True),
                    "points": points_text
                })

        return validated
    except Exception as e:
        log_print(f"Impossible de trouver vos émargements : {e}", "warning")
        driver.close()
        driver.quit()
        quit()


    driver.quit()
    time.sleep(2)


def parse_moodle_date(date_str):
    """
    Convertit :
    '15.12.25 (lun.)08:00 - 09:30'
    → (datetime_start, datetime_end)
    """

    m = re.match(
        r"(\d{2})\.(\d{2})\.(\d{2}).*?(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})",
        date_str
    )
    if not m:
        return None, None

    day, month, year, h_start, h_end = m.groups()
    year = int("20" + year)

    start = datetime.strptime(
        f"{year}-{month}-{day} {h_start}",
        "%Y-%m-%d %H:%M"
    )
    end = datetime.strptime(
        f"{year}-{month}-{day} {h_end}",
        "%Y-%m-%d %H:%M"
    )

    return PARIS_TZ.localize(start), PARIS_TZ.localize(end)

def normalize_moodle_attendance(moodle_events):
    """
    Transforme les émargements Moodle en structure comparable
    """
    normalized = []

    for ev in moodle_events:
        start, end = parse_moodle_date(ev["date"])
        if start:
            normalized.append({
                "start": start,
                "end": end
            })

    return normalized



def parse_time(t):
    return datetime.strptime(t, "%H:%M").time()


def slot_overlap(course_start, course_end, slot_start, slot_end):
    return course_start.replace(tzinfo=None) < slot_end and course_end.replace(tzinfo=None) > slot_start


def course_used_slots(courses):
    """
    Retourne la liste des créneaux (index) utilisés par un cours
    """
    used = []

#    for course in courses:
    course_start = courses["start"]
    course_end = courses["end"]
    day = course_start.date()

    for i, (s, e) in enumerate(TIME_SLOTS):
        slot_start = datetime.combine(day, parse_time(s))#.replace(tzinfo=PARIS_TZ)
        slot_end = datetime.combine(day, parse_time(e))#.replace(tzinfo=PARIS_TZ)

        if slot_overlap(course_start, course_end, slot_start, slot_end):
            used.append({
                "start": slot_start,
                "end": slot_end,
                "name": courses["name"],
            })

    return used


def find_oublies(courses, moodle_attendance):
    """
    courses : sorties de filter_events(hours_week())
    moodle_attendance : sorties normalisées Moodle
    """
    oublie = []
    course_slots = []

    for course in courses:
        course_slots = course_used_slots(course)

        trouve = False

        for c_slot in course_slots:
            for m_slot in moodle_attendance:
                if (
                    c_slot["start"].date() == m_slot["start"].date()
                    and c_slot["start"].time() == m_slot["start"].time()
                ):
                    trouve = True
                    break
            if trouve:
                break

        if not trouve:
            oublie.append(course)

    return oublie


def hours_week():
    """
    From the API, get each courses and their starting hours for today
    """
    response = requests.get(URL_PLANNING)
    try:
        data = response.json()
    except:
        log_print(f"Impossible de récupérer les données de l'API, vérifiez votre ANNEE, SEMESTRE et TP")
        quit()

    lundi = (datetime.now(PARIS_TZ) - timedelta(days=4)).strftime("%Y-%m-%d")
    mardi = (datetime.now(PARIS_TZ) - timedelta(days=3)).strftime("%Y-%m-%d")
    mercredi = (datetime.now(PARIS_TZ) - timedelta(days=2)).strftime("%Y-%m-%d")
    jeudi = (datetime.now(PARIS_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    vendredi = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")

    # Extract relevant fields and convert timestamps
    events = [
        {
            "name": event["summary"],
            "start": datetime.fromisoformat(event["startDate"].replace('Z', '')).replace(tzinfo=pytz.timezone('UTC')).astimezone(PARIS_TZ),
            "end": datetime.fromisoformat(event["endDate"].replace('Z', '')).replace(tzinfo=pytz.timezone('UTC')).astimezone(PARIS_TZ),
        }
        for event in data.get("events", [])
        if datetime.fromisoformat(event["startDate"].replace('Z', '')).strftime("%Y-%m-%d") in (lundi, mardi, mercredi, jeudi, vendredi)
    ]

    return events


def check_forget_attendancy():
    if RECAP == "oui" :
        courses_week = filter_events(hours_week())
        emarged = recup_emargement()
        moodle_norm = normalize_moodle_attendance(emarged)
        oublie = find_oublies(courses_week, moodle_norm)
        message = ""
        if len(oublie) != 0 :
            message += "Oubli d'émargement :\n"
            for o in oublie:
                message += f"- {o['name']} le {o['start'].strftime('%d/%m/20%y')} de {o['start'].strftime('%H:%M')} à {o['end'].strftime('%H:%M')}\n"
        else :
            message += "Aucun oubli d'émargement cette semaine !"

        send_notification(message)
        log_print(message)

def hours_Emarge():
    """
    From the API, get each courses and their starting hours for today
    """
    response = requests.get(URL_PLANNING)
    try:
        data = response.json()
    except json.decoder.JSONDecodeError:
        logging.error("Impossible de récupérer les données de l'API, vérifiez votre ANNEE, SEMESTRE et TP")
        print(f"[{RED}-{RESET}] Impossible de récupérer les données de l'API, vérifiez votre ANNEE, SEMESTRE et TP")
        quit()

    today_str = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    # Extract relevant fields and convert timestamps
    events = [
        {
            "name": event["name"],
            "start": datetime.fromtimestamp(event["start"] / 1000, tz=PARIS_TZ),
            "end": datetime.fromtimestamp(event["end"] / 1000, tz=PARIS_TZ),
        }
        for planning in data.get("plannings", [])
        for event in planning.get("events", [])
        if (datetime.fromtimestamp(event["start"] / 1000, tz=PARIS_TZ)).strftime("%Y-%m-%d") == today_str
        and (datetime.fromtimestamp(event["start"] / 1000, tz=PARIS_TZ)) + timedelta(minutes=15) > datetime.now(PARIS_TZ)
        and 8 <= (datetime.fromtimestamp(event["start"] / 1000, tz=PARIS_TZ)).hour <= 18
    ]

    # Return the list of events of today
    return events

def emarge(course_name):
    """
    Perform all the process like a normal student to emerge
    """
    options.add_argument(f"--user-agent={UserAgent(os='Linux').random}")
    driver = webdriver.Chrome(service=service, options=options)
    log_print(f"Ouverture du navigateur Selenium pour {course_name}")

    driver.get("https://moodle.univ-ubs.fr/")
    time.sleep(10)

    # Select UBS on the mir
    select_element = driver.find_element(By.ID, "idp")
    dropdown = Select(select_element)
    dropdown.select_by_visible_text("Université Bretagne Sud - UBS")
    select_button = driver.find_element(By.XPATH, "//button[@type='submit' and contains(@class, 'btn-primary')]")
    select_button.click()
    time.sleep(10)

    # Enter USERNAME / PASSWORD and submit them
    username_input = driver.find_element(By.ID, "username")
    username_input.send_keys(USERNAME)
    password_input = driver.find_element(By.ID, "password")
    password_input.send_keys(PASSWORD)
    login_button = driver.find_element(By.XPATH, "//button[@type='submit' and contains(@class, 'btn-primary')]")
    login_button.click()

    # Check if the mir accepted our credentials
    try:
        driver.find_element(By.ID, "loginErrorsPanel")
        log_print(f"Identifiant ou mot de passe incorrect", "warning")
        driver.quit()
        quit()
    except NoSuchElementException:
        logging.info("Connexion réussie")
    time.sleep(10)

    # Click on the first result that contains "ENSIBS : Émargement"
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        target_span = soup.find('span', class_='sr-only', string='ENSIBS : Émargement')
        link = target_span.find_next('a')
        href = link.get('href')
        driver.get(href)
        time.sleep(10)

    except Exception as e:
        log_print(f"Impossible de trouver le lien d'émargement pour {course_name} : {e}", "warning")
        driver.quit()
        quit()

    # Click on the Présence link on the bottom of the page
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        activity_divs = soup.find_all('div', class_='activityname')
        for div in activity_divs:
            if "Présence" in div.text:
                link = div.find('a')['href']
                driver.get(link)
                time.sleep(5)
                break
    except Exception as e:
        log_print(f"Impossible de trouver le lien d'émargement pour {course_name} : {e}", "warning")
        driver.close()
        driver.quit()
        quit()

    # Click on Envoyer le statut de présence or Submit attendance in english
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        link = soup.find('a', string='Envoyer le statut de présence')
        href = link.get('href')
        driver.get(href)
        time.sleep(5)
        log_print(f"Emargement réussi pour {course_name}", "success")
    except:
        try:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            link = soup.find('a', string='Submit attendance')
            href = link.get('href')
            driver.get(href)
            time.sleep(5)
            log_print(f"Emargement réussi pour {course_name}", "success")
        except:
            log_print(f"Impossible d'émarger pour {course_name}", "warning")

    driver.quit()
    time.sleep(2)

def schedule_random_times():
    """ 
    Set a date to emarge for each events of today.
    """
    check_for_updates(LAST_RELEASE_NAME)
    schedule.clear()
    schedule.every().day.at("07:00").do(schedule_random_times)
    times = []

    if datetime.now(PARIS_TZ).weekday() == 4:
        schedule.every().day.at("20:00").do(check_forget_attendancy)

    # Check if current day is weekend (5 = Saturday, 6 = Sunday)
    if datetime.now(PARIS_TZ).weekday() >= 5:
        return

    # Get from the API all the courses of the student for today
    events_today = ensure_minimum_gap(hours_Emarge())
    events_filtered = filter_events(events_today)

    # Add a timedelta
    for event in events_filtered:
        if MODE == "EMARGEMENT":
            start_hour = (event["start"] + timedelta(minutes=random.randint(5, 10))).strftime("%H:%M")
            event_name = event["name"]
            schedule.every().day.at(start_hour).do(emarge, event_name)
        elif MODE == "NOTIFICATION":
            start_hour = event["start"].strftime("%H:%M")
            message = f'Il faut émarger pour {event["name"]}'
            schedule.every().day.at(start_hour).do(log_print, message, "update")
        times.append(f"{start_hour}")

    if times:
        times.sort()
        log_print(f"Emargement prévu à {', '.join(times)}")
    else:
        log_print(f"Aucun cours à venir aujourd'hui")

def main():
    """
    Start the script the Emarge bot
    """
    if not os.path.exists("ntfy"):
        log_print(f"Démarrage du programme d'émargement...", "first")
        with open("ntfy", "w") as f:
            pass

    schedule_random_times()

    # While loop to check every minute if it's the time to emarge
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()
