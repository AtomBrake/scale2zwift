# scale2zwift

A lightweight Docker container with a simple web front-end that does one job: sync weight measurements from a Garmin scale (via Garmin Connect) to a Zwift account.

## Status

Work in progress.

## Security

This repository is public and must never contain private data or credentials.

- Garmin and Zwift credentials, login tokens and personal data (weights, profile info) are supplied at runtime only, via environment variables or a mounted data volume, and are never committed.
- `.env`, `secrets/` and `data/` are git-ignored. Commit an `.env.example` with placeholder values instead of a real `.env`.
- Test fixtures must use made-up data.
