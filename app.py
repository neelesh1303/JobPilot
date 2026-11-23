"""JobPilot – local UI for queueing job links and recruiter screenshots.

Run:  python app.py   ->  http://127.0.0.1:5050
Claude Code does the actual work via the /process-queue command.
"""
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime

from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from jobbot import store

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def open_terminal(cmd):
    """Run cmd (a list) in a new terminal window in the project folder. Returns False if no terminal was found."""
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/k", *cmd], cwd=store.ROOT, creationflags=subprocess.CREATE_NEW_CONSOLE)
        return True
    line = f"cd {shlex.quote(store.ROOT)} && {shlex.join(cmd)}"
    if sys.platform == "darwin":
        script = 'tell application "Terminal" to do script ' + '"' + line.replace("\\", "\\\\").replace('"', '\\"') + '"'
        subprocess.Popen(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'])
        return True
    for term, args in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
                       ("xfce4-terminal", ["-x"]), ("xterm", ["-e"])):
        if shutil.which(term):
            subprocess.Popen([term, *args, "bash", "-c", line + "; exec bash"])
            return True
    return False


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def state():
    s = store.get_settings()
    resume = os.path.join(store.RESUME_DIR, "base_resume.pdf")
    return jsonify({
        "settings": {"account_email": s["account_email"], "account_password": s["account_password"]},
        "resume": {"uploaded": os.path.exists(resume), "uploaded_at": s["resume_uploaded_at"],
                   "needs_sync": s["resume_needs_sync"]},
        "tasks": store.list_tasks(),
    })


@app.post("/api/settings")
def save_settings():
    body = request.get_json(force=True)
    email = (body.get("account_email") or "").strip()
    password = body.get("account_password") or ""
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    store.update_settings(account_email=email, account_password=password)
    return jsonify({"ok": True})


@app.post("/api/resume")
def upload_resume():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Upload a PDF"}), 400
    f.save(os.path.join(store.RESUME_DIR, "base_resume.pdf"))
    store.update_settings(resume_uploaded_at=store.now(), resume_needs_sync=True)
    return jsonify({"ok": True})


@app.post("/api/jobs")
def add_jobs():
    text = (request.get_json(force=True).get("urls") or "")
    urls = [u.strip() for u in text.split() if u.strip().lower().startswith(("http://", "https://"))]
    if not urls:
        return jsonify({"error": "Paste at least one link starting with http(s)://"}), 400
    added, dupes = 0, 0
    for u in urls:
        _, created = store.add_task("job", url=u)
        added += created
        dupes += not created
    return jsonify({"added": added, "duplicates": dupes})


@app.post("/api/outreach")
def add_outreach():
    f = request.files.get("file")
    note = request.form.get("note", "").strip()
    if not f:
        return jsonify({"error": "Attach a screenshot"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in IMAGE_EXT:
        return jsonify({"error": "Screenshot must be an image"}), 400
    name = datetime.now().strftime("%Y%m%d-%H%M%S-") + secure_filename(f.filename)
    f.save(os.path.join(store.UPLOADS_DIR, name))
    task, _ = store.add_task("outreach", screenshot=f"uploads/{name}", note=note)
    return jsonify({"ok": True, "id": task["id"]})


@app.post("/api/tasks/<task_id>")
def edit_task(task_id):
    body = request.get_json(force=True)
    try:
        t = store.update_task(task_id, history_msg="changed from UI", **{k: v for k, v in body.items() if k in ("status", "reason")})
    except (KeyError, ValueError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(t)


@app.delete("/api/tasks/<task_id>")
def remove_task(task_id):
    store.delete_task(task_id)
    return jsonify({"ok": True})


@app.get("/api/log.csv")
def log_csv():
    return Response(store.log_csv(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=applications_log.csv"})


@app.get("/api/log.xlsx")
def log_xlsx():
    store.sync_excel()
    if not os.path.exists(store.EXCEL_FILE):
        abort(404)
    return send_from_directory(store.DATA, "Applications.xlsx", as_attachment=True,
                               download_name="Applications.xlsx", max_age=0)


@app.post("/api/run")
def run_claude():
    """Open a new terminal running Claude Code (with Chrome) on the queue."""
    if (request.get_json(silent=True) or {}).get("only_if_pending") and not store.list_tasks("pending"):
        return jsonify({"ok": True, "skipped": "nothing pending"})
    if not open_terminal(["claude", "--chrome", "/process-queue"]):
        return jsonify({"error": "No terminal found. Run `claude --chrome \"/process-queue\"` in this folder"}), 400
    return jsonify({"ok": True})


# ---------- Inbox: daily job feed (shared with the phone app via MongoDB) ----------
LEAD_VIEWS = {"new": ["new"], "pc": ["starred"], "queued": ["queued"], "applied": ["applied"], "hidden": ["hidden"]}


def _leads():
    from jobbot import leads
    return leads


@app.get("/api/leads")
def api_leads():
    try:
        L = _leads()
        rows = L.list_leads(LEAD_VIEWS.get(request.args.get("view", "new"), ["new"]))
        counts = {v: L.db().leads.count_documents({"status": {"$in": s}}) for v, s in LEAD_VIEWS.items()}
        last = L.db().runs.find_one(sort=[("at", -1)])
        run = {"at": last["at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "new_leads": last.get("new_leads", 0),
               "errors": {p: v["errors"] for p, v in (last.get("portals") or {}).items() if v.get("errors")}} if last else None
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Job feed unavailable: {e}"}), 503
    return jsonify({"leads": rows, "counts": counts, "run": run, "feed_enabled": L.feed_enabled()})


@app.post("/api/leads/<lead_id>")
def api_lead_status(lead_id):
    try:
        _leads().set_status(lead_id, (request.get_json(force=True) or {}).get("status"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True})


def _queue_lead(lead_id):
    L = _leads()
    lead = L.get(lead_id)
    if not lead:
        raise KeyError(lead_id)
    task, created = store.add_task("job", url=lead["url"], lead_id=lead_id, company=lead["company"],
                                   role=lead["title"], portal=lead["source"],
                                   note=f"From job feed (fit {lead.get('fit')}%, lead project: {lead.get('best_project')})")
    g = L.get_resume(lead_id)
    if g and created:  # pre-tailored resume as a starting point; Claude still checks it against the JD
        out = os.path.join(store.OUTPUTS_DIR, task["id"])
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, g.filename), "wb") as f:
            f.write(g.read())
        store.update_task(task["id"], outputs={"feed_resume": f"outputs/{task['id']}/{g.filename}"})
    L.set_status(lead_id, "queued", task_id=task["id"])
    return task, created


@app.post("/api/leads/<lead_id>/apply")
def api_lead_apply(lead_id):
    try:
        task, created = _queue_lead(lead_id)
    except KeyError:
        return jsonify({"error": "lead not found"}), 404
    return jsonify({"ok": True, "task": task["id"], "created": created})


@app.post("/api/leads/apply-all")
def api_leads_apply_all():
    """Queue every job starred from the phone."""
    ids = [l["id"] for l in _leads().list_leads(["starred"])]
    for i in ids:
        _queue_lead(i)
    return jsonify({"ok": True, "queued": len(ids)})


@app.get("/r/<lead_id>.pdf")
def lead_resume(lead_id):
    g = _leads().get_resume(lead_id)
    if not g:
        abort(404)
    return Response(g.read(), mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{g.filename}"'})


@app.post("/api/discover")
def api_discover():
    """Run the job feed now, in a new terminal window."""
    cmd = [sys.executable, os.path.join(store.ROOT, "scripts", "discover.py")]
    if not open_terminal(cmd):
        subprocess.Popen(cmd, cwd=store.ROOT)
    return jsonify({"ok": True})


@app.get("/files/<path:rel>")
def files(rel):
    full = os.path.abspath(os.path.join(store.DATA, rel))
    if not full.startswith(os.path.abspath(store.DATA)) or not os.path.isfile(full):
        abort(404)
    return send_from_directory(store.DATA, rel)


if __name__ == "__main__":
    store.get_settings()  # ensure data dirs exist
    if not os.path.exists(store.SETTINGS_FILE):
        store.update_settings()
    print("JobPilot running at http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, debug=False)
