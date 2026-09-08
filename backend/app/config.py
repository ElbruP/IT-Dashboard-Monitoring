"""Konfiguration der Anwendung.

Alle Zugangsdaten werden aus Umgebungsvariablen bzw. der Datei .env gelesen
und stehen bewusst nicht im Quellcode. Die Datei .env wird nicht in die
Versionsverwaltung aufgenommen.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _int(name: str, standard: int) -> int:
    try:
        return int(os.getenv(name, standard))
    except ValueError:
        return standard


# --- Datenbank ---------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = _int("DB_PORT", 3306)
DB_NAME = os.getenv("DB_NAME", "monitoring")
DB_USER = os.getenv("DB_USER", "monitoring")
DB_PASSWORT = os.getenv("DB_PASSWORT", "")
DB_SOCKET = os.getenv("DB_SOCKET")  # optional, z. B. /run/mysqld/mysqld.sock

# --- Externe Quellen ---------------------------------------------------
# Ohne Token erlaubt die GitHub-API 60 Anfragen pro Stunde, mit Token 5000.
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HTTP_TIMEOUT = _int("HTTP_TIMEOUT", 10)
HTTP_VERSUCHE = _int("HTTP_VERSUCHE", 3)

# --- Sitzung -----------------------------------------------------------
# Der Schluessel signiert das Sitzungs-Cookie. Er muss im Betrieb gesetzt
# sein und darf nicht im Quellcode stehen; ein Wechsel meldet alle
# Benutzer ab.
SITZUNG_SCHLUESSEL = os.getenv("SITZUNG_SCHLUESSEL", "")
SITZUNG_DAUER_MIN = _int("SITZUNG_DAUER_MIN", 480)
# Nur bei HTTPS aktivieren, sonst sendet der Browser das Cookie nicht.
COOKIE_SICHER = os.getenv("COOKIE_SICHER", "false").lower() == "true"

# --- E-Mail-Benachrichtigung ------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_BENUTZER = os.getenv("SMTP_BENUTZER", "")
SMTP_KENNWORT = os.getenv("SMTP_KENNWORT", "")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
MAIL_ABSENDER = os.getenv("MAIL_ABSENDER", "monitoring@example.de")
MAIL_EMPFAENGER = [a.strip() for a in os.getenv("MAIL_EMPFAENGER", "").split(",") if a.strip()]
MAIL_AKTIV = os.getenv("MAIL_AKTIV", "false").lower() == "true"
INTERVALL_BENACHRICHTIGUNG_MIN = _int("INTERVALL_BENACHRICHTIGUNG_MIN", 10)

# --- Zeitsteuerung -----------------------------------------------------
INTERVALL_VERSIONEN_MIN = _int("INTERVALL_VERSIONEN_MIN", 60)
INTERVALL_MELDUNGEN_MIN = _int("INTERVALL_MELDUNGEN_MIN", 15)
INTERVALL_SCHWELLWERTE_MIN = _int("INTERVALL_SCHWELLWERTE_MIN", 5)
INTERVALL_SIMULATION_MIN = _int("INTERVALL_SIMULATION_MIN", 5)
SIMULATION_AKTIV = os.getenv("SIMULATION_AKTIV", "true").lower() == "true"
ZEITZONE = os.getenv("ZEITZONE", "Europe/Berlin")
