"""JobPilot Inbox: the hosted, phone-friendly view of the daily job feed.

Shows each run's leads with the job link, the tailored resume PDF and HR emails.
Protected by APP_PASSCODE. Runs on Render:  gunicorn cloud_app:app
Locally:  python cloud_app.py  ->  http://127.0.0.1:5070

Two ways in:
  - a browser / installed PWA logs in with the passcode and gets a session cookie;
  - the Android app (which runs from its own local origin) trades the passcode for a bearer token at /api/token.

Environment variables:
  MONGODB_URI       required, same database the daily feed writes to
  APP_PASSCODE      required, the passcode you type to open the inbox
  SECRET_KEY        recommended, any long random string (signs sessions, resume links and app tokens)
  TIMEZONE          optional, e.g. "Asia/Kolkata" (default UTC); used with KEEP_AWAKE_HOURS
  KEEP_AWAKE_HOURS  optional, e.g. "10-23": on Render's free plan, ping ourselves only in this window
  APK_URL           optional, where /app.apk redirects (default: the latest GitHub release, if APK_REPO is set)
  APK_REPO          optional, "owner/repo" whose latest release has JobPilot.apk
"""
import hmac
import os
import time
from collections import defaultdict
from datetime import timedelta

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_from_directory, session

from jobbot import config, leads
from jobbot.config import ROOT, env

from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

app = Flask(__name__, template_folder="templates", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # Render terminates HTTPS in front of us
app.config.update(
    SECRET_KEY=env("SECRET_KEY") or env("APP_PASSCODE") + "-jobpilot-session",
    PERMANENT_SESSION_LIFETIME=timedelta(days=180),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(env("RENDER")),
)
_fails = defaultdict(list)
PUBLIC = {"login", "token", "healthz", "ping", "manifest", "service_worker", "static", "apk"}
# Origins the Android app's WebView uses (Capacitor serves the bundled page from https://localhost).
APP_ORIGINS = {"https://localhost", "http://localhost", "capacitor://localhost"}


def _awake_hours():
    try:
        start, end = (int(x) for x in env("KEEP_AWAKE_HOURS").split("-"))
        return [start, end]
    except ValueError:
        return None


def _local_hour():
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(env("TIMEZONE") or "UTC")).hour
    except Exception:  # noqa: BLE001  (unknown zone name, or no tz database)
        return datetime.utcnow().hour


def _keep_awake():
    """Render's free plan sleeps after 15 idle minutes (30-60 s cold start), and its 750 free hours a month are
    shared by every free service on the account. We ping our own public URL every 10 minutes so the inbox stays
    fast. With KEEP_AWAKE_HOURS set (e.g. "10-23", in TIMEZONE) we only do it in that window and let Render
    sleep at night; the daily feed run wakes the service again. The phone app shows its saved copy instantly,
    so a sleeping server never blocks opening it."""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return
    window = _awake_hours()
    try:  # only one gunicorn worker runs the pinger
        import fcntl
        lock = open("/tmp/jobpilot-keepawake.lock", "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ImportError):
        return

    def loop():
        import requests
        while True:
            time.sleep(600)
            if window and not (window[0] <= _local_hour() < window[1]):
                continue  # night: let Render put us to sleep (this thread stops with it)
            try:
                requests.get(url.rstrip("/") + "/healthz", timeout=30)
            except Exception:  # noqa: BLE001
                pass

    import threading
    t = threading.Thread(target=loop, daemon=True, name="keep-awake")
    t._lock = lock  # keep the lock file open for the life of the process
    t.start()


_keep_awake()


def _sign(what):
    return hmac.new(app.config["SECRET_KEY"].encode(), what.encode(), "sha256").hexdigest()[:32]


def resume_token(lead_id):
    """Unguessable per-lead token so the PDF can open in a browser (outside the logged-in app)."""
    return _sign(f"resume:{lead_id}")


def notify_token():
    """Token the phone's background checker uses for /api/ping (it has no login)."""
    return _sign("notify")


def app_token():
    """Bearer token for the Android app. Changing APP_PASSCODE or SECRET_KEY signs every phone out."""
    return _sign(f"app:{env('APP_PASSCODE')}")


def _bearer_ok():
    h = request.headers.get("Authorization", "")
    return h.startswith("Bearer ") and bool(env("APP_PASSCODE")) and hmac.compare_digest(h[7:].strip(), app_token())


@app.before_request
def gate():
    if request.method == "OPTIONS":  # CORS preflight from the Android app
        return Response(status=204)
    if request.endpoint in PUBLIC or session.get("ok") or _bearer_ok():
        return None
    if request.endpoint == "resume" and hmac.compare_digest(
            request.args.get("t", ""), resume_token((request.view_args or {}).get("lead_id", ""))):
        return None
    if request.path.startswith("/api/") or request.path.startswith("/r/"):
        return jsonify({"error": "login required"}), 401
    return redirect("/login")


@app.after_request
def cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in APP_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Range"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "86400"
        resp.headers["Vary"] = "Origin"
    return resp


def _too_many(ip):
    _fails[ip] = [t for t in _fails[ip] if t > time.time() - 600]
    return len(_fails[ip]) >= 5


def _passcode_ok(given):
    return bool(env("APP_PASSCODE")) and hmac.compare_digest(given or "", env("APP_PASSCODE"))


def _ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        ip = _ip()
        if _too_many(ip):
            error = "Too many attempts. Try again in 10 minutes."
        elif _passcode_ok(request.form.get("passcode")):
            session.permanent = True
            session["ok"] = True
            return redirect("/")
        else:
            _fails[ip].append(time.time())
            error = "Wrong passcode."
    return render_template("mobile_login.html", error=error)


@app.post("/api/token")
def token():
    """Android app sign-in: passcode in, bearer token out."""
    ip = _ip()
    if _too_many(ip):
        return jsonify({"error": "Too many attempts. Try again in 10 minutes."}), 429
    if not _passcode_ok((request.get_json(silent=True) or {}).get("passcode")):
        _fails[ip].append(time.time())
        return jsonify({"error": "Wrong passcode."}), 401
    return jsonify({"token": app_token()})


@app.post("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.get("/")
def home():
    return render_template("mobile.html")


VIEWS = {"new": ["new"], "pc": ["starred", "queued"], "applied": ["applied"], "hidden": ["hidden"]}


@app.get("/api/leads")
def api_leads():
    view = request.args.get("view", "new")
    rows = leads.list_leads(VIEWS.get(view, ["new"]))
    for r in rows:  # the phone only needs links, resume and HR emails
        for k in ("alumni", "keywords", "dedupe_key", "external_id", "skills", "exp_min", "exp_max"):
            r.pop(k, None)
        if r.get("resume"):
            r["resume_url"] = request.host_url.rstrip("/") + f"/r/{r['id']}.pdf?t={resume_token(r['id'])}"
    last = leads.db().runs.find_one(sort=[("at", -1)])
    run = None
    if last:
        run = {"at": last["at"].strftime("%Y-%m-%dT%H:%M:%SZ"),  # the page shows it in the phone's own time zone
               "new_leads": last.get("new_leads", 0),
               "errors": [p for p, v in (last.get("portals") or {}).items() if v.get("errors")]}
    counts = {v: leads.db().leads.count_documents({"status": {"$in": s}}) for v, s in VIEWS.items()}
    try:
        first = config.candidate_name().split(" ")[0]
    except Exception:  # noqa: BLE001
        first = ""
    return jsonify({"leads": rows, "run": run, "counts": counts, "feed_enabled": leads.feed_enabled(),
                    "notify_token": notify_token(), "first_name": first, "awake_hours": _awake_hours()})


@app.get("/api/ping")
def ping():
    """Tiny status for the app's background notification check: when the last feed run was and how many it found."""
    if not hmac.compare_digest(request.args.get("t", ""), notify_token()):
        return jsonify({"error": "bad token"}), 401
    last = leads.db().runs.find_one(sort=[("at", -1)])
    return jsonify({"run_id": str(last["_id"]) if last else "", "new_leads": last.get("new_leads", 0) if last else 0,
                    "waiting": leads.db().leads.count_documents({"status": "new"})})


@app.post("/api/feed")
def api_feed():
    leads.set_feed_enabled((request.get_json(force=True) or {}).get("enabled", True))
    return jsonify({"ok": True, "feed_enabled": leads.feed_enabled()})


@app.post("/api/leads/<lead_id>")
def api_set(lead_id):
    status = (request.get_json(force=True) or {}).get("status")
    try:
        leads.set_status(lead_id, status)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if status == "applied":
        l = leads.get(lead_id)
        if l:
            leads.mark_applied_company(l["company"], l["title"])
    return jsonify({"ok": True})


@app.get("/r/<lead_id>.pdf")
def resume(lead_id):
    g = leads.get_resume(lead_id)
    if not g:
        abort(404)
    inline = request.args.get("dl") != "1"
    return Response(g.read(), mimetype="application/pdf", headers={
        "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{g.filename}"',
        "Cache-Control": "private, max-age=86400"})


@app.get("/manifest.webmanifest")
def manifest():
    return send_from_directory(os.path.join(ROOT, "static"), "manifest.webmanifest",
                               mimetype="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return send_from_directory(os.path.join(ROOT, "static"), "sw.js", mimetype="text/javascript")


@app.get("/app.apk")
def apk():
    """The Android app: a local static/JobPilot.apk if you put one there, else APK_URL / the latest GitHub release."""
    if os.path.exists(os.path.join(ROOT, "static", "JobPilot.apk")):
        return send_from_directory(os.path.join(ROOT, "static"), "JobPilot.apk", as_attachment=True,
                                   mimetype="application/vnd.android.package-archive")
    url = env("APK_URL") or (f"https://github.com/{env('APK_REPO')}/releases/latest/download/JobPilot.apk"
                             if env("APK_REPO") else "")
    if not url:
        abort(404)
    return redirect(url)


@app.get("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    # Local preview only (never on Render, which uses gunicorn): skip the passcode when asked.
    if os.environ.get("JOBPILOT_DEV_NOAUTH") == "1":
        app.before_request_funcs[None].insert(0, lambda: session.update(ok=True))
    app.run(host="127.0.0.1", port=5070, debug=False)
