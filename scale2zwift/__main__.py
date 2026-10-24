"""Entry point: ``python -m scale2zwift``."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from waitress import serve

from .garmin import GarminAccount
from .store import Store
from .sync import Syncer
from .web import create_app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger("scale2zwift")

    store = Store(Path(os.environ.get("DATA_DIR", "/data")))
    garmin = GarminAccount(store.garmin_dir)
    syncer = Syncer(store, garmin)
    app = create_app(store, garmin, syncer)

    if not os.environ.get("UI_PASSWORD"):
        log.warning("UI_PASSWORD is not set: anyone who can reach the web UI can change the accounts")

    syncer.start()
    port = int(os.environ.get("PORT", "8080"))
    log.info("Listening on port %d", port)
    serve(app, host="0.0.0.0", port=port, threads=4)


if __name__ == "__main__":
    main()
