"""Auswertung der Schwellwerte.

Die eigentliche Bewertung erfolgt in der Sicht v_metrikstatus. Dieser Dienst
liest das Ergebnis und erzeugt daraus Alarme. Damit ist sichergestellt, dass
Oberflaeche und Benachrichtigung denselben Zustand melden.
"""

import logging
from dataclasses import dataclass

from app import db

log = logging.getLogger(__name__)

SQL_ABWEICHUNGEN = """
    SELECT metrik_id, system_id, system_name, metrik, einheit,
           wert, einheit, status, richtung, grenze_warnung, grenze_kritisch
    FROM v_metrikstatus
    WHERE status <> 'ok' AND wert IS NOT NULL
"""

SQL_OFFENER_ALARM = """
    SELECT alarm_id, stufe
    FROM alarme
    WHERE metrik_id = %s AND typ = 'schwellwert' AND quittiert_am IS NULL
    ORDER BY ausgeloest_am DESC
    LIMIT 1
"""

SQL_ALARM = """
    INSERT INTO alarme (system_id, metrik_id, typ, stufe, meldung, messwert)
    VALUES (%s, %s, 'schwellwert', %s, %s, %s)
"""


@dataclass
class Ergebnis:
    geprueft: int = 0
    neue_alarme: int = 0
    verschaerft: int = 0


def _meldung(zeile: dict) -> str:
    richtung = "unterschreitet" if zeile["richtung"] == "untergrenze" else "ueberschreitet"
    grenze = (zeile["grenze_kritisch"] if zeile["status"] == "kritisch"
              else zeile["grenze_warnung"])
    return (
        f"{zeile['system_name']} – {zeile['metrik']}: "
        f"{zeile['wert']} {zeile['einheit']} {richtung} den Grenzwert "
        f"{grenze} {zeile['einheit']}."
    )[:255]


def pruefe_alle() -> Ergebnis:
    ergebnis = Ergebnis()

    for zeile in db.lese_alle(SQL_ABWEICHUNGEN):
        ergebnis.geprueft += 1
        offen = db.lese_einen(SQL_OFFENER_ALARM, (zeile["metrik_id"],))

        # Ein bereits gemeldeter Zustand wird nicht erneut gemeldet. Eine
        # Verschaerfung von 'warnung' auf 'kritisch' ist dagegen eine neue
        # Information und erzeugt einen weiteren Alarm.
        if offen and not (offen["stufe"] == "warnung" and zeile["status"] == "kritisch"):
            continue

        db.schreibe(SQL_ALARM, (
            zeile["system_id"], zeile["metrik_id"],
            zeile["status"], _meldung(zeile), zeile["wert"],
        ))

        if offen:
            ergebnis.verschaerft += 1
        else:
            ergebnis.neue_alarme += 1
        log.info("Schwellwertalarm: %s", _meldung(zeile))

    log.info("Schwellwertpruefung beendet: %s", ergebnis)
    return ergebnis
