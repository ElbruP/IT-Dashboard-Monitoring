"""Gemeinsame Grundlage aller Versionsquellen."""

import logging
import re
import time
from dataclasses import dataclass
from datetime import date

import httpx

from app import config

log = logging.getLogger(__name__)

# Begriffe, die einen Release als sicherheitsrelevant kennzeichnen.
SICHERHEITS_MUSTER = re.compile(
    r"\b(cve-\d{4}-\d{4,7}|security\s+(fix|release|update|advisory)"
    r"|vulnerabilit(y|ies)|sicherheitsl[uü]cke|xss|rce|sql[- ]injection)\b",
    re.IGNORECASE,
)

# Vorabversionen sollen nicht als verfuegbares Update gemeldet werden.
VORAB_MUSTER = re.compile(r"(alpha|beta|rc\d*|dev|snapshot|preview|nightly)", re.IGNORECASE)


class QuellenFehler(Exception):
    """Fehler beim Abruf einer externen Quelle."""


class KontingentFehler(QuellenFehler):
    """Das Anfragekontingent der Quelle ist erschoepft (HTTP 403 / 429)."""


@dataclass
class Versionsinfo:
    """Ergebnis einer Abfrage bei einer externen Quelle."""

    verfuegbare_version: str
    veroeffentlicht_am: date | None = None
    ist_sicherheitsupdate: bool = False
    changelog_url: str | None = None


def bereinige_version(roh: str) -> str:
    """Entfernt uebliche Praefixe, z. B. 'v30.0.1' oder 'php-8.3.9'."""
    if not roh:
        return ""
    bereinigt = roh.strip()
    bereinigt = re.sub(r"^[A-Za-z\-_]*[vV]?(?=\d)", "", bereinigt)
    return bereinigt.strip()


def _teile(version: str) -> tuple:
    """Zerlegt eine Version in vergleichbare Zahlenbestandteile."""
    zahlen = re.findall(r"\d+", version or "")
    return tuple(int(z) for z in zahlen)


def ist_neuer(verfuegbar: str, installiert: str) -> bool:
    """Vergleich nach dem Prinzip der semantischen Versionierung.

    Bei unterschiedlicher Anzahl an Stellen wird mit Nullen aufgefuellt,
    damit z. B. 10.11 und 10.11.0 als gleich gelten.
    """
    a, b = _teile(verfuegbar), _teile(installiert)
    if not a or not b:
        return False
    laenge = max(len(a), len(b))
    a += (0,) * (laenge - len(a))
    b += (0,) * (laenge - len(b))
    return a > b


def ist_vorabversion(version: str) -> bool:
    return bool(VORAB_MUSTER.search(version or ""))


def erkenne_sicherheitsupdate(*texte: str | None) -> bool:
    """Bewertet anhand des Freitextes, ob ein Sicherheitsupdate vorliegt.

    Diese Heuristik ersetzt keine Pruefung der offiziellen Meldungen des BSI
    oder der NVD, liefert im Betrieb aber bereits eine brauchbare Einstufung.
    """
    for text in texte:
        if text and SICHERHEITS_MUSTER.search(text):
            return True
    return False


def hole_json(url: str, kopfzeilen: dict | None = None) -> dict | list:
    """HTTP-Abruf mit Wiederholung.

    Ein Ausfall der Quelle fuehrt bewusst zu einer Ausnahme und nicht zu
    einem Alarm: eine gestoerte Internetverbindung darf nicht als Stoerung
    der ueberwachten Systeme erscheinen.
    """
    # Die GitHub-API weist Anfragen ohne User-Agent mit 403 zurueck.
    kopf = {"User-Agent": "IT-Monitoring-Dashboard/1.0"}
    kopf.update(kopfzeilen or {})

    letzter_fehler: Exception | None = None
    for versuch in range(1, config.HTTP_VERSUCHE + 1):
        try:
            antwort = httpx.get(
                url,
                headers=kopf,
                timeout=config.HTTP_TIMEOUT,
                follow_redirects=True,
            )
            # Ein erschoepftes Anfragekontingent ist kein Netzwerkfehler und
            # soll nicht wiederholt werden: die Sperre gilt bis zur vollen
            # Stunde. Ohne Token erlaubt GitHub 60 Anfragen pro Stunde.
            if antwort.status_code in (403, 429) and \
                    antwort.headers.get("x-ratelimit-remaining") == "0":
                zuruecksetzung = antwort.headers.get("x-ratelimit-reset", "unbekannt")
                raise KontingentFehler(
                    f"Anfragekontingent erschoepft (Zuruecksetzung: {zuruecksetzung}). "
                    "Abhilfe: Zugriffstoken hinterlegen oder Pruefintervall erhoehen."
                )
            antwort.raise_for_status()
            return antwort.json()
        except KontingentFehler:
            raise
        except Exception as fehler:
            letzter_fehler = fehler
            log.warning("Abruf %s fehlgeschlagen (Versuch %s): %s", url, versuch, fehler)
            if versuch < config.HTTP_VERSUCHE:
                time.sleep(2 ** versuch)
    raise QuellenFehler(f"Quelle nicht erreichbar: {url}") from letzter_fehler


class Quelle:
    """Schnittstelle, die jede Versionsquelle umsetzt."""

    typ: str = ""

    def ermittle(self, kennung: str | None) -> Versionsinfo:
        raise NotImplementedError
