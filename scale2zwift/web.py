"""The web front-end."""
from __future__ import annotations

import hmac
import logging
import os
import secrets
from datetime import datetime
from urllib.parse import urlsplit

from flask import Flask, Response, flash, redirect, render_template, request, url_for
from markupsafe import Markup

from .garmin import GarminAccount
from .store import Store
from .sync import Syncer
from .zwift import ZwiftAuthError, ZwiftError

log = logging.getLogger(__name__)


def create_app(store: Store, garmin: GarminAccount, syncer: Syncer) -> Flask:
    app = Flask(__name__)
    app.secret_key = secrets.token_bytes(32)
    ui_user = os.environ.get("UI_USERNAME", "admin")
    ui_password = os.environ.get("UI_PASSWORD", "")

    @app.template_filter("weight")
    def weight(grams: int | None) -> str:
        if grams is None:
            return "–"
        return f"{grams / 1000:.1f} kg ({grams / 453.59237:.1f} lb)"

    @app.template_filter("when")
    def when(iso: str | None) -> Markup:
        if not iso:
            return Markup("")
        dt = datetime.fromisoformat(iso)
        return Markup('<time datetime="{}">{} UTC</time>').format(dt.isoformat(), f"{dt:%Y-%m-%d %H:%M}")

    @app.before_request
    def protect():
        if request.endpoint == "healthz":
            return None
        if ui_password:
            auth = request.authorization
            if not (
                auth
                and hmac.compare_digest(auth.username or "", ui_user)
                and hmac.compare_digest(auth.password or "", ui_password)
            ):
                return Response(
                    "Login required", 401, {"WWW-Authenticate": 'Basic realm="scale2zwift"'}
                )
        if request.method == "POST":
            # Reject form posts made by other websites.
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site" or (
                origin and urlsplit(origin).netloc != request.host
            ):
                return Response("Cross-site request blocked", 403)
        return None

    @app.get("/")
    def index():
        state = store.state.load()
        zwift_email = store.secrets.load().get("zwift_email")
        return render_template(
            "index.html",
            garmin_connected=garmin.connected,
            garmin_email=state.get("garmin_email"),
            mfa_pending=garmin.mfa_pending,
            zwift_email=zwift_email,
            latest=state.get("latest_weigh_in"),
            last_run=state.get("last_run"),
            history=state.get("history", []),
            interval_hours=syncer.interval_hours,
            next_run=syncer.next_run().isoformat() if garmin.connected and zwift_email else None,
        )

    @app.post("/garmin/login")
    def garmin_login():
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        try:
            needs_mfa = garmin.login(email, password)
        except Exception as exc:
            log.warning("Garmin login failed: %s", exc)
            flash(f"Garmin login failed: {exc}", "error")
            return redirect(url_for("index"))
        store.state.update(garmin_email=email)
        if needs_mfa:
            flash("Enter the code Garmin just sent you.", "info")
        else:
            flash("Garmin connected.", "ok")
            syncer.run_soon()
        return redirect(url_for("index"))

    @app.post("/garmin/mfa")
    def garmin_mfa():
        try:
            garmin.submit_mfa(request.form.get("code", "").strip())
        except Exception as exc:
            flash(f"Garmin code was not accepted: {exc}", "error")
            return redirect(url_for("index"))
        flash("Garmin connected.", "ok")
        syncer.run_soon()
        return redirect(url_for("index"))

    @app.post("/garmin/disconnect")
    def garmin_disconnect():
        garmin.disconnect()
        store.state.update(garmin_email=None, latest_weigh_in=None)
        flash("Garmin disconnected and its saved login removed.", "ok")
        return redirect(url_for("index"))

    @app.post("/zwift/login")
    def zwift_login():
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        client = syncer.zwift_factory(email, password)
        try:
            client.login()
            client.get_profile()
        except ZwiftAuthError:
            flash("Zwift rejected that email or password.", "error")
            return redirect(url_for("index"))
        except (ZwiftError, OSError) as exc:
            flash(f"Could not connect to Zwift: {exc}", "error")
            return redirect(url_for("index"))
        store.secrets.save(
            {"zwift_email": email, "zwift_password": password, "zwift_tokens": client.tokens}
        )
        flash("Zwift connected.", "ok")
        syncer.run_soon()
        return redirect(url_for("index"))

    @app.post("/zwift/disconnect")
    def zwift_disconnect():
        store.secrets.save({})
        flash("Zwift disconnected and its saved login removed.", "ok")
        return redirect(url_for("index"))

    @app.post("/settings")
    def settings():
        try:
            hours = float(request.form.get("interval_hours", ""))
        except ValueError:
            hours = 0
        if not 0.25 <= hours <= 168:
            flash("Sync interval must be between 0.25 and 168 hours.", "error")
        else:
            syncer.set_interval_hours(hours)
            flash(f"Syncing every {hours:g} hours.", "ok")
        return redirect(url_for("index"))

    @app.post("/sync")
    def sync_now():
        event = syncer.run(force=True)
        flash(event["message"], "error" if event["status"] == "error" else "ok")
        return redirect(url_for("index"))

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app
