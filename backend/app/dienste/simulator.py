"""Simulation der Messwerte.

Im Rahmen des Projektes erfolgt kein Eingriff in produktive Systeme. Die
Messwerte werden daher durch diesen Dienst erzeugt. Die Werte verlaufen
bewusst nicht rein zufaellig, sondern entwickeln sich ausgehend vom letzten
Messwert weiter, damit die Verlaufsdarstellung realistisch wirkt.

Im Produktivbetrieb wird dieser Dienst durch die Anbindung realer Quellen
ersetzt (z. B. SNMP oder ein Agent auf dem Zielsystem).
"""

import logging
import random

from app import db

log = logging.getLogger(__name__)

SQL_METRIKEN = """
    SELECT m.metrik_id, m.bezeichnung, m.einheit,
           (SELECT w.wert FROM messwerte w
             WHERE w.metrik_id = m.metrik_id
             ORDER BY w.gemessen_am DESC LIMIT 1) AS letzter_wert
    FROM metriken m
    WHERE m.aktiv = TRUE
"""

SQL_SPEICHERN = "INSERT INTO messwerte (metrik_id, wert) VALUES (%s, %s)"

# Sinnvolle Wertebereiche je Einheit: (Minimum, Maximum, maximale Aenderung)
BEREICHE = {
    "%": (0.0, 100.0, 4.0),
    "°C": (16.0, 38.0, 0.8),
    "h": (0.0, 72.0, 1.0),
    "GB": (0.0, 4000.0, 25.0),
}
STANDARD = (0.0, 100.0, 5.0)


def _naechster_wert(letzter, einheit: str) -> float:
    minimum, maximum, schritt = BEREICHE.get(einheit, STANDARD)

    if letzter is None:
        return round(random.uniform(minimum + 0.2 * (maximum - minimum),
                                    minimum + 0.6 * (maximum - minimum)), 3)

    wert = float(letzter) + random.uniform(-schritt, schritt)
    return round(min(max(wert, minimum), maximum), 3)


def erzeuge_messwerte() -> int:
    anzahl = 0
    for metrik in db.lese_alle(SQL_METRIKEN):
        wert = _naechster_wert(metrik["letzter_wert"], metrik["einheit"])
        db.schreibe(SQL_SPEICHERN, (metrik["metrik_id"], wert))
        anzahl += 1
    log.info("Simulation: %s Messwerte erzeugt", anzahl)
    return anzahl
