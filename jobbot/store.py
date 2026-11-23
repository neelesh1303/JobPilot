"""Shared JSON-backed storage for tasks and settings (used by the web app and the CLI)."""
import csv
import io
import json
import os
import threading
import uuid
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TASKS_FILE = os.path.join(DATA, "tasks.json")
SETTINGS_FILE = os.path.join(DATA, "settings.json")
RESUME_DIR = os.path.join(DATA, "resume")
UPLOADS_DIR = os.path.join(DATA, "uploads")
OUTPUTS_DIR = os.path.join(DATA, "outputs")
EXCEL_FILE = os.path.join(DATA, "Applications.xlsx")

STATUSES = [
    "pending",            # waiting for Claude
    "in_progress",        # Claude is working on it
    "needs_input",        # Claude asked you something (OTP, CAPTCHA, missing answer)
    "awaiting_approval",  # form filled, waiting for your "yes" before submit
    "applied",            # submitted
    "drafted",            # outreach email drafted in Gmail
    "skipped",            # failed eligibility rules / duplicate
    "failed",
]

# Credentials are never stored in code. Set them in the UI (saved to data/settings.json,
# which is git-ignored) or via the JOBPILOT_EMAIL / JOBPILOT_PASSWORD environment variables.
DEFAULT_SETTINGS = {
    "account_email": os.getenv("JOBPILOT_EMAIL", ""),
    "account_password": os.getenv("JOBPILOT_PASSWORD", ""),
    "resume_uploaded_at": None,
    "resume_needs_sync": False,
}

_lock = threading.Lock()


def _ensure_dirs():
    for d in (DATA, RESUME_DIR, UPLOADS_DIR, OUTPUTS_DIR):
        os.makedirs(d, exist_ok=True)


def _read(path, default):
    _ensure_dirs()
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(path, obj):
    _ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    if path == TASKS_FILE:
        sync_excel(obj)


def sync_excel(tasks=None):
    """Rebuild data/Applications.xlsx. Never breaks a queue update; a locked file is retried next time."""
    try:
        from jobbot import excel
        if tasks is None:
            tasks = _read(TASKS_FILE, [])
        return excel.save(tasks, DATA, EXCEL_FILE)
    except Exception as e:  # noqa: BLE001
        print(f"[jobbot] Excel tracker not updated: {e}")
        return False


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------- settings ----------
def get_settings():
    with _lock:
        s = dict(DEFAULT_SETTINGS)
        s.update(_read(SETTINGS_FILE, {}))
        return s


def update_settings(**changes):
    with _lock:
        s = dict(DEFAULT_SETTINGS)
        s.update(_read(SETTINGS_FILE, {}))
        s.update(changes)
        _write(SETTINGS_FILE, s)
        return s


# ---------- tasks ----------
def list_tasks(status=None):
    with _lock:
        tasks = _read(TASKS_FILE, [])
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return tasks


def get_task(task_id):
    for t in list_tasks():
        if t["id"] == task_id:
            return t
    return None


def add_task(kind, url=None, screenshot=None, note="", **extra):
    with _lock:
        tasks = _read(TASKS_FILE, [])
        if kind == "job" and url:
            for t in tasks:
                if t.get("url") == url and t["status"] not in ("failed",):
                    return t, False
        task = {
            "id": uuid.uuid4().hex[:8],
            "type": kind,                 # "job" | "outreach"
            "url": url,
            "screenshot": screenshot,     # path relative to data/
            "note": note,
            "status": "pending",
            "company": "",
            "role": "",
            "portal": "",
            "contact_email": "",
            "reason": "",                 # skip/fail reason or what Claude needs from you
            "questions_asked": [],
            "outputs": {},                # name -> path relative to data/
            "history": [{"at": now(), "msg": "created"}],
            "created": now(),
            "updated": now(),
        }
        task.update({k: v for k, v in extra.items() if v not in (None, "")})  # e.g. lead_id, company, role, portal
        tasks.insert(0, task)
        _write(TASKS_FILE, tasks)
        os.makedirs(os.path.join(OUTPUTS_DIR, task["id"]), exist_ok=True)
        return task, True


def update_task(task_id, history_msg=None, **fields):
    with _lock:
        tasks = _read(TASKS_FILE, [])
        for t in tasks:
            if t["id"] == task_id:
                if "status" in fields and fields["status"] not in STATUSES:
                    raise ValueError(f"bad status {fields['status']!r}; use one of {STATUSES}")
                if "question" in fields:
                    t["questions_asked"].append(fields.pop("question"))
                if "outputs" in fields:
                    t["outputs"].update(fields.pop("outputs"))
                t.update(fields)
                t["updated"] = now()
                if fields.get("status") == "applied" and not t.get("applied_at"):
                    t["applied_at"] = now()
                if history_msg or "status" in fields:
                    t["history"].append({"at": now(), "msg": history_msg or f"status -> {fields['status']}"})
                _write(TASKS_FILE, tasks)
                _sync_lead(t, fields.get("status"))
                return t
    raise KeyError(task_id)


def _sync_lead(task, status):
    """Mirror an applied/skipped task back to the shared lead feed (best effort; works offline too)."""
    if status not in ("applied", "skipped") or task.get("type") != "job":
        return
    try:
        from jobbot import leads
        if status == "applied":
            leads.mark_applied_company(task.get("company"), task.get("role"))
        if task.get("lead_id"):
            leads.set_status(task["lead_id"], "applied" if status == "applied" else "hidden",
                             skip_reason=task.get("reason", "") if status == "skipped" else "")
    except Exception as e:  # noqa: BLE001
        print(f"[jobbot] lead feed not updated: {e}")


def delete_task(task_id):
    with _lock:
        tasks = [t for t in _read(TASKS_FILE, []) if t["id"] != task_id]
        _write(TASKS_FILE, tasks)


def log_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "type", "company", "role", "portal", "status", "url_or_contact", "reason", "questions_asked"])
    for t in reversed(list_tasks()):
        w.writerow([t["created"], t["type"], t["company"], t["role"], t["portal"], t["status"],
                    t.get("url") or t.get("contact_email", ""), t["reason"], " | ".join(t["questions_asked"])])
    return buf.getvalue()
