"""Leads (discovered jobs) in MongoDB Atlas, shared by the desktop app, the hosted app and the daily feed.

Lead statuses:
  new      found by the feed, not acted on
  starred  sent to the PC from the phone ("apply from PC")
  queued   turned into a desktop JobPilot task (Claude will apply)
  applied  application submitted
  hidden   dismissed
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from jobbot.config import env

STATUSES = ["new", "starred", "queued", "applied", "hidden"]
_db = None


def db():
    global _db
    if _db is None:
        from pymongo import MongoClient
        uri = env("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _db = MongoClient(uri, serverSelectionTimeoutMS=10000, tz_aware=True).get_default_database(default="jobpilot")
        _db.leads.create_index("status")
        _db.leads.create_index("found_at")
        _db.leads.create_index("dedupe_key")
    return _db


def fs():
    import gridfs
    return gridfs.GridFS(db(), collection="resumes")


def utcnow():
    return datetime.now(timezone.utc)


def lead_id(job):
    return hashlib.sha1(f"{job['source']}|{job['external_id']}".encode()).hexdigest()[:12]


def dedupe_key(job):
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()  # noqa: E731
    return f"{norm(job['company'])}|{norm(job['title'])}"


def known_ids(ids):
    return {d["_id"] for d in db().leads.find({"_id": {"$in": list(ids)}}, {"_id": 1})}


def known_dedupe_keys(keys):
    return {d["dedupe_key"] for d in db().leads.find({"dedupe_key": {"$in": list(keys)}}, {"dedupe_key": 1})}


def save(lead):
    db().leads.replace_one({"_id": lead["_id"]}, lead, upsert=True)


def save_skipped(ids):
    """Remember rejected jobs (id only) so tomorrow's run doesn't pay to score them again."""
    from pymongo import UpdateOne
    if ids:
        db().seen.bulk_write([UpdateOne({"_id": i}, {"$setOnInsert": {"at": utcnow()}}, upsert=True) for i in ids])


def seen_ids(ids):
    return {d["_id"] for d in db().seen.find({"_id": {"$in": list(ids)}}, {"_id": 1})}


def put_resume(lead_id_, pdf_path, filename):
    f = fs()
    for old in f.find({"lead_id": lead_id_}):
        f.delete(old._id)
    with open(pdf_path, "rb") as fh:
        return f.put(fh, filename=filename, lead_id=lead_id_, contentType="application/pdf")


def get_resume(lead_id_):
    return fs().find_one({"lead_id": lead_id_})


def list_leads(statuses=None, limit=200):
    q = {"status": {"$in": statuses}} if statuses else {}
    rows = list(db().leads.find(q, {"description": 0}).sort([("found_at", -1), ("fit", -1)]).limit(limit))
    for r in rows:
        r["id"] = r.pop("_id")
        for k in ("found_at", "updated_at"):
            if isinstance(r.get(k), datetime):
                r[k] = r[k].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # shown in the viewer's local time
    return rows


def get(lead_id_):
    return db().leads.find_one({"_id": lead_id_})


def set_status(lead_id_, status, **extra):
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}")
    db().leads.update_one({"_id": lead_id_}, {"$set": {"status": status, "updated_at": utcnow(), **extra}})


def feed_enabled():
    """The daily feed runs until it's paused from the phone app."""
    d = db().settings.find_one({"_id": "feed"})
    return True if d is None else bool(d.get("enabled", True))


def set_feed_enabled(enabled):
    db().settings.update_one({"_id": "feed"}, {"$set": {"enabled": bool(enabled), "changed_at": utcnow()}}, upsert=True)


def applied_companies():
    return {d["_id"] for d in db().applied.find({}, {"_id": 1})}


def mark_applied_company(company, role=""):
    if company:
        db().applied.update_one({"_id": company.strip().lower()}, {"$set": {"role": role, "at": utcnow()}}, upsert=True)


def prune(days):
    """Delete old leads nobody acted on, and their resume PDFs."""
    cutoff = utcnow() - timedelta(days=days)
    old = [d["_id"] for d in db().leads.find({"found_at": {"$lt": cutoff}, "status": {"$in": ["new", "hidden"]}}, {"_id": 1})]
    f = fs()
    for i in old:
        for g in f.find({"lead_id": i}):
            f.delete(g._id)
    db().leads.delete_many({"_id": {"$in": old}})
    db().seen.delete_many({"at": {"$lt": cutoff}})
    return len(old)
