import io
import time
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from app import config

bp = Blueprint("main", __name__)


def _library():
    return current_app.extensions["library"]


def _suffix(upload) -> str:
    return Path(upload.filename or "").suffix.lower() or ".bin"


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password_hash(config.PASSWORD_HASH, request.form.get("password", "")):
            session.permanent = True
            session["signed_in"] = True
            return redirect(url_for("main.tunes"))
        time.sleep(2)  # slows password guessing; there is only one account
        return render_template("login.html", wrong=True), 401
    return render_template("login.html", wrong=False)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.get("/")
def tunes():
    q = request.args.get("q", "").strip()
    found = [t for t in _library().list() if q.lower() in t["title"].lower()]
    return render_template("tunes.html", tunes=found, q=q, archived=False)


@bp.get("/archived")
def archived():
    return render_template("tunes.html", tunes=_library().list(archived=True), q="", archived=True)


@bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        return render_template("add.html")
    recording = request.files["recording"]
    tune_id = _library().add(
        request.form.get("title", ""),
        request.files["sheet"].read(),
        recording.read(),
        _suffix(recording),
    )
    return redirect(url_for("main.tune", tune_id=tune_id))


@bp.get("/tune/<tune_id>")
def tune(tune_id: str):
    library = _library()
    t = library.get(tune_id)
    return render_template(
        "tune.html",
        tune=t,
        qr_url=library.qr_url(tune_id),
        vanity_url=f"https://{config.AUDIO_HOST}/{t['slug']}",
    )


@bp.post("/tune/<tune_id>/rename")
def rename(tune_id: str):
    _library().rename(tune_id, request.form.get("title", ""))
    return redirect(url_for("main.tune", tune_id=tune_id))


@bp.post("/tune/<tune_id>/recording")
def replace_recording(tune_id: str):
    recording = request.files["recording"]
    _library().replace_audio(tune_id, recording.read(), _suffix(recording))
    return redirect(url_for("main.tune", tune_id=tune_id))


@bp.post("/tune/<tune_id>/sheet")
def replace_sheet(tune_id: str):
    _library().replace_sheet(tune_id, request.files["sheet"].read())
    return redirect(url_for("main.tune", tune_id=tune_id))


@bp.post("/tune/<tune_id>/archive")
def archive(tune_id: str):
    _library().set_archived(tune_id, True)
    return redirect(url_for("main.tunes"))


@bp.post("/tune/<tune_id>/restore")
def restore(tune_id: str):
    _library().set_archived(tune_id, False)
    return redirect(url_for("main.tune", tune_id=tune_id))


@bp.get("/tune/<tune_id>/sheet.pdf")
def sheet_pdf(tune_id: str):
    return _pdf(tune_id, with_qr=False)


@bp.get("/tune/<tune_id>/sheet-qr.pdf")
def sheet_qr_pdf(tune_id: str):
    return _pdf(tune_id, with_qr=True)


def _pdf(tune_id: str, with_qr: bool):
    library = _library()
    title = library.get(tune_id)["title"]
    return send_file(
        io.BytesIO(library.pdf(tune_id, with_qr)),
        mimetype="application/pdf",
        download_name=f"{title} (QR).pdf" if with_qr else f"{title}.pdf",
        as_attachment=False,
    )
