"""Datenbankzugriff.

Die Anwendungsschicht bleibt bewusst schlank: die Bewertung der Zustände
(ok / warnung / kritisch) liegt in den Sichten v_systemstatus und
v_metrikstatus. Hier wird ausschliesslich gelesen und geschrieben.
"""

import logging
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

log = logging.getLogger(__name__)


def _verbindungsparameter() -> dict:
    parameter = {
        "user": config.DB_USER,
        "password": config.DB_PASSWORT,
        "database": config.DB_NAME,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    if config.DB_SOCKET:
        parameter["unix_socket"] = config.DB_SOCKET
    else:
        parameter["host"] = config.DB_HOST
        parameter["port"] = config.DB_PORT
    return parameter


@contextmanager
def verbindung():
    """Stellt eine Verbindung bereit und gibt sie danach zuverlaessig frei."""
    conn = pymysql.connect(**_verbindungsparameter())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def lese_alle(sql: str, parameter: tuple = ()) -> list[dict]:
    with verbindung() as conn, conn.cursor() as cur:
        cur.execute(sql, parameter)
        return cur.fetchall()


def lese_einen(sql: str, parameter: tuple = ()) -> dict | None:
    with verbindung() as conn, conn.cursor() as cur:
        cur.execute(sql, parameter)
        return cur.fetchone()


def schreibe(sql: str, parameter: tuple = ()) -> int:
    """Fuehrt eine schreibende Anweisung aus und liefert die Anzahl der Zeilen."""
    with verbindung() as conn, conn.cursor() as cur:
        anzahl = cur.execute(sql, parameter)
        return anzahl


def pruefe_erreichbarkeit() -> bool:
    try:
        lese_einen("SELECT 1 AS treffer")
        return True
    except Exception as fehler:  # pragma: no cover
        log.error("Datenbank nicht erreichbar: %s", fehler)
        return False
