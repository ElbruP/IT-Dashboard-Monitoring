-- =====================================================================
-- Erweiterung 02: Informationsquellen und Meldungen
--
-- Setzt die Anforderungen des Projektantrags um:
--   - definierte, vertrauenswuerdige Quellen je Produkt und Themenbereich
--   - automatisierte Erfassung von Hersteller-, Update- und
--     Sicherheitsmeldungen einschliesslich CVE und Produktabkuendigung
--   - Zuordnung zu Produkt- und Themenbereichen
--   - Klassifizierung nach Relevanz bzw. Handlungsbedarf
--   - nachvollziehbare Protokollierung fehlerhafter Quellenabfragen
--
-- Das Skript ist mehrfach ausfuehrbar.
-- =====================================================================

SET NAMES utf8mb4;
USE monitoring;


-- ---------------------------------------------------------------------
-- 1) bereiche  –  fachliche Themenbereiche der Oberflaeche
--    Bilden die im Antrag genannten Unterbereiche ab (Linux, Nextcloud,
--    Virtualisierung, Microsoft und weitere).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bereiche (
    bereich_id   TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name         VARCHAR(60)      NOT NULL,
    beschreibung VARCHAR(255)     NULL,
    sortierung   TINYINT UNSIGNED NOT NULL DEFAULT 50,
    PRIMARY KEY (bereich_id),
    UNIQUE KEY uq_bereich (name)
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 2) quellen  –  angebundene Informationsquellen
--    Der Betriebszustand wird unmittelbar an der Quelle mitgefuehrt,
--    damit die Uebersicht ohne Auswertung des Protokolls auskommt.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quellen (
    quelle_id          SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    bezeichnung        VARCHAR(120)      NOT NULL,
    typ                ENUM('rss','nvd','endoflife','github') NOT NULL,
    adresse            VARCHAR(500)      NULL
                       COMMENT 'URL bzw. Suchbegriff, je nach Typ',
    bereich_id         TINYINT UNSIGNED  NULL,
    system_id          INT UNSIGNED      NULL
                       COMMENT 'gesetzt, wenn die Quelle genau ein Produkt betrifft',
    pruefintervall_min SMALLINT UNSIGNED NOT NULL DEFAULT 240,
    aktiv              BOOLEAN           NOT NULL DEFAULT TRUE,

    letzter_lauf       DATETIME          NULL,
    letzter_erfolg     DATETIME          NULL,
    letzter_fehler     VARCHAR(500)      NULL,
    fehler_in_folge    SMALLINT UNSIGNED NOT NULL DEFAULT 0,

    PRIMARY KEY (quelle_id),
    UNIQUE KEY uq_quelle (bezeichnung),
    KEY idx_quelle_bereich (bereich_id),
    CONSTRAINT fk_quelle_bereich FOREIGN KEY (bereich_id)
        REFERENCES bereiche (bereich_id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_quelle_system FOREIGN KEY (system_id)
        REFERENCES systeme (system_id) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 3) quellen_laeufe  –  Protokoll jeder einzelnen Abfrage
--    Erfuellt die Anforderung, fehlerhafte Abfragen nachvollziehbar zu
--    protokollieren. Erfolgreiche Laeufe werden ebenfalls erfasst, damit
--    die Verfuegbarkeit einer Quelle beurteilt werden kann.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quellen_laeufe (
    lauf_id       BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    quelle_id     SMALLINT UNSIGNED NOT NULL,
    gestartet_am  DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dauer_ms      INT UNSIGNED      NULL,
    erfolgreich   BOOLEAN           NOT NULL,
    http_status   SMALLINT UNSIGNED NULL,
    gefunden      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    neu           SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    fehlertext    VARCHAR(500)      NULL,
    PRIMARY KEY (lauf_id),
    KEY idx_lauf_quelle (quelle_id, gestartet_am DESC),
    KEY idx_lauf_fehler (erfolgreich, gestartet_am DESC),
    CONSTRAINT fk_lauf_quelle FOREIGN KEY (quelle_id)
        REFERENCES quellen (quelle_id) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 4) meldungen  –  die erfassten Informationen
--    externe_kennung ist die eindeutige Kennung beim Anbieter, etwa die
--    CVE-Nummer oder der Verweis eines Beitrags. Zusammen mit der Quelle
--    verhindert sie, dass dieselbe Information mehrfach gespeichert wird.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meldungen (
    meldung_id        BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
    quelle_id         SMALLINT UNSIGNED NOT NULL,
    bereich_id        TINYINT UNSIGNED  NULL,
    system_id         INT UNSIGNED      NULL,

    externe_kennung   VARCHAR(255)      NOT NULL,
    titel             VARCHAR(300)      NOT NULL,
    zusammenfassung   TEXT              NULL,
    verweis           VARCHAR(500)      NULL,

    kategorie         ENUM('sicherheitswarnung','cve','update','eol',
                           'produktinformation','sonstiges')
                      NOT NULL DEFAULT 'sonstiges',
    relevanz          ENUM('info','mittel','hoch','kritisch')
                      NOT NULL DEFAULT 'info',
    cvss              DECIMAL(3,1)      NULL,

    veroeffentlicht_am DATETIME         NULL,
    erfasst_am         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    gelesen_am         DATETIME         NULL,
    gelesen_von        INT UNSIGNED     NULL,

    PRIMARY KEY (meldung_id),
    UNIQUE KEY uq_meldung (quelle_id, externe_kennung),
    KEY idx_meldung_zeit (veroeffentlicht_am DESC),
    KEY idx_meldung_relevanz (relevanz, gelesen_am),
    KEY idx_meldung_bereich (bereich_id),
    CONSTRAINT fk_meldung_quelle FOREIGN KEY (quelle_id)
        REFERENCES quellen (quelle_id) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_meldung_bereich FOREIGN KEY (bereich_id)
        REFERENCES bereiche (bereich_id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_meldung_system FOREIGN KEY (system_id)
        REFERENCES systeme (system_id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_meldung_benutzer FOREIGN KEY (gelesen_von)
        REFERENCES benutzer (benutzer_id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB;


-- ---------------------------------------------------------------------
-- 5) systeme um die Bereichszuordnung erweitern
-- ---------------------------------------------------------------------
ALTER TABLE systeme
    ADD COLUMN IF NOT EXISTS bereich_id TINYINT UNSIGNED NULL AFTER kategorie_id;

-- Fremdschluessel nur anlegen, wenn er noch nicht existiert.
SET @vorhanden = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = 'monitoring'
      AND CONSTRAINT_NAME = 'fk_system_bereich'
);
SET @anweisung = IF(@vorhanden = 0,
    'ALTER TABLE systeme ADD CONSTRAINT fk_system_bereich
       FOREIGN KEY (bereich_id) REFERENCES bereiche (bereich_id)
       ON UPDATE CASCADE ON DELETE SET NULL',
    'SELECT "Fremdschluessel bereits vorhanden"');
PREPARE s FROM @anweisung; EXECUTE s; DEALLOCATE PREPARE s;


-- =====================================================================
-- SICHTEN
-- =====================================================================

-- Betriebszustand jeder Quelle. Eine Quelle gilt als gestoert, sobald
-- der letzte Lauf fehlgeschlagen ist; als veraltet, wenn seit dem
-- letzten Erfolg mehr als das Dreifache des Intervalls vergangen ist.
CREATE OR REPLACE VIEW v_quellenstatus AS
SELECT
    q.quelle_id,
    q.bezeichnung,
    q.typ,
    q.adresse,
    b.name AS bereich,
    q.pruefintervall_min,
    q.aktiv,
    q.letzter_lauf,
    q.letzter_erfolg,
    q.letzter_fehler,
    q.fehler_in_folge,
    (SELECT COUNT(*) FROM meldungen m WHERE m.quelle_id = q.quelle_id) AS meldungen,
    CASE
        WHEN q.aktiv = FALSE                     THEN 'deaktiviert'
        WHEN q.letzter_lauf IS NULL              THEN 'unbekannt'
        WHEN q.fehler_in_folge >= 3              THEN 'gestoert'
        WHEN q.fehler_in_folge > 0               THEN 'auffaellig'
        WHEN q.letzter_erfolg IS NULL            THEN 'gestoert'
        WHEN q.letzter_erfolg <
             NOW() - INTERVAL (q.pruefintervall_min * 3) MINUTE THEN 'veraltet'
        ELSE 'erreichbar'
    END AS zustand
FROM quellen q
LEFT JOIN bereiche b ON b.bereich_id = q.bereich_id;


-- Meldungen mit allen fuer die Anzeige benoetigten Bezeichnungen.
CREATE OR REPLACE VIEW v_meldungen AS
SELECT
    m.meldung_id,
    m.titel,
    m.zusammenfassung,
    m.verweis,
    m.kategorie,
    m.relevanz,
    m.cvss,
    m.veroeffentlicht_am,
    m.erfasst_am,
    m.gelesen_am,
    n.benutzername      AS gelesen_von,
    q.bezeichnung       AS quelle,
    q.typ               AS quellentyp,
    COALESCE(b.name, bs.name, 'Allgemein') AS bereich,
    s.name              AS system_name
FROM meldungen m
JOIN quellen q       ON q.quelle_id = m.quelle_id
LEFT JOIN bereiche b ON b.bereich_id = m.bereich_id
LEFT JOIN systeme s  ON s.system_id = m.system_id
LEFT JOIN bereiche bs ON bs.bereich_id = s.bereich_id
LEFT JOIN benutzer n ON n.benutzer_id = m.gelesen_von;


-- =====================================================================
-- GRUNDDATEN
-- =====================================================================

INSERT IGNORE INTO bereiche (name, beschreibung, sortierung) VALUES
('Linux',           'Debian, Ubuntu und weitere Linux-Server',        10),
('Nextcloud',       'Nextcloud Server und Zusatzanwendungen',         20),
('Virtualisierung', 'Proxmox VE und VMware',                          30),
('Backup',          'Veeam Backup & Replication',                     40),
('Microsoft',       'Microsoft 365, Windows und Windows Server',      50),
('Kommunikation',   '3CX und weitere Kommunikationsloesungen',        60),
('Sicherheit',      'uebergreifende Sicherheitsmeldungen',            70);


-- Produkte gemaess Projektantrag.
INSERT IGNORE INTO systeme
    (name, hersteller, kategorie_id, bereich_id, installierte_version,
     quelle_typ, quelle_kennung)
SELECT * FROM (
    SELECT 'Proxmox VE'    AS n, 'Proxmox Server Solutions' AS h, 1 AS k,
           (SELECT bereich_id FROM bereiche WHERE name='Virtualisierung') AS b,
           '8.2.4'  AS v, 'endoflife' AS qt, 'proxmox-ve' AS qk
    UNION ALL SELECT 'VMware ESXi', 'Broadcom', 1,
           (SELECT bereich_id FROM bereiche WHERE name='Virtualisierung'),
           '8.0 U2', 'endoflife', 'esxi'
    UNION ALL SELECT 'Veeam Backup & Replication', 'Veeam', 3,
           (SELECT bereich_id FROM bereiche WHERE name='Backup'),
           '12.1', 'manuell', NULL
    UNION ALL SELECT 'Microsoft 365', 'Microsoft', 3,
           (SELECT bereich_id FROM bereiche WHERE name='Microsoft'),
           'aktueller Kanal', 'manuell', NULL
    UNION ALL SELECT '3CX Phone System', '3CX', 2,
           (SELECT bereich_id FROM bereiche WHERE name='Kommunikation'),
           '20.0', 'manuell', NULL
    UNION ALL SELECT 'Ubuntu Server', 'Canonical', 1,
           (SELECT bereich_id FROM bereiche WHERE name='Linux'),
           '22.04', 'endoflife', 'ubuntu'
) AS neu;

-- Bereichszuordnung der bereits vorhandenen Systeme nachtragen.
UPDATE systeme SET bereich_id = (SELECT bereich_id FROM bereiche WHERE name='Nextcloud')
    WHERE name = 'Nextcloud' AND bereich_id IS NULL;
UPDATE systeme SET bereich_id = (SELECT bereich_id FROM bereiche WHERE name='Microsoft')
    WHERE name = 'Windows Server' AND bereich_id IS NULL;
UPDATE systeme SET bereich_id = (SELECT bereich_id FROM bereiche WHERE name='Linux')
    WHERE name IN ('MariaDB', 'PHP') AND bereich_id IS NULL;
UPDATE systeme SET bereich_id = (SELECT bereich_id FROM bereiche WHERE name='Backup')
    WHERE name = 'Backup-Server' AND bereich_id IS NULL;


-- ---------------------------------------------------------------------
-- Informationsquellen
--
-- HINWEIS: Die Adressen sind vor dem produktiven Einsatz zu pruefen.
-- Anbieter aendern ihre Adressen gelegentlich; eine nicht erreichbare
-- Quelle wird von der Anwendung erkannt und im Reiter "Quellen"
-- ausgewiesen, ohne dass eine Fehlmeldung entsteht.
-- ---------------------------------------------------------------------
INSERT IGNORE INTO quellen (bezeichnung, typ, adresse, bereich_id, pruefintervall_min) VALUES
('BSI CERT-Bund Sicherheitshinweise', 'rss',
 'https://wid.cert-bund.de/content/public/securityAdvisory/rss',
 (SELECT bereich_id FROM bereiche WHERE name='Sicherheit'), 120),

('Ubuntu Security Notices', 'rss',
 'https://ubuntu.com/security/notices/rss.xml',
 (SELECT bereich_id FROM bereiche WHERE name='Linux'), 240),

('Debian Security Advisories', 'rss',
 'https://www.debian.org/security/dsa',
 (SELECT bereich_id FROM bereiche WHERE name='Linux'), 240),

('Proxmox VE Ankuendigungen', 'rss',
 'https://forum.proxmox.com/forums/proxmox-ve-announcements.16/index.rss',
 (SELECT bereich_id FROM bereiche WHERE name='Virtualisierung'), 240),

('Microsoft Security Update Guide', 'rss',
 'https://api.msrc.microsoft.com/update-guide/rss',
 (SELECT bereich_id FROM bereiche WHERE name='Microsoft'), 240),

('NVD – Nextcloud', 'nvd', 'nextcloud',
 (SELECT bereich_id FROM bereiche WHERE name='Nextcloud'), 360),
('NVD – VMware ESXi', 'nvd', 'vmware esxi',
 (SELECT bereich_id FROM bereiche WHERE name='Virtualisierung'), 360),
('NVD – Veeam', 'nvd', 'veeam',
 (SELECT bereich_id FROM bereiche WHERE name='Backup'), 360),
('NVD – 3CX', 'nvd', '3cx',
 (SELECT bereich_id FROM bereiche WHERE name='Kommunikation'), 360),
('NVD – Proxmox', 'nvd', 'proxmox',
 (SELECT bereich_id FROM bereiche WHERE name='Virtualisierung'), 360);

-- Produktbezogene Quellen fuer Version und Supportende.
INSERT IGNORE INTO quellen (bezeichnung, typ, adresse, system_id, bereich_id, pruefintervall_min)
SELECT CONCAT('endoflife.date – ', s.name), 'endoflife', s.quelle_kennung,
       s.system_id, s.bereich_id, 720
FROM systeme s
WHERE s.quelle_typ = 'endoflife' AND s.quelle_kennung IS NOT NULL;

INSERT IGNORE INTO quellen (bezeichnung, typ, adresse, system_id, bereich_id, pruefintervall_min)
SELECT CONCAT('GitHub Releases – ', s.name), 'github', s.quelle_kennung,
       s.system_id, s.bereich_id, 240
FROM systeme s
WHERE s.quelle_typ = 'github' AND s.quelle_kennung IS NOT NULL;


-- Kontrollabfragen:
-- SELECT bezeichnung, typ, zustand FROM v_quellenstatus;
-- SELECT bereich, kategorie, relevanz, titel FROM v_meldungen LIMIT 20;
