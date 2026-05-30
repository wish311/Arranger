# Arranger

Arranger is a local FastAPI service that organizes Radarr movies and Sonarr series into the correct configured root folders by using the Radarr/Sonarr APIs. It is designed for folders such as Kids, Family, Anime, Documentary, and General while avoiding unsafe moves during downloads, imports, or incomplete TV states.

Arranger **does not perform normal moves with raw filesystem commands**. It updates Radarr/Sonarr item paths/root folders through their APIs and asks the Arr application to move files so that the Arr database, import logic, and future imports stay consistent.

## Safety model

- `dry_run` defaults to `true` and blocks every destructive API update.
- All move decisions are logged and stored in SQLite.
- Real moves are refused if the live API schema cannot be verified.
- Real moves are refused if the target root is not returned by `/api/v3/rootfolder`.
- Real moves are refused if a queue/import item exists for the same media.
- Real moves are refused if the current path is under configured download/temp folders.
- Sonarr uses a stricter `SonarrSafetyGate` because partial TV seasons and future episodes are riskier than movies.

## How Sonarr moves stay safe for future episodes

For Sonarr, Arranger updates the series `path` and `rootFolderPath` through the Sonarr API with `moveFiles=true` only after verifying the current series object and root folders. That means Sonarr's own database points at the new series folder after a successful move, so future episodes import into the new path instead of the old path.

## Configuration

Copy the example config and edit it:

```bash
cp config/arranger.example.yaml config/arranger.yaml
```

The default example has:

```yaml
app:
  dry_run: true
```

Keep this enabled until audits show expected decisions.

### Getting API keys

- Radarr: **Settings → General → Security → API Key**
- Sonarr: **Settings → General → Security → API Key**

Set each URL to the hostname reachable from Arranger. In Docker this is often `http://radarr:7878` and `http://sonarr:8989` when containers share a Docker network.

### Rules

Rules are deterministic. Higher priority wins. If two rules match at the same priority, Arranger blocks the decision unless `rules.allow_first_equal_priority_match` is set true.

A rule can match:

- genres
- tags
- certifications/content ratings
- title regex
- monitored state
- path substrings
- exact custom fields from the Arr API payload

Genres are case-insensitive and support aliases such as `kids`/`children` and `animation`/`animated`. Anime is **not** treated as Kids unless your rules explicitly do so.

## Dry-run workflow

1. Start Arranger with `dry_run: true`.
2. Run an audit:

   ```bash
   curl -X POST http://localhost:8787/audit/all
   ```

3. View queue/history:

   ```bash
   curl http://localhost:8787/queue
   curl http://localhost:8787/history
   ```

Dry-run records use status `dry_run` and no move/update API call is made.

## Enabling real moves safely

1. Confirm every target root exists inside Radarr/Sonarr root folder settings.
2. Confirm your download/temp folders are not configured as media roots.
3. Review dry-run history and rule matches.
4. Set `app.dry_run: false`.
5. Optionally set `app.manual_approval: true` to require queue approval before execution.
6. Restart Arranger.
7. Run a small audit first (for example via webhook or one service audit).

Even when `dry_run` is false, Arranger still blocks real moves when safety checks or live API schema verification fail.

## Sonarr completion safety

`sonarr_move_safety.mode` supports:

- `series_complete_only`: only ended/complete series with all monitored episodes having files.
- `season_complete_only`: monitored episodes in the current season must have files.
- `all_available_episodes`: all currently aired monitored episodes must have files and queue/import must be empty. This is the default.

Recently imported episode files are blocked for `delay_after_last_import_minutes` to avoid racing imports and post-processing.

## Docker

Create the external Docker network used by your Arr apps if it does not exist:

```bash
docker network create arr-network
```

Copy and edit config:

```bash
cp config/arranger.example.yaml config/arranger.yaml
```

Start:

```bash
docker compose up -d --build
```

Open health:

```bash
curl http://localhost:8787/health
```

## Local development

Requires Python 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp config/arranger.example.yaml config/arranger.yaml
ARRANGER_CONFIG=config/arranger.yaml python -m arranger
```

Run tests and lint:

```bash
pytest
ruff check .
```

## HTTP API

- `GET /health` - startup self-check including DB, log file, and enabled Arr apps.
- `GET /status` - queue/history counts.
- `POST /audit/radarr` - audit Radarr items.
- `POST /audit/sonarr` - audit Sonarr items.
- `POST /audit/all` - audit both and process approved moves.
- `GET /queue` - pending/blocked/approved/running queue records.
- `GET /history` - all move records.
- `POST /queue/{id}/approve` - approve a queued record.
- `POST /queue/{id}/cancel` - cancel a queued record.
- `POST /webhook/radarr` - Radarr webhook entrypoint.
- `POST /webhook/sonarr` - Sonarr webhook entrypoint.

## Webhooks

Configure Radarr/Sonarr webhook URLs:

- Radarr: `http://arranger:8787/webhook/radarr`
- Sonarr: `http://arranger:8787/webhook/sonarr`

Webhook payloads vary by event and version. Arranger tries to extract the movie/series id. If it cannot, it logs the unknown payload and schedules a normal audit. Webhooks never bypass the dry-run, queue, or safety pipeline.

## API behavior verified at runtime

Arranger checks these endpoints at startup for enabled apps:

- `/api/v3/system/status`
- `/api/v3/rootfolder`
- `/api/v3/queue`

For moves, Arranger fetches the current item, validates required fields, validates the target root against live root folders, updates the item through `PUT /api/v3/movie/{id}` or `PUT /api/v3/series/{id}` with `moveFiles=true`, verifies the returned path, and then triggers a refresh command. If the live instance rejects the request or returns an unexpected schema, the move is marked failed.

## Troubleshooting

### Target root not found

Add the target folder to Radarr/Sonarr root folders first. Arranger refuses targets not returned by `/api/v3/rootfolder`.

### Queue active

Wait for downloads/imports to finish. Arranger blocks media with active queue/import records.

### Missing monitored episodes

For Sonarr, complete monitored available episodes or adjust the safety mode only if you understand the risk.

### API schema mismatch

Check Radarr/Sonarr version and API compatibility. Arranger intentionally refuses real moves when required fields or response shapes differ.

### Permission issues

Ensure Radarr/Sonarr can move files into the target root. Arranger asks Arr to move files; filesystem permissions must be correct for the Arr app containers/users.

### Wrong Docker network

The `docker-compose.yml` expects an external `arr-network`. Change it to match your Radarr/Sonarr network or create that network.

### Download folder accidentally configured as root folder

Do not use download/temp folders as library root folders. Arranger also checks `app.download_temp_paths` and blocks current paths under those directories.

## Current API assumptions to verify on your live instance

Radarr and Sonarr v3/v4 commonly use `/api/v3` endpoints and support `moveFiles=true` on item update. Arranger validates this against your running instance before recording success, but you should test with dry-run and a low-risk item before bulk real moves.
