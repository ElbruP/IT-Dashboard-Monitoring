"""Zeitsteuerung der wiederkehrenden Aufgaben.

Verwendet wird der BackgroundScheduler, da die Anwendung parallel den
Webserver betreibt. max_instances=1 verhindert, dass ein laenger laufender
Abruf ein zweites Mal gestartet wird; coalesce fasst waehrend einer Stoerung
versaeumte Ausfuehrungen zu einer einzigen zusammen.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app import config
from app.dienste import (
    benachrichtigung, meldungserfassung, schwellwertpruefung, simulator,
    versionspruefung,
)

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

STANDARDWERTE = {
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 300,
    "replace_existing": True,
}


def _sicher(funktion, bezeichnung: str):
    """Kapselt einen Auftrag, damit ein Fehler den Scheduler nicht beendet."""
    def auftrag():
        try:
            funktion()
        except Exception:
            log.exception("Auftrag '%s' fehlgeschlagen", bezeichnung)
    auftrag.__name__ = bezeichnung
    return auftrag


def starte() -> BackgroundScheduler:
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(timezone=config.ZEITZONE)

    _scheduler.add_job(
        _sicher(versionspruefung.pruefe_alle, "versionspruefung"),
        "interval", minutes=config.INTERVALL_VERSIONEN_MIN,
        id="versionspruefung", **STANDARDWERTE,
    )
    # Die Quellen bringen ihr eigenes Intervall mit; der Auftrag prueft
    # nur, welche Quelle faellig ist. Ein kurzer Takt ist daher guenstig.
    _scheduler.add_job(
        _sicher(meldungserfassung.erfasse_alle, "meldungserfassung"),
        "interval", minutes=config.INTERVALL_MELDUNGEN_MIN,
        id="meldungserfassung", **STANDARDWERTE,
    )
    _scheduler.add_job(
        _sicher(meldungserfassung.raeume_auf, "protokoll_aufraeumen"),
        "cron", hour=3, minute=30,
        id="protokoll_aufraeumen", **STANDARDWERTE,
    )
    _scheduler.add_job(
        _sicher(schwellwertpruefung.pruefe_alle, "schwellwertpruefung"),
        "interval", minutes=config.INTERVALL_SCHWELLWERTE_MIN,
        id="schwellwertpruefung", **STANDARDWERTE,
    )
    if config.SIMULATION_AKTIV:
        _scheduler.add_job(
            _sicher(simulator.erzeuge_messwerte, "simulation"),
            "interval", minutes=config.INTERVALL_SIMULATION_MIN,
            id="simulation", **STANDARDWERTE,
        )

    if config.MAIL_AKTIV:
        _scheduler.add_job(
            _sicher(benachrichtigung.versende_offene, "benachrichtigung"),
            "interval", minutes=config.INTERVALL_BENACHRICHTIGUNG_MIN,
            id="benachrichtigung", **STANDARDWERTE,
        )

    # Zusaetzlich ein taeglicher Volldurchlauf zu einer Randzeit, damit auch
    # bei langem Pruefintervall einmal je Tag alle Quellen abgefragt werden.
    _scheduler.add_job(
        _sicher(versionspruefung.pruefe_alle, "versionspruefung_taeglich"),
        "cron", hour=6, minute=0,
        id="versionspruefung_taeglich", **STANDARDWERTE,
    )

    _scheduler.start()
    log.info("Zeitsteuerung gestartet: %s",
             [job.id for job in _scheduler.get_jobs()])
    return _scheduler


def beende() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Zeitsteuerung beendet")
    _scheduler = None


def auftraege() -> list[dict]:
    if not _scheduler:
        return []
    return [
        {
            "id": job.id,
            "naechste_ausfuehrung": job.next_run_time.isoformat()
            if job.next_run_time else None,
        }
        for job in _scheduler.get_jobs()
    ]
