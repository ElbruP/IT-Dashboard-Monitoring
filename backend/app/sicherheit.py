"""Anmeldung, Kennwortverwaltung und Rollenpruefung.

Kennwoerter werden ausschliesslich als bcrypt-Hash gespeichert. bcrypt ist
bewusst rechenaufwendig; das Ausprobieren gestohlener Hashes wird dadurch
erheblich verlangsamt. Der Klartext verlaesst die Anmeldefunktion nie.

Die Sitzung wird in einem signierten Cookie gefuehrt. Der Cookie enthaelt
nur die Benutzerkennung und die Rolle, keine Berechtigungsnachweise.
"""

import logging
from datetime import datetime

import bcrypt
from fastapi import Depends, HTTPException, Request, status

from app import db

log = logging.getLogger(__name__)

# Rangfolge der Rollen: eine hoehere Rolle schliesst die niedrigeren ein.
RANG = {"leser": 1, "bearbeiter": 2, "admin": 3}

# Kosten-Faktor von bcrypt. 12 ist ein tragfaehiger Kompromiss zwischen
# Sicherheit und Antwortzeit (rund 0,3 s je Pruefung).
KOSTEN = 12


# --- Kennwoerter -------------------------------------------------------

def erzeuge_hash(kennwort: str) -> str:
    return bcrypt.hashpw(kennwort.encode("utf-8"), bcrypt.gensalt(KOSTEN)).decode()


def pruefe_kennwort(kennwort: str, gespeicherter_hash: str) -> bool:
    try:
        return bcrypt.checkpw(kennwort.encode("utf-8"), gespeicherter_hash.encode())
    except (ValueError, TypeError):
        # Ungueltiger Hash in der Datenbank darf nicht zu einem Serverfehler
        # fuehren, sondern gilt als fehlgeschlagene Anmeldung.
        return False


# --- Anmeldung ---------------------------------------------------------

SQL_BENUTZER = """
    SELECT benutzer_id, benutzername, passwort_hash, rolle, aktiv
    FROM benutzer
    WHERE benutzername = %s
"""


def melde_an(benutzername: str, kennwort: str) -> dict | None:
    """Prueft die Anmeldedaten und liefert den Benutzer ohne Hash zurueck."""
    benutzer = db.lese_einen(SQL_BENUTZER, (benutzername,))

    # Auch bei unbekanntem Benutzernamen wird eine Pruefung durchgefuehrt.
    # Andernfalls liesse sich an der Antwortzeit ablesen, welche Namen
    # existieren (Benutzernamen-Aufzaehlung ueber Zeitmessung).
    hash_wert = benutzer["passwort_hash"] if benutzer else erzeuge_hash("platzhalter")
    stimmt = pruefe_kennwort(kennwort, hash_wert)

    if not benutzer or not stimmt or not benutzer["aktiv"]:
        log.warning("Fehlgeschlagene Anmeldung fuer '%s'", benutzername)
        return None

    db.schreibe(
        "UPDATE benutzer SET letzter_login = NOW() WHERE benutzer_id = %s",
        (benutzer["benutzer_id"],),
    )
    log.info("Anmeldung erfolgreich: %s (%s)", benutzername, benutzer["rolle"])
    return {
        "benutzer_id": benutzer["benutzer_id"],
        "benutzername": benutzer["benutzername"],
        "rolle": benutzer["rolle"],
    }


def setze_sitzung(request: Request, benutzer: dict) -> None:
    request.session.clear()  # verhindert das Uebernehmen einer alten Sitzung
    request.session.update({
        "benutzer_id": benutzer["benutzer_id"],
        "benutzername": benutzer["benutzername"],
        "rolle": benutzer["rolle"],
        "angemeldet_seit": datetime.now().isoformat(timespec="seconds"),
    })


# --- Zugriffsschutz ----------------------------------------------------

def aktueller_benutzer(request: Request) -> dict:
    """Liefert den angemeldeten Benutzer oder bricht mit 401 ab."""
    sitzung = request.session
    if not sitzung.get("benutzer_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht angemeldet.",
        )
    return {
        "benutzer_id": sitzung["benutzer_id"],
        "benutzername": sitzung["benutzername"],
        "rolle": sitzung["rolle"],
    }


def erfordert_rolle(mindestrolle: str):
    """Erzeugt eine Abhaengigkeit, die eine Mindestrolle durchsetzt."""
    erforderlich = RANG[mindestrolle]

    def pruefer(benutzer: dict = Depends(aktueller_benutzer)) -> dict:
        if RANG.get(benutzer["rolle"], 0) < erforderlich:
            log.warning("Zugriff verweigert fuer %s (Rolle %s, noetig %s)",
                        benutzer["benutzername"], benutzer["rolle"], mindestrolle)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Diese Aktion erfordert mindestens die Rolle '{mindestrolle}'.",
            )
        return benutzer

    return pruefer
