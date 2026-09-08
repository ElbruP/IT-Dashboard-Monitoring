"""Benachrichtigung per E-Mail.

Versendet werden ausschliesslich Alarme, die noch nicht versendet wurden.
Mehrere Meldungen eines Durchlaufs werden zu einer einzigen E-Mail
zusammengefasst: bei einer Stoerung, die mehrere Systeme betrifft, wuerde
sonst eine Flut einzelner Nachrichten entstehen, die niemand liest.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app import config, db

log = logging.getLogger(__name__)

SQL_UNVERSENDET = """
    SELECT a.alarm_id, a.typ, a.stufe, a.meldung, a.ausgeloest_am,
           s.name AS system_name
    FROM alarme a
    JOIN systeme s ON s.system_id = a.system_id
    WHERE a.benachrichtigt_am IS NULL
      AND a.quittiert_am IS NULL
      AND a.stufe IN ('warnung', 'kritisch')
    ORDER BY FIELD(a.stufe, 'kritisch', 'warnung'), a.ausgeloest_am
    LIMIT 50
"""

SQL_MARKIEREN = "UPDATE alarme SET benachrichtigt_am = NOW() WHERE alarm_id IN ({})"


@dataclass
class Ergebnis:
    gefunden: int = 0
    versendet: int = 0
    uebersprungen: str | None = None


def _betreff(alarme: list[dict]) -> str:
    kritisch = sum(1 for a in alarme if a["stufe"] == "kritisch")
    if kritisch:
        return f"[IT-Monitoring] {kritisch} kritische Meldung(en), {len(alarme)} gesamt"
    return f"[IT-Monitoring] {len(alarme)} Warnung(en)"


def _text(alarme: list[dict]) -> str:
    zeilen = [
        "Die IT-Informationsplattform hat folgende Meldungen erzeugt:",
        "",
    ]
    for a in alarme:
        zeitpunkt = a["ausgeloest_am"].strftime("%d.%m.%Y %H:%M")
        zeilen.append(f"[{a['stufe'].upper():<8}] {zeitpunkt}  {a['system_name']}")
        zeilen.append(f"           {a['meldung']}")
        zeilen.append("")
    zeilen += [
        "Die Meldungen bleiben offen, bis sie im Dashboard quittiert werden.",
        "",
        "Diese Nachricht wurde automatisch erzeugt.",
    ]
    return "\n".join(zeilen)


def _versende(betreff: str, text: str) -> None:
    nachricht = EmailMessage()
    nachricht["Subject"] = betreff
    nachricht["From"] = config.MAIL_ABSENDER
    nachricht["To"] = ", ".join(config.MAIL_EMPFAENGER)
    nachricht.set_content(text)

    kontext = ssl.create_default_context()
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
        if config.SMTP_STARTTLS:
            server.starttls(context=kontext)
        if config.SMTP_BENUTZER:
            server.login(config.SMTP_BENUTZER, config.SMTP_KENNWORT)
        server.send_message(nachricht)


def versende_offene() -> Ergebnis:
    ergebnis = Ergebnis()

    if not config.MAIL_AKTIV:
        ergebnis.uebersprungen = "Benachrichtigung ist deaktiviert (MAIL_AKTIV)."
        return ergebnis
    if not config.SMTP_HOST or not config.MAIL_EMPFAENGER:
        ergebnis.uebersprungen = "SMTP-Server oder Empfaenger nicht konfiguriert."
        log.warning(ergebnis.uebersprungen)
        return ergebnis

    alarme = db.lese_alle(SQL_UNVERSENDET)
    ergebnis.gefunden = len(alarme)
    if not alarme:
        return ergebnis

    try:
        _versende(_betreff(alarme), _text(alarme))
    except Exception as fehler:
        # Der Versand scheitert z. B. bei einem nicht erreichbaren Mailserver.
        # Die Alarme bleiben unmarkiert und werden beim naechsten Durchlauf
        # erneut versucht; verloren geht dadurch keine Meldung.
        log.error("E-Mail-Versand fehlgeschlagen: %s", fehler)
        ergebnis.uebersprungen = f"Versand fehlgeschlagen: {fehler}"
        return ergebnis

    kennungen = [a["alarm_id"] for a in alarme]
    platzhalter = ", ".join(["%s"] * len(kennungen))
    db.schreibe(SQL_MARKIEREN.format(platzhalter), tuple(kennungen))

    ergebnis.versendet = len(kennungen)
    log.info("E-Mail mit %s Meldungen versendet", ergebnis.versendet)
    return ergebnis
