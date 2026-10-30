# AI Radar

**AI Radar** ist eine selbst gehostete AI-/Tech-Intelligence-Anwendung. Sie sammelt Nachrichten aus konfigurierbaren RSS-/Atom-Feeds, bereitet sie mithilfe einer LLM-API auf und zeigt relevante Entwicklungen in einem interaktiven Dashboard sowie einer automatisch aktualisierten **News-Wall** für einen dauerhaft laufenden Monitor.

> **Status:** Planung und Projektsetup (MVP). Die Anwendung ist noch nicht implementiert.

## Ziel und Funktionen des MVP

- **Nachrichten sammeln:** RSS-/Atom-Quellen verwalten, alle 15 Minuten abrufen, Duplikate erkennen und nach Möglichkeit Artikelvolltexte extrahieren.
- **Mit KI aufbereiten:** Artikel zusammenfassen, kategorisieren und ihre allgemeine Bedeutung sowie persönliche Relevanz bewerten; Bewertungen nachvollziehbar begründen.
- **Personalisieren:** Interessen gewichten und aus Relevant-/Irrelevant-Feedback lernen, ohne manuelle Einstellungen stillschweigend zu überschreiben.
- **Nachrichten durchsuchen:** Volltextsuche, Kategorien-, Relevanz- und Zeitfilter sowie Sortierung.
- **News-Wall anzeigen:** Automatisch aktualisierte Vollbildansicht mit konfigurierbarer Mindest-Relevanz.
- **Deutsch und Englisch:** Sprache der Oberfläche und KI-Zusammenfassungen umschaltbar; beide Textversionen werden gespeichert.
- **Verlauf behalten:** Artikel, Analysen, Einstellungen und Feedback dauerhaft speichern.

## Geplante Architektur

Ein **modularer Monolith** mit getrenntem Web-Frontend:

| Bereich | Geplante Technologie |
|---|---|
| Backend und HTTP-API | Python, FastAPI |
| Frontend | React, TypeScript, Vite |
| Datenbank | SQLite |
| KI-Analyse | Externe LLM-API, zunächst OpenAI; austauschbarer Anbieter |
| Hintergrundverarbeitung | Python-Scheduler mit begrenzter Parallelität |
| Entwicklung | macOS |
| Späterer Betrieb | Ubuntu, Docker Compose |

Die Anwendung ist zunächst für **einen Nutzer** und den Zugriff im lokalen Netzwerk vorgesehen, nicht für eine öffentliche Bereitstellung.

## Dokumentation

- [Anforderungen](docs/requirements.md) – fachlicher Umfang und Akzeptanzgrundlage
- [Architektur](docs/architecture.md) – Komponenten, Datenflüsse und technische Entscheidungen
- [Agenten-Workflow](docs/agentic-workflow.md) – Issue-gesteuerte Entwicklung mit `/autonomous-feature`

## Projektstatus

Vorhanden sind ein FastAPI-Backend mit Health-Check (`GET /health`) und Feed-Verwaltung (`/api/feeds`), SQLite-Speicherung von Artikeln und Feeds mit Deduplizierung und ein manuell gestarteter RSS-/Atom-Abruf per CLI. Scheduler, KI-Analyse und Frontend sind noch nicht implementiert.

## Backend lokal starten

Voraussetzung: Python ≥ 3.12. Alle Befehle im Projektverzeichnis ausführen.

```bash
# Virtuelle Umgebung anlegen (einmalig, falls noch nicht vorhanden)
python3 -m venv .venv

# Backend inklusive Test-Abhängigkeiten installieren (editable)
.venv/bin/pip install -e "backend[dev]"

# Server starten (http://127.0.0.1:8000)
cd backend && ../.venv/bin/uvicorn ai_radar.main:app --reload

# In einem zweiten Terminal prüfen
curl http://127.0.0.1:8000/health   # → {"status":"ok"}
```

Die interaktive API-Dokumentation ist unter http://127.0.0.1:8000/docs erreichbar.

Die Datenbankdatei wird über `AI_RADAR_DB` festgelegt (Standard: `ai-radar.db` im Arbeitsverzeichnis, also `backend/` beim obigen Startbefehl). Schema und Migrationen werden beim Start angelegt.

```bash
cd backend && AI_RADAR_DB=../ai-radar.db ../.venv/bin/uvicorn ai_radar.main:app --reload
```

## Feeds verwalten (API)

| Methode | Pfad | Ergebnis |
|---|---|---|
| `GET` | `/api/feeds` | Liste aller Feeds |
| `POST` | `/api/feeds` | Feed anlegen (`url`, optional `name`, `enabled`, `fetch_full_text`) → `201`; ungültige URL `422`, doppelte URL `409` |
| `PATCH` | `/api/feeds/{id}` | Nur übergebene Felder ändern → `200`; unbekannte ID `404` |
| `DELETE` | `/api/feeds/{id}` | Feed entfernen → `204`; bereits gespeicherte Artikel bleiben erhalten |

```bash
curl -X POST http://127.0.0.1:8000/api/feeds \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com/feed.xml", "name": "Example"}'
```

Beim Anlegen wird der Feed nicht abgerufen. Die API hat keinen Zugriffsschutz und ist nur für `127.0.0.1` vorgesehen (D9); Anfragen mit einem anderen `Host`-Header als `127.0.0.1` oder `localhost` werden mit `400` abgelehnt (Schutz vor DNS-Rebinding).

## Feeds abrufen

```bash
# Alle aktivierten, gespeicherten Feeds (siehe /api/feeds) abrufen
.venv/bin/python -m ai_radar.ingest --db ai-radar.db

# Oder einzelne Feed-URLs als Argumente und/oder aus einer Datei (eine URL pro Zeile, # für Kommentare)
.venv/bin/python -m ai_radar.ingest --db ai-radar.db https://example.com/feed.xml
.venv/bin/python -m ai_radar.ingest --db ai-radar.db --feeds-file feeds.txt
```

Beim Abruf gespeicherter Feeds werden deaktivierte Feeds übersprungen; pro Feed werden Zeitpunkt des letzten Abrufs und des letzten Erfolgs sowie die letzte Fehlermeldung gespeichert, und neue Artikel werden mit ihrem Feed verknüpft. Beim Abruf über URL-Argumente bleiben gespeicherte Feeds unverändert.

Abgerufen werden nur öffentliche `http`/`https`-Adressen (SSRF-Schutz, siehe [Architektur](docs/architecture.md)). Fehlerhafte Feeds werden gemeldet, ohne die übrigen zu blockieren; der Exit-Code ist dann `1`.

## Tests ausführen

```bash
.venv/bin/pytest backend
```

## Continuous Integration

Die GitHub-Actions-Pipeline (`.github/workflows/ci.yml`) läuft bei Pull Requests gegen `main` und bei Pushes auf `main`. Jeder Befund lässt die Pipeline fehlschlagen.

| Job | Prüfung |
|---|---|
| Backend (Python 3.12 und 3.14) | Ruff-Linting (`E`, `F`, `I`, `B`) und pytest |
| Backend (nur Python 3.14) | `pip-audit`: bekannte Schwachstellen in installierten Python-Paketen |
| Gitleaks | Secret-Scan über die gesamte Git-Historie |
| Semgrep | Statische Sicherheitsanalyse von `backend/` mit dem öffentlichen Regelsatz `p/python`, ohne Semgrep-Account |

Der Workflow hat nur Leserechte (`contents: read`). Actions sind auf Commit-SHAs, Docker-Images auf Digests gepinnt.

Lokal ausführen (aus dem Projektverzeichnis):

```bash
cd backend
../.venv/bin/ruff check .
../.venv/bin/pytest
../.venv/bin/pip-audit --skip-editable
cd .. && gitleaks git .            # erfordert eine lokale Gitleaks-Installation
```

## Geplanter Entwicklungsansatz

Kleine, überprüfbare Änderungen statt einer Komplettimplementierung in einem Schritt. Jede Funktion wird gegen die Anforderungen entwickelt und getestet; Architekturänderungen werden bewusst entschieden und dokumentiert.

## Lizenz

Noch nicht festgelegt.
