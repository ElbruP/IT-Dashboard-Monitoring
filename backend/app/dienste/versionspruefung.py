"""Abruf und Auswertung der Versionsinformationen.

Ablauf je System:
  1. passende Quelle anhand von quelle_typ auswaehlen
  2. verfuegbare Version abrufen
  3. Ergebnis in versionspruefungen historisieren
  4. bei einem neuen Stand einen Alarm erzeugen
"""

import logging
from dataclasses import dataclass

from app import db
from app.quellen.basis import KontingentFehler, QuellenFehler, ist_neuer
from app.quellen.anbieter import hole_quelle

log = logging.getLogger(__name__)

SQL_SYSTEME = """
    SELECT system_id, name, installierte_version, quelle_typ, quelle_kennung
    FROM systeme
    WHERE aktiv = TRUE AND quelle_typ <> 'manuell'
"""

SQL_LETZTE_PRUEFUNG = """
    SELECT verfuegbare_version
    FROM versionspruefungen
    WHERE system_id = %s
    ORDER BY geprueft_am DESC
    LIMIT 1
"""

SQL_SPEICHERN = """
    INSERT INTO versionspruefungen
        (system_id, verfuegbare_version, veroeffentlicht_am,
         ist_sicherheitsupdate, changelog_url)
    VALUES (%s, %s, %s, %s, %s)
"""

SQL_OFFENER_ALARM = """
    SELECT alarm_id
    FROM alarme
    WHERE system_id = %s AND typ = 'version' AND quittiert_am IS NULL
    LIMIT 1
"""

SQL_ALARM = """
    INSERT INTO alarme (system_id, typ, stufe, meldung)
    VALUES (%s, 'version', %s, %s)
"""


@dataclass
class Ergebnis:
    geprueft: int = 0
    aktualisiert: int = 0
    alarme: int = 0
    fehler: int = 0


def _erzeuge_alarm(system: dict, info) -> bool:
    """Legt einen Alarm an, sofern nicht bereits ein offener Alarm besteht.

    Ohne diese Pruefung entstuende bei jedem Durchlauf ein neuer Eintrag und
    die Uebersicht waere nach kurzer Zeit unbrauchbar (Alarmflut).
    """
    if db.lese_einen(SQL_OFFENER_ALARM, (system["system_id"],)):
        return False

    stufe = "kritisch" if info.ist_sicherheitsupdate else "warnung"
    zusatz = " (Sicherheitsupdate)" if info.ist_sicherheitsupdate else ""
    meldung = (
        f"Neue Version {info.verfuegbare_version} verfuegbar"
        f"{zusatz}; installiert ist {system['installierte_version']}."
    )
    db.schreibe(SQL_ALARM, (system["system_id"], stufe, meldung[:255]))
    log.info("Alarm erzeugt fuer %s: %s", system["name"], meldung)
    return True


def pruefe_system(system: dict, ergebnis: Ergebnis) -> None:
    try:
        quelle = hole_quelle(system["quelle_typ"])
        info = quelle.ermittle(system["quelle_kennung"])
    except KontingentFehler as fehler:
        # Bewusst nur protokollieren: ein erschoepftes Kontingent ist kein
        # Zustand des ueberwachten Systems.
        log.warning("%s: %s", system["name"], fehler)
        ergebnis.fehler += 1
        return
    except QuellenFehler as fehler:
        log.warning("%s: Quelle nicht auswertbar: %s", system["name"], fehler)
        ergebnis.fehler += 1
        return

    ergebnis.geprueft += 1

    vorher = db.lese_einen(SQL_LETZTE_PRUEFUNG, (system["system_id"],))
    bekannt = vorher["verfuegbare_version"] if vorher else None

    # Nur schreiben, wenn sich der Stand geaendert hat. Andernfalls waechst
    # die Historie ohne Erkenntnisgewinn.
    if bekannt == info.verfuegbare_version:
        return

    db.schreibe(SQL_SPEICHERN, (
        system["system_id"],
        info.verfuegbare_version,
        info.veroeffentlicht_am,
        info.ist_sicherheitsupdate,
        info.changelog_url,
    ))
    ergebnis.aktualisiert += 1
    log.info("%s: neuer Stand %s (vorher %s)",
             system["name"], info.verfuegbare_version, bekannt or "unbekannt")

    if ist_neuer(info.verfuegbare_version, system["installierte_version"] or ""):
        if _erzeuge_alarm(system, info):
            ergebnis.alarme += 1


def pruefe_alle() -> Ergebnis:
    ergebnis = Ergebnis()
    for system in db.lese_alle(SQL_SYSTEME):
        try:
            pruefe_system(system, ergebnis)
        except Exception as fehler:  # pragma: no cover
            log.exception("Unerwarteter Fehler bei %s: %s", system["name"], fehler)
            ergebnis.fehler += 1
    log.info("Versionspruefung beendet: %s", ergebnis)
    return ergebnis
