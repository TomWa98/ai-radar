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

## Projektstatus

Ein minimales FastAPI-Backend mit Health-Check (`GET /health`) ist vorhanden. Feed-Abruf, KI-Analyse, Datenbank und Frontend sind noch nicht implementiert.

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

## Tests ausführen

```bash
.venv/bin/pytest backend
```

## Geplanter Entwicklungsansatz

Kleine, überprüfbare Änderungen statt einer Komplettimplementierung in einem Schritt. Jede Funktion wird gegen die Anforderungen entwickelt und getestet; Architekturänderungen werden bewusst entschieden und dokumentiert.

## Lizenz

Noch nicht festgelegt.
