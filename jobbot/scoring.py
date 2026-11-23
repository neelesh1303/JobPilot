"""Eligibility filters and fit scoring.

1. prefilter(): cheap rules (title seniority, stated experience, location) with no API calls.
2. score(): Gemini reads each JD against your profile (CLAUDE.md + master_resume.json) and returns a fit score,
   matched/missing skills, best project and hard-rule checks (paid, experience, graduation year, location).

Who you are and what you're looking for comes from the "candidate" block in profile/search.json.
"""
import json
import os
import re
import time

import requests

from jobbot import config
from jobbot.config import ROOT, env


def _master():
    return config.master_resume()


def projects():
    return [p["key"] for p in _master()["projects"] + _master().get("extra_projects", [])]


def gemini(prompt, schema=None, temperature=0.2, rounds=2):
    """Call Gemini, falling back through GEMINI_MODELS when a model is overloaded or rate-limited."""
    key = env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    models = [m.strip() for m in env("GEMINI_MODELS", "gemini-3.5-flash,gemini-2.5-flash,gemini-3.5-flash-lite").split(",")]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}}
    if schema:
        body["generationConfig"]["responseSchema"] = schema
    last = None
    for rnd in range(rounds):
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                r = requests.post(url, params={"key": key}, json=body, timeout=90)
            except requests.RequestException as e:
                last = f"{model}: {e.__class__.__name__}"
                continue
            if r.status_code in (404, 429, 500, 502, 503, 504):
                last = f"{model}: {r.status_code}"
                continue
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            return json.loads("".join(p.get("text", "") for p in parts))
        time.sleep(20 * (rnd + 1))
    raise RuntimeError(f"Gemini unavailable ({last})")


def profile_text():
    """Education + skills sections of CLAUDE.md, plus every project in the master resume: the only facts the scorer may use."""
    with open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8") as f:
        md = f.read()
    m = re.search(r"## 2\. EDUCATION.*?(?=## 4\.)", md, re.S)
    head = m.group(0) if m else md[:6000]
    # Projects come from the master resume, so every project you add there is considered.
    projs = "\n".join(
        f"- [{p['key']}] {re.sub(r'<.*?>', '', p['name'])} ({p['stack']}): "
        + " ".join(re.sub(r"<.*?>", "", b) for b in p["bullets"])
        for p in _master()["projects"] + _master().get("extra_projects", []))
    return head + "\n## PROJECTS (key in brackets)\n" + projs


def _words(s):
    return re.findall(r"[a-z0-9.+#]+", (s or "").lower())


def prefilter(job, cfg):
    """Return a skip reason, or None if the job should be scored."""
    title = (job.get("title") or "").lower()
    padded = " " + " ".join(_words(title)) + " "
    for bad in cfg["title_exclude"]:
        if f" {bad} " in padded:
            return f"title says '{bad}'"
    for bad, allowed in cfg.get("title_exclude_unless", {}).items():
        if f" {bad} " in padded and not any(a in title for a in allowed):
            return f"title says '{bad}'"
    if job.get("exp_min") is not None and job["exp_min"] > cfg["max_experience_years"]:
        return f"needs {job['exp_min']:g}+ years"
    loc = (job.get("location") or "").lower()
    allowed = [a.lower() for a in cfg.get("allowed_locations") or []]
    if loc and allowed and not job.get("remote") and not any(a in loc for a in allowed):
        return "location not in allowed_locations and not remote"
    if (cfg.get("candidate") or {}).get("paid_only", True) and re.search(r"\bunpaid\b", (job.get("description") or "").lower()):
        return "unpaid"
    return None


def score_schema():
    keys = projects()
    return {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "i": {"type": "INTEGER"},
                "fit": {"type": "INTEGER"},
                "paid": {"type": "STRING", "enum": ["yes", "no", "unknown"]},
                "min_years": {"type": "NUMBER"},
                "batch_ok": {"type": "STRING", "enum": ["yes", "no", "unknown"]},
                "location_ok": {"type": "STRING", "enum": ["yes", "no", "unknown"]},
                "matched": {"type": "ARRAY", "items": {"type": "STRING"}},
                "missing": {"type": "ARRAY", "items": {"type": "STRING"}},
                "best_project": {"type": "STRING", "enum": keys},
                "project_rank": {"type": "ARRAY", "items": {"type": "STRING", "enum": keys}},
                "why": {"type": "STRING"},
                "keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["i", "fit", "paid", "min_years", "batch_ok", "location_ok", "matched", "missing",
                         "best_project", "project_rank", "why", "keywords"],
        },
    }


PROMPT = """You screen job postings for one candidate. Use ONLY the profile below; never assume skills that are not listed.

PROFILE
{profile}

CANDIDATE
- {about}
- Location: {location_rule}

RULES
- fit: 0-100. How well the candidate's "Used in projects" skills and projects match the role's core requirements.
  Skills under "Explored / learning" count only a little. Roles needing {hard_max}+ years must score below 30.
- paid: "no" only if the posting says unpaid / no stipend. "unknown" if it doesn't say.
- min_years: minimum years of experience the posting requires (0 if fresher/intern/not stated).
- batch_ok: {batch_rule}
- location_ok: "no" if the role's location breaks the candidate's location rule above (for example onsite in a place they won't work). "unknown" if unclear.
- matched: up to 8 required skills the candidate has. missing: up to 5 important required skills the candidate lacks.
- best_project: the candidate project most relevant to this role (its key).
- project_rank: the 3 project keys that best prove fit for THIS role, most relevant first (for the tailored resume).
- fit 80+ means a strong match: most core requirements are covered by skills used in projects. Be strict; don't inflate.
- why: one plain sentence (max 22 words) addressed to the candidate as "you", on why it fits or doesn't (e.g. "Your FastAPI service and pytest work match their Python API stack.").
- keywords: up to 12 technical terms from the posting (exact spelling as in the posting) that also appear in the candidate's profile.

JOBS
{jobs}

Return a JSON array with one object per job, using the job's index as "i"."""


def build_prompt(prof, listing, cfg):
    cand = cfg.get("candidate") or {}
    year = cand.get("graduation_year")
    batch_rule = (f'"no" only if the posting explicitly limits eligibility to graduation years that exclude {year} '
                  f'(e.g. "{int(year) - 1} batch only"). Otherwise "yes" or "unknown".') if year else '"unknown" always.'
    return PROMPT.format(
        profile=prof, jobs=listing, hard_max=cfg["hard_max_years"], batch_rule=batch_rule,
        about=cand.get("about") or "Open to roles that match the profile.",
        location_rule=cand.get("location_rule") or "Any location.")


def score(jobs, cfg=None, batch=8, pause=4):
    """Score jobs in place (adds job['score']). Jobs whose batch fails keep score=None."""
    cfg = cfg or config.search_cfg()
    prof = profile_text()
    schema = score_schema()
    for start in range(0, len(jobs), batch):
        chunk = jobs[start:start + batch]
        listing = "\n\n".join(
            f"[{i}] {j['title']} at {j['company']} | {j['location']} | salary: {j.get('salary') or 'not stated'}"
            f" | experience: {j.get('exp_min')}-{j.get('exp_max')}\n{(j.get('description') or '')[:2500]}"
            for i, j in enumerate(chunk))
        try:
            res = gemini(build_prompt(prof, listing, cfg), schema)
        except Exception as e:  # noqa: BLE001
            print(f"[score] batch {start} failed: {e}")
            continue
        for r in res:
            if 0 <= r.get("i", -1) < len(chunk):
                chunk[r["i"]]["score"] = r
        time.sleep(pause)
    return jobs


def hard_fail(s, cfg):
    """Rules that make a job ineligible, given Gemini's reading of it."""
    if s["paid"] == "no" and (cfg.get("candidate") or {}).get("paid_only", True):
        return "unpaid"
    if s["min_years"] and s["min_years"] >= cfg["hard_max_years"]:
        return f"needs {s['min_years']:g}+ years"
    if s["batch_ok"] == "no":
        return "excludes your graduation year"
    if s["location_ok"] == "no":
        return "location doesn't work for you"
    if s["fit"] < cfg["min_fit"]:
        return f"low fit ({s['fit']})"
    return None
