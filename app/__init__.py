import logging
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse

import click
from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from app import check, config, notify
from app.errors import UserError
from app.library import Library, TuneNotFound
from app.redirects import Redirects
from app.store import Store, make_s3


def create_app(library: Library | None = None) -> Flask:
    logging.basicConfig(level=logging.INFO)
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.SECRET_KEY,
        MAX_CONTENT_LENGTH=config.MAX_UPLOAD_BYTES,
        PERMANENT_SESSION_LIFETIME=timedelta(days=180),
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if library is None:
        library = Library(
            Store(
                make_s3(config.CF_ACCOUNT_ID, config.R2_ACCESS_KEY_ID, config.R2_SECRET_ACCESS_KEY),
                config.PRIVATE_BUCKET,
                config.AUDIO_BUCKET,
            ),
            Redirects(
                config.CF_ACCOUNT_ID, config.CF_LIST_ID, config.CF_API_TOKEN, config.AUDIO_HOST
            ),
            config.AUDIO_HOST,
            after_change=lambda tune_id, slug: check.check_later(
                f"https://{config.AUDIO_HOST}/{tune_id}", f"https://{config.AUDIO_HOST}/{slug}"
            ),
        )
    app.extensions["library"] = library

    @app.before_request
    def require_login():
        if request.endpoint in ("main.login", "static") or session.get("signed_in"):
            return None
        return redirect(url_for("main.login"))

    def back_link() -> str | None:
        referrer = request.referrer
        return referrer if referrer and urlparse(referrer).netloc == request.host else None

    @app.errorhandler(UserError)
    def user_error(e: UserError):
        return render_template("error.html", message=e.message, back=back_link()), 400

    @app.errorhandler(TuneNotFound)
    def unknown_tune(e: TuneNotFound):
        return render_template("error.html", message="That tune doesn't exist.", back=None), 404

    @app.errorhandler(413)
    def too_big(e: HTTPException):
        message = "That file is too big. Recordings and sheet music must be under 200 MB."
        return render_template("error.html", message=message, back=back_link()), 413

    @app.errorhandler(Exception)
    def unexpected(e: Exception):
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("request failed")
        notify.send("Tune uploader error", f"{request.method} {request.path}: {e!r}")
        message = "Something went wrong and nothing was saved. It's been reported."
        return render_template("error.html", message=message, back=back_link()), 500

    @app.cli.command("check-links")
    def check_links():
        tunes = library.list() + library.list(archived=True)
        problems = check.check_all(
            [(library.qr_url(t["id"]), f"https://{config.AUDIO_HOST}/{t['slug']}") for t in tunes]
        )
        if problems:
            notify.send("Tune QR links broken", "\n".join(problems))
            click.echo("\n".join(problems))
            sys.exit(1)
        click.echo(f"{len(tunes)} QR links OK")

    @app.template_filter("nicedate")
    def nicedate(value: str) -> str:
        return datetime.fromisoformat(value).strftime("%-d %b %Y")

    @app.context_processor
    def audio_host():
        return {"config_audio_host": config.AUDIO_HOST}

    from app.routes import bp

    app.register_blueprint(bp)
    return app
