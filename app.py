import os
import hmac
import sqlite3
import secrets
import uuid
from functools import wraps

from flask import (Flask, g, render_template, request, redirect, url_for,
                   session, send_from_directory, abort, flash)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "app.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", 200)) * 1024 * 1024

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


# ---------- Database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
            conn.executescript(f.read())


init_db()


# ---------- Helpers ----------
def human_size(n):
    n = float(n or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


app.jinja_env.filters["filesize"] = human_size


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.form.get("csrf", "")
        if not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Invalid CSRF token")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ---------- Public routes ----------
@app.route("/")
def index():
    files = get_db().execute(
        "SELECT id, title, description, file_size, downloads, created_at "
        "FROM files ORDER BY id DESC").fetchall()
    return render_template("index.html", files=files)


@app.route("/file/<int:file_id>")
def view_file(file_id):
    item = get_db().execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not item:
        abort(404)
    return render_template("view.html", f=item)


@app.route("/download/<int:file_id>")
def download(file_id):
    db = get_db()
    item = db.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not item:
        abort(404)
    db.execute("UPDATE files SET downloads = downloads + 1 WHERE id = ?", (file_id,))
    db.commit()
    return send_from_directory(UPLOAD_DIR, item["stored_name"],
                               as_attachment=True,
                               download_name=item["original_name"])


# ---------- Admin routes ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if (hmac.compare_digest(u, ADMIN_USERNAME)
                and hmac.compare_digest(p, ADMIN_PASSWORD)):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong username or password!")
    return render_template("admin/login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    files = get_db().execute("SELECT * FROM files ORDER BY id DESC").fetchall()
    return render_template("admin/dashboard.html", files=files)


@app.route("/admin/upload", methods=["POST"])
@login_required
def admin_upload():
    file = request.files.get("file")
    title = request.form.get("title", "").strip()
    if not file or not file.filename or not title:
        flash("Title and file are required.")
        return redirect(url_for("admin_dashboard"))

    ext = os.path.splitext(file.filename)[1].lower()
    stored = uuid.uuid4().hex + ext
    path = os.path.join(UPLOAD_DIR, stored)
    file.save(path)

    db = get_db()
    db.execute(
        "INSERT INTO files (title, description, original_name, stored_name, file_size, "
        "telegram_bot_token, telegram_chat_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, request.form.get("description", "").strip(), file.filename, stored,
         os.path.getsize(path), request.form.get("bot_token", "").strip(),
         request.form.get("chat_id", "").strip()))
    db.commit()
    flash("File uploaded successfully.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete/<int:file_id>", methods=["POST"])
@login_required
def admin_delete(file_id):
    db = get_db()
    item = db.execute("SELECT stored_name FROM files WHERE id = ?", (file_id,)).fetchone()
    if item:
        try:
            os.remove(os.path.join(UPLOAD_DIR, item["stored_name"]))
        except FileNotFoundError:
            pass
        db.execute("DELETE FROM files WHERE id = ?", (file_id,))
        db.commit()
        flash("File deleted.")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
