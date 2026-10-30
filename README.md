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

Vorhanden sind ein FastAPI-Backend mit Health-Check (`GET /health`) und Feed-Verwaltung (`/api/feeds`), SQLite-Speicherung von Artikeln und Feeds mit Deduplizierung, ein automatischer Feed-Abruf alle 15 Minuten im Serverprozess mit anschließender Analyse (derzeit mit dem FakeAnalyzer) und ein manuell gestarteter Abruf per CLI. Echter LLM-Anbieter und Frontend sind noch nicht implementiert.

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

Solange der Server läuft, ruft er alle aktivierten, gespeicherten Feeds direkt nach dem Start und danach alle 15 Minuten ab. Das Intervall in Minuten lässt sich mit `AI_RADAR_FETCH_INTERVAL_MINUTES` ändern; `0` schaltet den automatischen Abruf ab. Läuft ein Abruf noch, wird der nächste übersprungen statt doppelt gestartet.

Ein Abruf lässt sich auch manuell anstoßen:

```bash
curl -X POST http://127.0.0.1:8000/api/refresh   # → 202 (gestartet) oder 409 (läuft bereits)
curl http://127.0.0.1:8000/api/refresh           # → {"running": …, "last_started_at": …, "last_finished_at": …}
```

Nach jedem Abruf im Serverprozess werden neue Artikel analysiert (Status `new` → `processing` → `analyzed` bzw. `failed`). Fehlgeschlagene Analysen werden in späteren Läufen erneut versucht, bis `AI_RADAR_ANALYSIS_MAX_ATTEMPTS` (Standard 3) erreicht ist; Fehlermeldung und Anzahl der Versuche werden gespeichert. `AI_RADAR_ANALYSIS_CONCURRENCY` (Standard 2) begrenzt gleichzeitige Analysen. Standard für `AI_RADAR_ANALYZER` ist `fake` (deterministischer FakeAnalyzer, keine kostenpflichtigen API-Aufrufe).

### OpenAI-Analyzer (kostenpflichtig)

`AI_RADAR_ANALYZER=openai` nutzt die OpenAI-API (Chat Completions mit strukturierter JSON-Ausgabe). Der Server startet damit nur, wenn alle folgenden Umgebungsvariablen gesetzt sind:

| Variable | Bedeutung |
|---|---|
| `OPENAI_API_KEY` | API-Schlüssel (nur in der Umgebung, nie einchecken) |
| `AI_RADAR_OPENAI_MODEL` | Modellname |
| `AI_RADAR_OPENAI_INPUT_PRICE_PER_MTOK`, `AI_RADAR_OPENAI_OUTPUT_PRICE_PER_MTOK` | Preis je 1 Mio. Input-/Output-Token (> 0) |
| `AI_RADAR_MONTHLY_BUDGET` | Monatsbudget in derselben Währung; Standard `0` = keine Live-Aufrufe (Startfehler) |

Token-Verbrauch und geschätzte Kosten werden je Aufruf in `llm_calls` gespeichert. Ist das Budget im laufenden Kalendermonat (UTC) erreicht, finden keine weiteren Aufrufe statt; betroffene Artikel werden mit dem Grund „Budget“ als `failed` markiert und ohne Verbrauch eines Versuchs später erneut analysiert. Per CLI abgerufene Artikel werden beim nächsten Lauf des Servers analysiert.

Manuelle und automatische Abrufe laufen nie gleichzeitig. Anfragen, die ein Browser von einer fremden Website sendet (`Origin` nicht `127.0.0.1`/`localhost`), werden mit `403` abgelehnt.

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

## Interessen verwalten (API)

| Methode | Pfad | Ergebnis |
|---|---|---|
| `GET` | `/api/interests` | Liste der manuellen Interessen |
| `POST` | `/api/interests` | Interesse anlegen (`topic`, `weight`: `low`/`medium`/`high`, Standard `medium`) → `201`; doppeltes Thema (ohne Groß-/Kleinschreibung) `409`; ungültige Eingabe oder mehr als 100 Interessen `422` |
| `PATCH` | `/api/interests/{id}` | Thema und/oder Gewichtung ändern → `200`; unbekannte ID `404` |
| `DELETE` | `/api/interests/{id}` | Interesse entfernen → `204` |

Themen werden von überflüssigen Leerzeichen bereinigt (max. 100 Zeichen, keine Steuerzeichen). Manuelle Interessen ändert nur der Nutzer; sie werden nie automatisch angepasst. Gelernte Präferenzen werden getrennt geführt.

## Relevanzfeedback (API)

| Methode | Pfad | Ergebnis |
|---|---|---|
| `PUT` | `/api/articles/{id}/feedback` | Bewertung setzen oder ändern (`{"rating": "relevant"}` bzw. `"irrelevant"`) → `200`; unbekannter Artikel `404` |
| `DELETE` | `/api/articles/{id}/feedback` | Bewertung entfernen → `204` (auch wenn keine vorhanden war); unbekannter Artikel `404` |

Pro Artikel gibt es höchstens eine Bewertung. Feedback ändert keine bestehenden Analysen.

## Gelernte Präferenzen (API)

Aus dem Feedback werden regelbasiert (ohne Machine Learning) Präferenzen abgeleitet: Je Thema-Stichwort eines bewerteten Artikels zählt „relevant“ +1 und „irrelevant“ −1; ab 3 Bewertungen wird das Thema als gelernte Präferenz geführt. Neue Analysen erhalten die stärksten gelernten Präferenzen; bestehende Analysen werden nicht neu berechnet.

| Methode | Pfad | Ergebnis |
|---|---|---|
| `GET` | `/api/preferences` | `{"learned": [{"topic", "score", "relevant", "irrelevant", "ratings"}], "last_reset_at"}` – getrennt von den manuellen Interessen (`/api/interests`) |
| `DELETE` | `/api/preferences` | Gelernte Präferenzen zurücksetzen → `204`; Feedback und manuelle Interessen bleiben erhalten |

## Feeds abrufen

```bash
# Alle aktivierten, gespeicherten Feeds (siehe /api/feeds) abrufen
.venv/bin/python -m ai_radar.ingest --db ai-radar.db

# Oder einzelne Feed-URLs als Argumente und/oder aus einer Datei (eine URL pro Zeile, # für Kommentare)
.venv/bin/python -m ai_radar.ingest --db ai-radar.db https://example.com/feed.xml
.venv/bin/python -m ai_radar.ingest --db ai-radar.db --feeds-file feeds.txt
```

Beim Abruf gespeicherter Feeds werden deaktivierte Feeds übersprungen; pro Feed werden Zeitpunkt des letzten Abrufs und des letzten Erfolgs sowie die letzte Fehlermeldung gespeichert, und neue Artikel werden mit ihrem Feed verknüpft. Beim Abruf über URL-Argumente bleiben gespeicherte Feeds unverändert.

Für Feeds mit `fetch_full_text: true` (Standard: aus) wird zu jedem neuen Artikel die Artikelseite abgerufen und mit `trafilatura` von Navigation, Werbung und ähnlichen Elementen bereinigt. Der Abruf nutzt denselben SSRF-Schutz und dieselben Limits wie der Feed-Abruf, ohne Cookies oder Logins. Ist der Volltext nicht frei verfügbar (Fehler, HTTP 401/402/403, leerer Extrakt oder Paywall-Kennzeichnung `isAccessibleForFree: false`), bleibt der Feed-Auszug die Analysebasis. Der Feed-Auszug wird immer zusätzlich gespeichert. Nutzungsbedingungen der Quellen verantwortet der Nutzer (D3).

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
