
from flask import Flask, render_template, request, redirect, url_for, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, io, json, zipfile, urllib.request
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your-secret-key"

DB_NAME = "tracker.db"
VISUAL_BASELINE_ZIP_URL = "https://ecomcms-pr69-runner.onrender.com/visual-baselines.zip"
_visual_baseline_zip = None
_visual_baseline_manifest = None

def _load_visual_baselines():
    global _visual_baseline_zip, _visual_baseline_manifest
    if _visual_baseline_zip is None or _visual_baseline_manifest is None:
        req = urllib.request.Request(VISUAL_BASELINE_ZIP_URL, headers={"Cache-Control": "no-cache", "User-Agent": "EcomCMS-visual-review"})
        with urllib.request.urlopen(req, timeout=30) as response:
            archive_bytes = response.read()
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        manifest = json.loads(archive.read("visual-baselines-manifest.json").decode("utf-8"))
        files = manifest.get("files") or []
        if manifest.get("count") != 48 or len(files) != 48:
            raise RuntimeError("Unexpected visual baseline manifest")
        _visual_baseline_zip = archive
        _visual_baseline_manifest = manifest
    return _visual_baseline_zip, _visual_baseline_manifest

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS commenters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS members (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
                        id INTEGER PRIMARY KEY,
                        streamlabs_token TEXT,
                        tracking_enabled INTEGER DEFAULT 0)''')
        c.execute("INSERT OR IGNORE INTO settings (id, streamlabs_token, tracking_enabled) VALUES (1, '', 0)")
        c.execute("INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)",
                  ("admin", generate_password_hash("admin123")))
        conn.commit()

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            c.execute("SELECT password_hash FROM users WHERE username=?", (username,))
            user = c.fetchone()
            if user and check_password_hash(user[0], password):
                session["username"] = username
                return redirect(url_for("admin"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/admin")
def admin():
    if "username" not in session:
        return redirect(url_for("login"))
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT name, timestamp FROM commenters")
        commenters = c.fetchall()
        c.execute("SELECT name, timestamp FROM members")
        members = c.fetchall()
        c.execute("SELECT streamlabs_token, tracking_enabled FROM settings WHERE id=1")
        settings = c.fetchone()
    return render_template("dashboard.html", commenters=commenters, members=members, token=settings[0], tracking=bool(settings[1]))

@app.route("/update", methods=["POST"])
def update():
    if "username" not in session:
        return redirect(url_for("login"))
    token = request.form.get("token")
    tracking = 1 if request.form.get("tracking") == "on" else 0
    commenters = request.form.get("commenters", "").splitlines()
    members = request.form.get("members", "").splitlines()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("UPDATE settings SET streamlabs_token=?, tracking_enabled=? WHERE id=1", (token, tracking))
        c.execute("DELETE FROM commenters")
        for name in set(filter(None, commenters)):
            c.execute("INSERT INTO commenters (name) VALUES (?)", (name.strip(),))
        c.execute("DELETE FROM members")
        for name in set(filter(None, members)):
            c.execute("INSERT INTO members (name) VALUES (?)", (name.strip(),))
        conn.commit()

    with open("commenters.txt", "w") as cf:
        for name in commenters:
            cf.write(name.strip() + "\n")
    with open("members.txt", "w") as mf:
        for name in members:
            mf.write(name.strip() + "\n")

    return redirect(url_for("admin"))

@app.route("/reset_commenters", methods=["POST"])
def reset_commenters():
    if "username" not in session:
        return redirect(url_for("login"))
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM commenters")
        conn.commit()
    with open("commenters.txt", "w") as f:
        f.write("")
    return redirect(url_for("admin"))

@app.route("/raw/<list_type>")
def raw_list(list_type):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        if list_type == "commenters":
            c.execute("SELECT name FROM commenters")
        elif list_type == "members":
            c.execute("SELECT name FROM members")
        else:
            return "Invalid list type", 404
        names = sorted(set([row[0] for row in c.fetchall()]))
    return "\n".join(names), 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route("/files/<filename>")
def public_file(filename):
    if filename not in ["commenters.txt", "members.txt"]:
        return "File not allowed", 403
    return send_file(filename, mimetype='text/plain')

@app.route("/visual-review/<int:index>.png")
def visual_review(index):
    if index < 0 or index >= 48:
        return "Not found", 404
    try:
        archive, manifest = _load_visual_baselines()
        item = manifest["files"][index]
        path = item.get("path", "")
        if not path.startswith("tests/storefront-template-viewport.spec.ts-snapshots/") or not path.endswith(".png"):
            return "Not found", 404
        payload = archive.read(path)
        if len(payload) != item.get("bytes"):
            return "Invalid baseline", 502
        return Response(payload, 200, {
            "Content-Type": "image/png",
            "Content-Length": str(len(payload)),
            "Cache-Control": "no-store",
            "X-Baseline-Name": path.rsplit("/", 1)[-1],
        })
    except Exception:
        return "Visual review unavailable", 502

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080)
