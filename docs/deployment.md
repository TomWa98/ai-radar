# Betrieb mit Docker Compose

Betrieb von AI Radar auf einem Ubuntu-Rechner nach Entscheidung D11 in `docs/architecture.md`. Beide Images werden lokal gebaut; eine Registry wird nicht benötigt. Erreichbar ist die Anwendung nur auf dem Rechner selbst (D9).

## Einrichten und starten

Voraussetzungen: Docker Engine mit Compose-Plugin und ein Klon dieses Repositorys.

```bash
cp .env.example .env    # Werte anpassen; die Datei wird nicht eingecheckt
docker compose up -d --build
```

Die Anwendung läuft danach unter <http://127.0.0.1:8080>, die News-Wall unter <http://127.0.0.1:8080/#/news-wall>. Aufrufe über `localhost` funktionieren ebenfalls; andere Hostnamen werden abgewiesen.

Standard ist der kostenlose FakeAnalyzer. Kostenpflichtige OpenAI-Aufrufe entstehen nur mit den in der README beschriebenen Einstellungen. Enthält ein Wert in der `.env` ein `$`, muss er in einfachen Anführungszeichen stehen, weil Compose `$` sonst als Variable auswertet.

## Update

```bash
git pull --ff-only
docker compose up -d --build
```

Die SQLite-Datenbank liegt im benannten Volume `ai-radar_ai-radar-data` und bleibt bei Neustarts und Rebuilds erhalten. `docker compose down -v` löscht dieses Volume und damit alle Daten.

## Sicherheitskonzept

- **Host-Prüfung in zwei Stufen (Schutz gegen DNS-Rebinding):** nginx akzeptiert nur `127.0.0.1` und `localhost` und schließt die Verbindung bei allen anderen Hostnamen. Zulässige Anfragen behalten ihren ursprünglichen Host, und `TrustedHostMiddleware` prüft ihn im Backend erneut. Eine pauschale Freigabe aller Hosts ist unzulässig; weitere Hostnamen setzen das Zugriffskonzept aus D9 voraus.
- **Exposition:** Nur nginx veröffentlicht einen Port, gebunden an `127.0.0.1`. Das Backend hat keinen veröffentlichten Port.
- **Secrets:** Die `.env` wird erst zur Laufzeit an das Backend übergeben. `.dockerignore` hält sie aus dem Build-Kontext.

## Einschränkungen

- Das Backend hat kein Lockfile und installiert aus den Versionsangaben in `backend/pyproject.toml`. Ein Rebuild kann daher andere Versionen der Backend-Abhängigkeiten ergeben und ist nicht exakt reproduzierbar.
- Die Basisimages sind auf Version und Digest festgelegt und erhalten Sicherheitsupdates erst, wenn diese Angaben in den Dockerfiles aktualisiert werden.

## Testablauf

Belegt die Akzeptanzkriterien von Issue #30 an einer laufenden Installation. Für Schritt 7 müssen bereits Artikel vorhanden sein: In der Ansicht „Quellen“ einen Feed anlegen und abrufen. Mit dem FakeAnalyzer entstehen dabei keine Kosten.

| # | Prüfung | Befehl | Erwartet |
|---|---|---|---|
| 1 | Nur nginx ist veröffentlicht, nur an Loopback | `docker compose ps --format '{{.Service}}: {{.Publishers}}'` und `ss -ltn \| grep 8080` | Backend ohne veröffentlichten Port; Frontend und `ss` zeigen `127.0.0.1:8080` |
| 2 | Auslieferung und Weiterleitung | `curl -fsS http://127.0.0.1:8080/health` und `curl -fsS http://localhost:8080/health` | jeweils `{"status":"ok"}` |
| 3 | Kein SPA-Fallback | `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/wall` | `404`; `/#/news-wall` öffnet im Browser die News-Wall |
| 4 | nginx weist fremde Hosts ab, das Backend sieht sie nicht | `curl -sS -H 'Host: attacker.example' http://127.0.0.1:8080/api/host-check-probe`, danach `docker compose logs backend \| grep -c host-check-probe` | `curl` meldet „Empty reply from server“; Zähler `0` |
| 5 | Schreibzugriff über nginx | `curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Origin: http://127.0.0.1:8080' http://127.0.0.1:8080/api/refresh` | `202`, oder `409`, wenn bereits ein Abruf läuft |
| 6 | Backend weist fremde Hosts selbst ab | siehe Befehl unter der Tabelle | `400` |
| 7 | Daten überstehen Neustart und Rebuild | siehe Befehle unter der Tabelle | beide Zahlen sind gleich groß, oder die zweite ist größer |
| 8 | Keine `.env` in den Images | `docker compose exec -T --user root backend find / -xdev -name .env` und `docker compose exec -T frontend find / -xdev -name .env` | keine Ausgabe |

Schritt 6:

```bash
docker compose exec backend python -c "
import urllib.request as u, urllib.error as e
try:
    u.urlopen(u.Request('http://127.0.0.1:8000/health', headers={'Host': 'attacker.example'}))
except e.HTTPError as x:
    print(x.code)
"
```

Schritt 7:

```bash
count() { curl -fsS 'http://127.0.0.1:8080/api/articles?limit=1' | python3 -c 'import json,sys; print(json.load(sys.stdin)["total"])'; }
count
docker compose restart
git pull --ff-only
docker compose up -d --build --wait
count
```
