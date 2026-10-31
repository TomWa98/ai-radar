# AI Radar

**AI Radar** ist eine selbst gehostete AI-/Tech-Intelligence-Anwendung für einen Nutzer. Sie sammelt Nachrichten aus RSS-/Atom-Feeds, lässt sie von einer LLM-API zusammenfassen, kategorisieren und bewerten (DE/EN) und zeigt sie in einem Dashboard und später auf einer **News-Wall** für einen dauerhaft laufenden Monitor.

> **Status:** MVP in Entwicklung. Backend und Teile des Frontends funktionieren lokal; Docker-Betrieb auf Ubuntu ist noch nicht umgesetzt.

## Stand

**Vorhanden**

- **Backend (FastAPI, SQLite):** Feed-Verwaltung, Abruf alle 15 Minuten und manuell (`/api/refresh`, CLI), Deduplizierung, optionaler Volltext (`trafilatura`) mit SSRF-Schutz.
- **Analyse:** Zusammenfassung, Kategorie, Bedeutung und persönliche Relevanz mit Begründung (DE/EN). Standard ist der kostenlose FakeAnalyzer; OpenAI ist optional und budgetbegrenzt.
- **Suche und Personalisierung:** Volltextsuche (FTS5) und Filter, manuelle Interessen, Relevanzfeedback und daraus gelernte Präferenzen.
- **Frontend (React, TypeScript, Vite):** Übersicht (Editorial Grid mit Suche, Filtern, Sortierung, Feedback, Aktualisierung), Interessen & Personalisierung, DE/EN-Umschaltung.

**Offen:** Quellen-Ansicht im Frontend (#28), News-Wall (#29), Docker-Compose-Betrieb, Zugriff aus dem LAN.

## Lokal starten

Voraussetzungen: Python ≥ 3.12, Node.js aus `frontend/.nvmrc`.

```bash
# Backend (http://127.0.0.1:8000, API-Doku unter /docs)
python3 -m venv .venv
.venv/bin/pip install -e "backend[dev]"
cd backend && ../.venv/bin/uvicorn ai_radar.main:app --reload

# Frontend in einem zweiten Terminal (http://127.0.0.1:5173)
cd frontend && npm ci --ignore-scripts && npm run dev
```

Der Vite-Dev-Server leitet `/api` und `/health` an das Backend weiter. Feeds werden bis zur Quellen-Ansicht über die API angelegt (`POST /api/feeds`, siehe `/docs`); per CLI abrufen: `.venv/bin/python -m ai_radar.ingest --db ai-radar.db`.

## Konfiguration

| Variable | Standard | Bedeutung |
|---|---|---|
| `AI_RADAR_DB` | `ai-radar.db` | SQLite-Datei (relativ zum Arbeitsverzeichnis); Schema wird beim Start angelegt |
| `AI_RADAR_FETCH_INTERVAL_MINUTES` | `15` | Abrufintervall; `0` schaltet den automatischen Abruf ab |
| `AI_RADAR_ANALYZER` | `fake` | `fake` oder `openai` |
| `AI_RADAR_ANALYSIS_CONCURRENCY` | `2` | gleichzeitige Analysen |
| `AI_RADAR_ANALYSIS_MAX_ATTEMPTS` | `3` | Versuche je Artikel |

**OpenAI (kostenpflichtig):** `AI_RADAR_ANALYZER=openai` erfordert `OPENAI_API_KEY`, `AI_RADAR_OPENAI_MODEL`, `AI_RADAR_OPENAI_INPUT_PRICE_PER_MTOK`, `AI_RADAR_OPENAI_OUTPUT_PRICE_PER_MTOK` und ein `AI_RADAR_MONTHLY_BUDGET` > 0. Token und Kosten werden je Aufruf gespeichert; bei erreichtem Budget stoppen die Aufrufe. Schlüssel nur in der Umgebung setzen, nie einchecken.

## Sicherheit

Die API hat keine Anmeldung und ist nur für `127.0.0.1` gedacht: fremde `Host`-Header ergeben `400`, Anfragen fremder Websites `403`. Feeds und Artikelseiten werden nur von öffentlichen `http(s)`-Adressen abgerufen, mit Timeouts und Größenlimits. Externe Texte werden im Frontend nur als Text dargestellt.

## Prüfungen

Wie in der CI (`.github/workflows/ci.yml`, bei Pull Requests und Pushes auf `main`):

```bash
.venv/bin/ruff check backend/ && .venv/bin/pytest backend
.venv/bin/pip-audit --skip-editable
gitleaks dir . --redact
cd frontend && npm run lint && npm test && npm run build && npm audit
```

Die CI führt zusätzlich Semgrep (`p/python`) und die Backend-Tests unter Python 3.12 und 3.14 aus.

## Dokumentation

- [Anforderungen](docs/requirements.md) – fachlicher Umfang
- [Architektur](docs/architecture.md) – Komponenten und Entscheidungen (D1–D10)
- [Frontend-Design](docs/frontend-design.md) – verbindliche Gestaltung
- [Agenten-Workflow](docs/agentic-workflow.md) – Issue-gesteuerte Entwicklung mit `/autonomous-feature`

## Lizenz

Noch nicht festgelegt.
