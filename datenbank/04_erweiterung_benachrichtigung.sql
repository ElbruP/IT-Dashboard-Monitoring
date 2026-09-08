-- =====================================================================
-- Erweiterung 01: Nachverfolgung der E-Mail-Benachrichtigung
-- Anzuwenden auf eine bestehende Datenbank. Das Skript ist mehrfach
-- ausfuehrbar, ohne einen Fehler zu erzeugen.
-- =====================================================================

SET NAMES utf8mb4;
USE monitoring;

-- Ohne dieses Feld liesse sich nicht unterscheiden, ob ein Alarm bereits
-- versendet wurde. Bei jedem Durchlauf wuerde dieselbe Meldung erneut
-- verschickt.
ALTER TABLE alarme
    ADD COLUMN IF NOT EXISTS benachrichtigt_am DATETIME NULL
        COMMENT 'Zeitpunkt des E-Mail-Versands, NULL = noch nicht versendet'
        AFTER ausgeloest_am;

-- Index fuer die Abfrage der noch nicht versendeten Meldungen.
CREATE INDEX IF NOT EXISTS idx_unversendet
    ON alarme (benachrichtigt_am, stufe);

-- Kontrolle:
-- SHOW COLUMNS FROM alarme LIKE 'benachrichtigt_am';
