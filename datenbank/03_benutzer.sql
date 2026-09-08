-- =====================================================================
-- Datenbankbenutzer der Anwendung
-- Es werden bewusst nur die tatsaechlich benoetigten Rechte vergeben.
-- Die Anwendung darf keine Tabellen anlegen oder loeschen; strukturelle
-- Aenderungen erfolgen ausschliesslich ueber die Skripte im Ordner
-- datenbank/ durch einen Administrator.
-- =====================================================================

CREATE USER IF NOT EXISTS 'monitoring'@'localhost'
    IDENTIFIED BY 'Sommer2026!!';

-- Falls der Benutzer bereits mit einem anderen Kennwort existiert:
ALTER USER 'monitoring'@'localhost' IDENTIFIED BY 'Sommer2026!!';

GRANT SELECT, INSERT, UPDATE ON monitoring.*        TO 'monitoring'@'localhost';

-- DELETE wird nur fuer die Bereinigung alter Messwerte benoetigt.
GRANT DELETE               ON monitoring.messwerte  TO 'monitoring'@'localhost';

FLUSH PRIVILEGES;

-- Kontrolle:
-- SHOW GRANTS FOR 'monitoring'@'localhost';
