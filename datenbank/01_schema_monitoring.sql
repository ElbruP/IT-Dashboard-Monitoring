-- =====================================================================
-- IT-Monitoring-Dashboard  |  Datenbankschema
-- DBMS:      MariaDB 10.6+ / MySQL 8.0+
-- Zeichensatz: utf8mb4 / utf8mb4_unicode_ci
-- Normalform: 3. Normalform (3NF)
-- Autor:     Elbrus
-- Version:   1.0
-- =====================================================================

-- Ohne diese Anweisung interpretiert der Client die Datei je nach
-- Voreinstellung als latin1. Zeichen wie "°C" oder Umlaute werden dann
-- doppelt kodiert gespeichert.
SET NAMES utf8mb4;

DROP DATABASE IF EXISTS monitoring;
CREATE DATABASE monitoring
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
USE monitoring;


-- ---------------------------------------------------------------------
-- 1) benutzer  –  Anmeldung und Rollen (RBAC)
-- ---------------------------------------------------------------------
CREATE TABLE benutzer (
    benutzer_id     INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    benutzername    VARCHAR(50)     NOT NULL,
    passwort_hash   CHAR(60)        NOT NULL COMMENT 'bcrypt-Hash, niemals Klartext',
    email           VARCHAR(120)    NOT NULL,
    rolle           ENUM('admin','bearbeiter','leser') NOT NULL DEFAULT 'leser',
    aktiv           BOOLEAN         NOT NULL DEFAULT TRUE,
    letzter_login   DATETIME        NULL,
    erstellt_am     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (benutzer_id),
    UNIQUE KEY uq_benutzername (benutzername),
    UNIQUE KEY uq_email (email)
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 2) system_kategorien  –  Nachschlagetabelle (vermeidet Redundanz)
-- ---------------------------------------------------------------------
CREATE TABLE system_kategorien (
    kategorie_id    TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    bezeichnung     VARCHAR(50)      NOT NULL,
    PRIMARY KEY (kategorie_id),
    UNIQUE KEY uq_kategorie (bezeichnung)
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 3) systeme  –  überwachte Server, Dienste und Anwendungen
-- ---------------------------------------------------------------------
CREATE TABLE systeme (
    system_id            INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    name                 VARCHAR(100)  NOT NULL,
    hersteller           VARCHAR(100)  NULL,
    kategorie_id         TINYINT UNSIGNED NOT NULL,
    hostname             VARCHAR(120)  NULL,
    ip_adresse           VARCHAR(45)   NULL COMMENT 'IPv4 oder IPv6',
    standort             VARCHAR(100)  NULL,
    installierte_version VARCHAR(30)   NULL,
    quelle_typ           ENUM('github','endoflife','rss','manuell')
                                       NOT NULL DEFAULT 'manuell',
    quelle_kennung       VARCHAR(150)  NULL COMMENT 'z. B. nextcloud/server',
    pruefintervall_min   SMALLINT UNSIGNED NOT NULL DEFAULT 60,
    aktiv                BOOLEAN       NOT NULL DEFAULT TRUE,
    erstellt_am          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    geaendert_am         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                       ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (system_id),
    UNIQUE KEY uq_system_name (name),
    KEY idx_kategorie (kategorie_id),
    CONSTRAINT fk_system_kategorie
        FOREIGN KEY (kategorie_id) REFERENCES system_kategorien (kategorie_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 4) versionspruefungen  –  Ergebnis jedes Update-Checks (Historie)
-- ---------------------------------------------------------------------
CREATE TABLE versionspruefungen (
    pruefung_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    system_id             INT UNSIGNED    NOT NULL,
    verfuegbare_version   VARCHAR(30)     NOT NULL,
    veroeffentlicht_am    DATE            NULL,
    ist_sicherheitsupdate BOOLEAN         NOT NULL DEFAULT FALSE,
    changelog_url         VARCHAR(255)    NULL,
    geprueft_am           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pruefung_id),
    KEY idx_system_zeit (system_id, geprueft_am DESC),
    CONSTRAINT fk_pruefung_system
        FOREIGN KEY (system_id) REFERENCES systeme (system_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 5) metriken  –  Definition einer Messgröße (nicht der Wert selbst!)
-- ---------------------------------------------------------------------
CREATE TABLE metriken (
    metrik_id    INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    system_id    INT UNSIGNED  NOT NULL,
    bezeichnung  VARCHAR(80)   NOT NULL COMMENT 'z. B. Speicherplatz frei',
    einheit      VARCHAR(20)   NOT NULL COMMENT 'z. B. %, GB, °C',
    beschreibung VARCHAR(255)  NULL,
    aktiv        BOOLEAN       NOT NULL DEFAULT TRUE,
    PRIMARY KEY (metrik_id),
    UNIQUE KEY uq_system_metrik (system_id, bezeichnung),
    CONSTRAINT fk_metrik_system
        FOREIGN KEY (system_id) REFERENCES systeme (system_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 6) messwerte  –  Zeitreihe der Messungen (wächst am stärksten)
-- ---------------------------------------------------------------------
CREATE TABLE messwerte (
    messwert_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    metrik_id   INT UNSIGNED    NOT NULL,
    wert        DECIMAL(12,3)   NOT NULL,
    gemessen_am DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (messwert_id),
    KEY idx_metrik_zeit (metrik_id, gemessen_am DESC),
    CONSTRAINT fk_messwert_metrik
        FOREIGN KEY (metrik_id) REFERENCES metriken (metrik_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 7) schwellwerte  –  Regeln für Warnungen
--    richtung = 'obergrenze'  -> Alarm, wenn Wert ÜBERschritten wird
--    richtung = 'untergrenze' -> Alarm, wenn Wert UNTERschritten wird
-- ---------------------------------------------------------------------
CREATE TABLE schwellwerte (
    schwellwert_id  INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    metrik_id       INT UNSIGNED  NOT NULL,
    richtung        ENUM('obergrenze','untergrenze') NOT NULL,
    grenze_warnung  DECIMAL(12,3) NOT NULL,
    grenze_kritisch DECIMAL(12,3) NOT NULL,
    aktiv           BOOLEAN       NOT NULL DEFAULT TRUE,
    PRIMARY KEY (schwellwert_id),
    UNIQUE KEY uq_metrik (metrik_id),
    CONSTRAINT fk_schwellwert_metrik
        FOREIGN KEY (metrik_id) REFERENCES metriken (metrik_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 8) alarme  –  ausgelöste Meldungen (Schwellwert oder neue Version)
-- ---------------------------------------------------------------------
CREATE TABLE alarme (
    alarm_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    system_id     INT UNSIGNED    NOT NULL,
    metrik_id     INT UNSIGNED    NULL COMMENT 'NULL bei Versions-Alarm',
    typ           ENUM('schwellwert','version','verfuegbarkeit') NOT NULL,
    stufe         ENUM('info','warnung','kritisch') NOT NULL,
    meldung       VARCHAR(255)    NOT NULL,
    messwert      DECIMAL(12,3)   NULL,
    ausgeloest_am DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    quittiert_am  DATETIME        NULL,
    quittiert_von INT UNSIGNED    NULL,
    PRIMARY KEY (alarm_id),
    KEY idx_offene_alarme (quittiert_am, stufe, ausgeloest_am DESC),
    KEY idx_alarm_system (system_id),
    CONSTRAINT fk_alarm_system
        FOREIGN KEY (system_id) REFERENCES systeme (system_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_alarm_metrik
        FOREIGN KEY (metrik_id) REFERENCES metriken (metrik_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_alarm_benutzer
        FOREIGN KEY (quittiert_von) REFERENCES benutzer (benutzer_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;


-- =====================================================================
-- SICHTEN (Views) für das Dashboard
-- =====================================================================

-- Versionsstatus je System (Ampel für die Kacheln)
CREATE OR REPLACE VIEW v_systemstatus AS
SELECT
    s.system_id,
    s.name,
    k.bezeichnung                AS kategorie,
    s.installierte_version,
    vp.verfuegbare_version,
    vp.ist_sicherheitsupdate,
    vp.geprueft_am,
    CASE
        WHEN vp.verfuegbare_version IS NULL                    THEN 'unbekannt'
        WHEN s.installierte_version = vp.verfuegbare_version   THEN 'aktuell'
        WHEN vp.ist_sicherheitsupdate = TRUE                   THEN 'kritisch'
        ELSE 'update_verfuegbar'
    END AS versionsstatus
FROM systeme s
JOIN system_kategorien k ON k.kategorie_id = s.kategorie_id
LEFT JOIN versionspruefungen vp
       ON vp.pruefung_id = (
            SELECT p.pruefung_id
            FROM versionspruefungen p
            WHERE p.system_id = s.system_id
            ORDER BY p.geprueft_am DESC
            LIMIT 1)
WHERE s.aktiv = TRUE;


-- Letzter Messwert je Metrik inkl. Bewertung gegen den Schwellwert
CREATE OR REPLACE VIEW v_metrikstatus AS
SELECT
    m.metrik_id,
    s.system_id,
    s.name          AS system_name,
    m.bezeichnung   AS metrik,
    m.einheit,
    mw.wert,
    mw.gemessen_am,
    sw.richtung,
    sw.grenze_warnung,
    sw.grenze_kritisch,
    CASE
        WHEN sw.schwellwert_id IS NULL THEN 'ok'
        WHEN sw.richtung = 'obergrenze'  AND mw.wert >= sw.grenze_kritisch THEN 'kritisch'
        WHEN sw.richtung = 'obergrenze'  AND mw.wert >= sw.grenze_warnung  THEN 'warnung'
        WHEN sw.richtung = 'untergrenze' AND mw.wert <= sw.grenze_kritisch THEN 'kritisch'
        WHEN sw.richtung = 'untergrenze' AND mw.wert <= sw.grenze_warnung  THEN 'warnung'
        ELSE 'ok'
    END AS status
FROM metriken m
JOIN systeme s        ON s.system_id = m.system_id
LEFT JOIN schwellwerte sw ON sw.metrik_id = m.metrik_id AND sw.aktiv = TRUE
LEFT JOIN messwerte mw
       ON mw.messwert_id = (
            SELECT w.messwert_id
            FROM messwerte w
            WHERE w.metrik_id = m.metrik_id
            ORDER BY w.gemessen_am DESC
            LIMIT 1)
WHERE m.aktiv = TRUE;


-- =====================================================================
-- TESTDATEN (Seed)
-- =====================================================================

INSERT INTO system_kategorien (bezeichnung) VALUES
('Server'), ('Dienst'), ('Anwendung'), ('Netzwerk'), ('Datenbank');

-- Anfangskennwort beider Konten: Start!2026
-- Es ist bei der Uebergabe zwingend zu aendern. Der Hash wurde mit bcrypt
-- (Kostenfaktor 12) erzeugt; der Klartext steht nirgends in der Anwendung.
INSERT INTO benutzer (benutzername, passwort_hash, email, rolle) VALUES
('admin',  '$2b$12$AILD.UvIUHiPP9o.XD4P4.nJTmKVMKHR90G/pn6ZptQ2usu7S7pZm', 'admin@example.de', 'admin'),
('lesend', '$2b$12$/pBeOaVXAhe57IylJaYQLOEexTB.tpZdOV520JgOVMtEbwE9c3xY2', 'leser@example.de', 'leser');

INSERT INTO systeme
(name, hersteller, kategorie_id, hostname, ip_adresse, standort, installierte_version, quelle_typ, quelle_kennung) VALUES
('Nextcloud',      'Nextcloud GmbH', 2, 'cloud.intern',  '192.168.10.20', 'Serverraum 1', '29.0.4',  'github',    'nextcloud/server'),
('MariaDB',        'MariaDB Found.', 5, 'db01.intern',   '192.168.10.21', 'Serverraum 1', '10.11.6', 'endoflife', 'mariadb'),
('Windows Server', 'Microsoft',      1, 'dc01.intern',   '192.168.10.10', 'Serverraum 1', '2019',    'manuell',   NULL),
('PHP',            'PHP Group',      3, 'web01.intern',  '192.168.10.22', 'Serverraum 2', '8.2.12',  'endoflife', 'php'),
('Backup-Server',  'Veeam',          1, 'bkp01.intern',  '192.168.10.30', 'Serverraum 2', '12.1',    'manuell',   NULL);

INSERT INTO versionspruefungen
(system_id, verfuegbare_version, veroeffentlicht_am, ist_sicherheitsupdate, changelog_url) VALUES
(1, '30.0.1',  '2026-07-15', TRUE,  'https://github.com/nextcloud/server/releases'),
(2, '10.11.6', '2026-05-02', FALSE, NULL),
(4, '8.3.9',   '2026-06-20', FALSE, NULL);

INSERT INTO metriken (system_id, bezeichnung, einheit, beschreibung) VALUES
(1, 'Speicherplatz frei', '%',  'Freier Speicher auf dem Datenlaufwerk'),
(1, 'CPU-Auslastung',     '%',  'Durchschnitt der letzten 5 Minuten'),
(3, 'RAM-Auslastung',     '%',  'Belegter Arbeitsspeicher'),
(5, 'Backup-Alter',       'h',  'Stunden seit dem letzten erfolgreichen Backup'),
(5, 'Serverraum-Temp.',   '°C', 'Temperatur im Serverschrank');

INSERT INTO schwellwerte (metrik_id, richtung, grenze_warnung, grenze_kritisch) VALUES
(1, 'untergrenze', 15.000, 5.000),    -- weniger als 15 % frei -> Warnung
(2, 'obergrenze',  80.000, 95.000),
(3, 'obergrenze',  85.000, 95.000),
(4, 'obergrenze',  26.000, 48.000),   -- Backup älter als 26 h -> Warnung
(5, 'obergrenze',  27.000, 32.000);

INSERT INTO messwerte (metrik_id, wert, gemessen_am) VALUES
(1, 42.500, NOW() - INTERVAL 2 HOUR),
(1, 12.300, NOW()),                   -- löst 'warnung' aus
(2, 35.000, NOW()),
(3, 96.400, NOW()),                   -- löst 'kritisch' aus
(4,  8.000, NOW()),
(5, 24.100, NOW());


-- =====================================================================
-- KONTROLLABFRAGEN
-- =====================================================================
-- SELECT * FROM v_systemstatus;
-- SELECT * FROM v_metrikstatus WHERE status <> 'ok';
-- SELECT * FROM alarme WHERE quittiert_am IS NULL ORDER BY ausgeloest_am DESC;
