# =====================================================================
#  IT-Monitoring-Dashboard - Einrichtung und Start
#
#  Aufruf in PowerShell aus dem Hauptordner des Projektes:
#      .\start.ps1
#
#  Das Skript ist mehrfach ausfuehrbar. Bereits erledigte Schritte
#  werden uebersprungen.
# =====================================================================

$ErrorActionPreference = "Stop"

function Schritt($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Gut($text)     { Write-Host "   OK  $text" -ForegroundColor Green }
function Warnung($text) { Write-Host "   !   $text" -ForegroundColor Yellow }
function Fehler($text)  { Write-Host "   X   $text" -ForegroundColor Red }

# --- Ins Projektverzeichnis wechseln ---------------------------------
Set-Location $PSScriptRoot
if (-not (Test-Path "backend\app\api.py")) {
    Fehler "Dieses Skript muss im Hauptordner des Projektes liegen."
    Write-Host "   Erwartet wird der Ordner mit den Unterordnern backend\, frontend\ und datenbank\."
    exit 1
}

# --- 1. Python pruefen ------------------------------------------------
Schritt "Python pruefen"
try {
    $pythonVersion = & python --version 2>&1
    Gut $pythonVersion
} catch {
    Fehler "Python wurde nicht gefunden."
    Write-Host "   Installieren von https://www.python.org/downloads/"
    Write-Host "   WICHTIG: bei der Installation 'Add Python to PATH' ankreuzen."
    exit 1
}

# --- 2. MariaDB suchen ------------------------------------------------
Schritt "MariaDB suchen"
$mysql = $null

if (Get-Command mysql -ErrorAction SilentlyContinue) {
    $mysql = "mysql"
    Gut "mysql ist im PATH verfuegbar"
} else {
    Warnung "mysql ist nicht im PATH - es wird gesucht ..."
    $kandidaten = @(
        "C:\Program Files\MariaDB*\bin\mysql.exe",
        "C:\Program Files (x86)\MariaDB*\bin\mysql.exe",
        "C:\xampp\mysql\bin\mysql.exe",
        "C:\Program Files\MySQL\*\bin\mysql.exe"
    )
    foreach ($muster in $kandidaten) {
        $treffer = Get-Item $muster -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($treffer) { $mysql = $treffer.FullName; break }
    }
    if ($mysql) {
        Gut "gefunden: $mysql"
    } else {
        Fehler "MariaDB wurde nicht gefunden."
        Write-Host "   Installieren von https://mariadb.org/download/"
        Write-Host "   Bei der Installation: Kennwort fuer 'root' setzen und"
        Write-Host "   'Install as service' ankreuzen. Danach PowerShell neu oeffnen."
        exit 1
    }
}

# --- 3. Konfiguration -------------------------------------------------
Schritt "Konfiguration anlegen"
$envDatei = "backend\.env"

if (Test-Path $envDatei) {
    Write-Host "   .env ist bereits vorhanden."
    $antwort = Read-Host "   Neu erstellen? Noetig, wenn das Kennwort nicht mehr stimmt [j/N]"
    if ($antwort -match '^[jJyY]') {
        Remove-Item $envDatei
        Warnung ".env wird neu erstellt"
    } else {
        Gut ".env wird beibehalten"
    }
}

if (Test-Path $envDatei) {
    $kennwort = $null
} else {
    $sicher   = Read-Host "   Kennwort des Datenbankbenutzers 'root'" -AsSecureString
    $kennwort = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sicher))

    # Sitzungsschluessel lokal erzeugen, damit er nirgendwo sonst existiert.
    $schluessel = & python -c "import secrets; print(secrets.token_urlsafe(48))"

    @"
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=monitoring
DB_USER=root
DB_PASSWORT=$kennwort

GITHUB_TOKEN=
HTTP_TIMEOUT=10
HTTP_VERSUCHE=3

SITZUNG_SCHLUESSEL=$schluessel
SITZUNG_DAUER_MIN=480
COOKIE_SICHER=false

INTERVALL_VERSIONEN_MIN=60
INTERVALL_SCHWELLWERTE_MIN=5
INTERVALL_SIMULATION_MIN=5
SIMULATION_AKTIV=true
ZEITZONE=Europe/Berlin

MAIL_AKTIV=false
SMTP_HOST=
SMTP_PORT=587
SMTP_BENUTZER=
SMTP_KENNWORT=
SMTP_STARTTLS=true
MAIL_ABSENDER=monitoring@example.de
MAIL_EMPFAENGER=
INTERVALL_BENACHRICHTIGUNG_MIN=10
"@ | Set-Content -Path $envDatei -Encoding UTF8

    Gut ".env erstellt, Sitzungsschluessel erzeugt"
}

# --- 4. Datenbank einrichten ------------------------------------------
Schritt "Datenbank einrichten"
if (-not $kennwort) {
    $sicher   = Read-Host "   Kennwort des Datenbankbenutzers 'root'" -AsSecureString
    $kennwort = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sicher))
}

# Ueber cmd, weil PowerShell den Operator "<" nicht unterstuetzt.
# --default-character-set verhindert doppelt kodierte Zeichen wie "Grad C".
foreach ($skript in @("01_schema_monitoring.sql", "04_erweiterung_benachrichtigung.sql")) {
    $pfad = "datenbank\$skript"
    cmd /c "`"$mysql`" -u root -p$kennwort --default-character-set=utf8mb4 < $pfad" 2>&1 |
        Where-Object { $_ -notmatch "Using a password" } | Write-Host
    if ($LASTEXITCODE -ne 0) {
        Fehler "$skript konnte nicht ausgefuehrt werden. Kennwort richtig?"
        exit 1
    }
    Gut $skript
}

# Das Kennwort hat sich soeben als richtig erwiesen. Es wird daher in die
# .env uebernommen. Andernfalls koennte dort noch ein aelteres Kennwort
# aus einem frueheren Versuch stehen und die Anwendung kaeme nicht an die
# Datenbank, obwohl die Skripte durchgelaufen sind.
$inhalt = Get-Content $envDatei
$inhalt = $inhalt -replace '^DB_PASSWORT=.*$', "DB_PASSWORT=$kennwort"
$inhalt | Set-Content -Path $envDatei -Encoding UTF8
Gut "Kennwort in .env abgeglichen"

# --- 5. Python-Umgebung -----------------------------------------------
Schritt "Python-Umgebung einrichten"
Set-Location backend

if (-not (Test-Path "venv")) {
    & python -m venv venv
    Gut "venv erstellt"
} else {
    Gut "venv ist bereits vorhanden"
}

& .\venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
Gut "Abhaengigkeiten installiert"

# --- 6. Selbsttest ----------------------------------------------------
Schritt "Verbindung pruefen"

# Der Test liegt in einer eigenen Datei. In einem PowerShell-Here-String
# waeren Anfuehrungszeichen im Python-Code nicht zuverlaessig zu maskieren.
$testDatei = Join-Path $env:TEMP "monitoring_selbsttest.py"
@'
from app import db
systeme = db.lese_alle('SELECT name, versionsstatus FROM v_systemstatus')
print(str(len(systeme)) + ' Systeme in der Datenbank')
for s in systeme:
    print('   ' + s['name'].ljust(16) + ' ' + s['versionsstatus'])
'@ | Set-Content -Path $testDatei -Encoding UTF8

$pruefung = & .\venv\Scripts\python.exe $testDatei 2>&1
Remove-Item $testDatei -ErrorAction SilentlyContinue

if ($LASTEXITCODE -ne 0) {
    Fehler "Die Datenbank ist nicht erreichbar:"
    Write-Host $pruefung
    Write-Host ""
    Write-Host "   Haeufigste Ursache: in backend\.env steht ein falsches Kennwort." -ForegroundColor Yellow
    Write-Host "   Abhilfe: backend\.env loeschen und start.ps1 erneut ausfuehren." -ForegroundColor Yellow
    exit 1
}
$pruefung | ForEach-Object { Gut $_ }

# --- 7. Starten -------------------------------------------------------
Schritt "Anwendung starten"
Write-Host ""
Write-Host "   Oberflaeche:      http://localhost:8000" -ForegroundColor White
Write-Host "   Schnittstelle:    http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "   Anmeldung:  admin / Start!2026" -ForegroundColor White
Write-Host "   Nur lesend: lesend / Start!2026" -ForegroundColor White
Write-Host ""
Write-Host "   Beenden mit Strg+C" -ForegroundColor DarkGray
Write-Host ""

Start-Process "http://localhost:8000"
& .\venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
