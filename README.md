# scale2zwift

A lightweight Docker container with a simple web front-end that does one job: copy weigh-ins from a Garmin scale (via Garmin Connect) to your Zwift profile weight.

## How it works

- Every few hours (4 by default, configurable in the web UI) it fetches your most recent weigh-in from Garmin Connect.
- If that weigh-in hasn't been synced yet, it sets your Zwift profile weight to match, then reads your profile back to confirm the change took effect.
- A weight you change by hand in Zwift is left alone until your next weigh-in. **Sync now** pushes the latest weigh-in immediately.

## Running it

The image is published to GitHub Container Registry for `linux/amd64` and `linux/arm64` (e.g. Raspberry Pi, most NAS boxes).

```sh
curl -O https://raw.githubusercontent.com/AtomBrake/scale2zwift/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/AtomBrake/scale2zwift/main/.env.example
# edit .env and set UI_PASSWORD
docker compose up -d
```

Then open `http://<host>:8080`, connect Garmin and Zwift, and you're done.

Or with plain Docker:

```sh
docker run -d --name scale2zwift --restart unless-stopped \
  -p 8080:8080 -e UI_PASSWORD=change-me \
  -v scale2zwift-data:/data ghcr.io/atombrake/scale2zwift:latest
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `UI_PASSWORD` | *(none)* | Password for the web UI (HTTP basic auth). Strongly recommended. |
| `UI_USERNAME` | `admin` | Username for the web UI. |
| `PORT` | `8080` | Port the web UI listens on. |
| `LOG_LEVEL` | `INFO` | Python log level. |

Don't expose the web UI to the internet. Keep it on your home network or behind a VPN or a reverse proxy with its own authentication.

## What's stored, and where

Everything lives in the `/data` volume, readable only by the container user:

- `garmin/garmin_tokens.json`: Garmin login tokens. Your Garmin password is used once to log in (including MFA if enabled) and is **not** saved. If the tokens ever expire, reconnect Garmin in the UI.
- `secrets.json`: your Zwift email, password and tokens. The password is kept so the app can log back in by itself, since Zwift sessions expire.
- `state.json`: settings, the latest weigh-in and sync history.

**Disconnect** in the UI deletes the saved login for that account.

## Caveats

- Zwift has no public API. This uses the same endpoints as the Zwift website and companion app, which Zwift could change at any time. Because every update is read back, a change on Zwift's side shows up as an error in the history rather than a silent failure.
- Zwift doesn't allow weight changes while you're in an event or group ride. The update fails and is retried on the next scheduled run.
- Garmin access uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) library.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
DATA_DIR=./data PORT=8080 .venv/bin/python -m scale2zwift
```

CI runs a secret scan (gitleaks) and the tests on every push, then builds the multi-arch image and pushes it to `ghcr.io/atombrake/scale2zwift` from `main`.

## Security

This repository is public and must never contain private data or credentials.

- Garmin and Zwift credentials, login tokens and personal data (weights, profile info) are supplied at runtime only, via environment variables or a mounted data volume, and are never committed.
- `.env`, `secrets/` and `data/` are git-ignored. Commit an `.env.example` with placeholder values instead of a real `.env`.
- Test fixtures must use made-up data.

## License

[MIT](LICENSE)
