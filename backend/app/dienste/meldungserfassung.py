"""Erfassung der Meldungen aus den angebundenen Quellen.

Ablauf je Quelle:
  1. pruefen, ob das Pruefintervall abgelaufen ist
  2. Quelle abfragen und Rohmeldungen ermitteln
  3. Kategorie und Relevanz bestimmen
  4. neue Meldungen speichern, bereits bekannte uebergehen
  5. jeden Lauf protokollieren, auch den fehlgeschlagenen

Eine nicht erreichbare Quelle erzeugt bewusst keine Meldung. Sie wird im
Reiter "Quellen" als gestoert ausgewiesen. Andernfalls waere eine
Netzstoerung von einer echten Sicherheitsmeldung nicht zu unterscheiden.
"""

import logging
import re
import time
from dataclasses import dataclass

from app import db
from app.quellen import feeds
from app.quellen.basis import KontingentFehler, QuellenFehler

log = logging.getLogger(__name__)

SQL_FAELLIGE_QUELLEN = """
    SELECT quelle_id, bezeichnung, typ, adresse, bereich_id, system_id,
           pruefintervall_min, letzter_lauf
    FROM quellen
    WHERE aktiv = TRUE
      AND (letzter_lauf IS NULL
           OR letzter_lauf < NOW() - INTERVAL pruefintervall_min MINUTE)
    ORDER BY letzter_lauf IS NOT NULL, letzter_lauf
"""

SQL_ALLE_QUELLEN = """
    SELECT quelle_id, bezeichnung, typ, adresse, bereich_id, system_id,
           pruefintervall_min, letzter_lauf
    FROM quellen WHERE aktiv = TRUE
"""

SQL_LAUF = """
    INSERT INTO quellen_laeufe
        (quelle_id, dauer_ms, erfolgreich, http_status, gefunden, neu, fehlertext)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
"""

SQL_ERFOLG = """
    UPDATE quellen
    SET letzter_lauf = NOW(), letzter_erfolg = NOW(),
        letzter_fehler = NULL, fehler_in_folge = 0
    WHERE quelle_id = %s
"""

SQL_FEHLER = """
    UPDATE quellen
    SET letzter_lauf = NOW(), letzter_fehler = %s,
        fehler_in_folge = fehler_in_folge + 1
    WHERE quelle_id = %s
"""

SQL_SPEICHERN = """
    INSERT IGNORE INTO meldungen
        (quelle_id, bereich_id, system_id, externe_kennung, titel,
         zusammenfassung, verweis, kategorie, relevanz, cvss,
         veroeffentlicht_am)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


@dataclass
class Ergebnis:
    quellen: int = 0
    erfolgreich: int = 0
    gestoert: int = 0
    neue_meldungen: int = 0


# Zuordnung einer Meldung zu einem Produkt anhand des Namens. Damit
# landen zum Beispiel Nextcloud-Meldungen aus dem BSI-Feed beim richtigen
# Produkt, obwohl die Quelle selbst produktuebergreifend ist.
def _lade_produktbegriffe() -> list[tuple[int, int | None, re.Pattern]]:
    begriffe = []
    for system in db.lese_alle(
            "SELECT system_id, bereich_id, name FROM systeme WHERE aktiv = TRUE"):
        wortteile = [t for t in re.split(r"[\s\-&]+", system["name"]) if len(t) > 2]
        if not wortteile:
            continue
        muster = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in wortteile) + r")\b",
            re.IGNORECASE)
        begriffe.append((system["system_id"], system["bereich_id"], muster))
    return begriffe


def _ordne_zu(rohmeldung, quelle: dict,
              begriffe: list) -> tuple[int | None, int | None]:
    """Liefert (bereich_id, system_id) fuer eine Meldung."""
    # Ist die Quelle einem Produkt fest zugeordnet, gilt diese Zuordnung.
    if quelle["system_id"]:
        return quelle["bereich_id"], quelle["system_id"]

    text = f"{rohmeldung.titel} {rohmeldung.zusammenfassung or ''}"
    for system_id, bereich_id, muster in begriffe:
        if muster.search(text):
            return bereich_id or quelle["bereich_id"], system_id

    return quelle["bereich_id"], None


def _hole_rohmeldungen(quelle: dict):
    typ, adresse = quelle["typ"], quelle["adresse"]
    if typ == "rss":
        return feeds.lies_feed(adresse)
    if typ == "nvd":
        return feeds.lies_nvd(adresse)
    if typ == "endoflife":
        return feeds.lies_endoflife(adresse)
    if typ == "github":
        return feeds.lies_github(adresse)
    raise QuellenFehler(f"Unbekannter Quellentyp: {typ}")


def erfasse_quelle(quelle: dict, begriffe: list) -> tuple[bool, int]:
    """Fragt eine Quelle ab. Liefert (erfolgreich, Anzahl neuer Meldungen)."""
    beginn = time.monotonic()
    status = None

    try:
        rohmeldungen, status = _hole_rohmeldungen(quelle)
    except KontingentFehler as fehler:
        text = f"Anfragekontingent erschoepft: {fehler}"
        db.schreibe(SQL_LAUF, (quelle["quelle_id"],
                               int((time.monotonic() - beginn) * 1000),
                               False, status, 0, 0, text[:500]))
        db.schreibe(SQL_FEHLER, (text[:500], quelle["quelle_id"]))
        log.warning("%s: %s", quelle["bezeichnung"], text)
        return False, 0
    except Exception as fehler:
        text = f"{type(fehler).__name__}: {fehler}"
        db.schreibe(SQL_LAUF, (quelle["quelle_id"],
                               int((time.monotonic() - beginn) * 1000),
                               False, status, 0, 0, text[:500]))
        db.schreibe(SQL_FEHLER, (text[:500], quelle["quelle_id"]))
        log.warning("Quelle '%s' nicht abrufbar: %s", quelle["bezeichnung"], text)
        return False, 0

    neu = 0
    for roh in rohmeldungen:
        kategorie = roh.kategorie or feeds.bestimme_kategorie(
            roh.titel, roh.zusammenfassung)
        relevanz = feeds.bestimme_relevanz(
            kategorie, roh.cvss, roh.titel, roh.zusammenfassung)
        bereich_id, system_id = _ordne_zu(roh, quelle, begriffe)

        # INSERT IGNORE: bereits bekannte Meldungen werden anhand des
        # eindeutigen Schluessels (Quelle, externe Kennung) uebergangen.
        neu += db.schreibe(SQL_SPEICHERN, (
            quelle["quelle_id"], bereich_id, system_id,
            roh.externe_kennung, roh.titel, roh.zusammenfassung,
            roh.verweis, kategorie, relevanz, roh.cvss,
            roh.veroeffentlicht_am,
        ))

    db.schreibe(SQL_LAUF, (quelle["quelle_id"],
                           int((time.monotonic() - beginn) * 1000),
                           True, status, len(rohmeldungen), neu, None))
    db.schreibe(SQL_ERFOLG, (quelle["quelle_id"],))

    if neu:
        log.info("%s: %s neue Meldungen von %s gefundenen",
                 quelle["bezeichnung"], neu, len(rohmeldungen))
    return True, neu


def erfasse_alle(alle: bool = False) -> Ergebnis:
    """Fragt die faelligen Quellen ab.

    alle=True erzwingt die Abfrage saemtlicher Quellen unabhaengig vom
    Intervall; das wird von der Schaltflaeche "Jetzt aktualisieren"
    genutzt.
    """
    ergebnis = Ergebnis()
    begriffe = _lade_produktbegriffe()

    for quelle in db.lese_alle(SQL_ALLE_QUELLEN if alle else SQL_FAELLIGE_QUELLEN):
        ergebnis.quellen += 1
        erfolgreich, neu = erfasse_quelle(quelle, begriffe)
        if erfolgreich:
            ergebnis.erfolgreich += 1
            ergebnis.neue_meldungen += neu
        else:
            ergebnis.gestoert += 1

    log.info("Meldungserfassung beendet: %s", ergebnis)
    return ergebnis


def raeume_auf(tage: int = 180) -> int:
    """Entfernt alte Protokolleintraege.

    Die Meldungen selbst bleiben erhalten; sie bilden die Historie. Nur
    das technische Abfrageprotokoll wird begrenzt, damit die Tabelle nicht
    unbegrenzt waechst.
    """
    return db.schreibe(
        "DELETE FROM quellen_laeufe WHERE gestartet_am < NOW() - INTERVAL %s DAY",
        (tage,))
