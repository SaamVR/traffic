from flask import Flask, request, send_file, render_template, redirect, url_for, jsonify
import threading
import time
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret'

# --- Config ---
ADMIN_PASSWORD = "admin123"
STREAMLABS_TOKEN = ""
tracking_enabled = False

# --- In-memory data ---
commenters = []
members = []
timestamps = {}

def save_lists():
    with open("commenters.txt", "w") as f:
        for name in sorted(set(commenters)):
            f.write(name + "\n")
    with open("members.txt", "w") as f:
        for name in sorted(set(members)):
            f.write(name + "\n")

def mock_streamlabs_listener():
    while True:
        if tracking_enabled:
            commenters.append("viewer_" + str(int(time.time()) % 100))
            members.append("member_" + str(int(time.time()) % 50))
            save_lists()
        time.sleep(10)

threading.Thread(target=mock_streamlabs_listener, daemon=True).start()

@app.route("/")
def home():
    return redirect("/admin")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") != ADMIN_PASSWORD:
            return render_template("admin.html", error="Wrong password.")
        return render_template("dashboard.html",
            token=STREAMLABS_TOKEN,
            commenters=sorted(set(commenters)),
            members=sorted(set(members)),
            tracking=tracking_enabled
        )
    return render_template("admin.html")

@app.route("/update", methods=["POST"])
def update_data():
    global STREAMLABS_TOKEN, tracking_enabled, commenters, members
    if request.form.get("admin_key") != ADMIN_PASSWORD:
        return "Unauthorized", 403

    STREAMLABS_TOKEN = request.form.get("token", "")
    tracking_enabled = request.form.get("tracking") == "on"
    commenters = list(filter(None, request.form.get("commenters", "").split("\n")))
    members = list(filter(None, request.form.get("members", "").split("\n")))

    save_lists()
    return redirect("/admin")

@app.route("/reset_commenters", methods=["POST"])
def reset_commenters():
    global commenters
    if request.form.get("admin_key") != ADMIN_PASSWORD:
        return "Unauthorized", 403
    commenters = []
    open("commenters.txt", "w").close()
    return redirect("/admin")

@app.route("/raw/<list_type>")
def raw_list(list_type):
    if list_type == "commenters":
        return send_file("commenters.txt", mimetype='text/plain')
    elif list_type == "members":
        return send_file("members.txt", mimetype='text/plain')
    return "Invalid list type", 404

if __name__ == "__main__":
    if not os.path.exists("commenters.txt"):
        open("commenters.txt", "w").close()
    if not os.path.exists("members.txt"):
        open("members.txt", "w").close()
    app.run(host="0.0.0.0", port=8080)
