"""Fetch fresh job postings from each portal and normalise them to one shape.

Normalised job:
  {source, external_id, url, title, company, location, remote, posted, description,
   salary, exp_min, exp_max, company_domain, skills}

Where to search (country, LinkedIn/Wellfound location) comes from profile/search.json.
"""
import html
import re
import time
from datetime import datetime, timezone

import requests

from jobbot import config
from jobbot.config import env

APIFY = "https://api.apify.com/v2"

ACTORS = {
    "linkedin": "valig~linkedin-jobs-scraper",
    "naukri": "valig~naukri-jobs-scraper",
    "foundit": "themineworks~foundit-jobs-scraper",  # some other Foundit actors refuse free-plan API runs (402)
    "wellfound": "memo23~wellfound-jobs-scraper",
    "google": "scraperlink~google-search-results-serp-scraper",
}


def _cfg():
    return config.search_cfg()


def apify_run(actor, payload, max_usd=0.5, wait_s=600):
    """Run an Apify actor, wait for it, and return its dataset items."""
    tok = env("APIFY_TOKEN")
    if not tok:
        raise RuntimeError("APIFY_TOKEN is not set")
    h = {"Authorization": f"Bearer {tok}"}
    # The free plan caps the memory of runs going at once; when other scrapers are busy Apify answers 402
    # (not a billing problem). Wait for them to finish and try again.
    for attempt in range(6):
        r = requests.post(f"{APIFY}/acts/{actor}/runs", params={"maxTotalChargeUsd": max_usd, "waitForFinish": 60},
                          json=payload, headers=h, timeout=90)
        if r.status_code != 402 or attempt == 5:
            break
        time.sleep(45)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} from Apify: {r.text[:200]}")
    run = r.json()["data"]
    deadline = time.time() + wait_s
    while run["status"] in ("READY", "RUNNING") and time.time() < deadline:
        run = requests.get(f"{APIFY}/actor-runs/{run['id']}", params={"waitForFinish": 60}, headers=h, timeout=90).json()["data"]
    if run["status"] in ("READY", "RUNNING"):
        requests.post(f"{APIFY}/actor-runs/{run['id']}/abort", headers=h, timeout=30)
    items = requests.get(f"{APIFY}/datasets/{run['defaultDatasetId']}/items", params={"clean": "true"},
                         headers=h, timeout=90).json()
    return items if isinstance(items, list) else []


def strip_html(s):
    s = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _iso(v):
    if v in (None, "", "None"):
        return ""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        v = float(v)
        if v > 1e11:
            v /= 1000
        return datetime.fromtimestamp(v, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(v)[:10]


def _domain(url):
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


# ---------- per-portal fetchers ----------
def linkedin(keyword, limit):
    items = apify_run(ACTORS["linkedin"], {"keywords": keyword, "location": _cfg()["country"],
                                           "datePosted": "r86400", "limit": limit})
    out = []
    for j in items:
        out.append({
            "source": "LinkedIn", "external_id": str(j.get("id")), "url": j.get("url"),
            "apply_url": j.get("applyUrl") or "", "title": j.get("title", ""), "company": j.get("companyName", ""),
            "location": j.get("location", ""), "remote": "remote" in (j.get("location", "") + j.get("title", "")).lower(),
            "posted": _iso(j.get("postedDate")), "description": strip_html(j.get("descriptionHtml") or j.get("description")),
            "salary": j.get("salary") or "", "exp_min": None, "exp_max": None, "company_domain": "",
            "skills": [], "level": j.get("experienceLevel", ""),
        })
    return out


def naukri(keyword, limit):
    """Naukri is India-only."""
    items = apify_run(ACTORS["naukri"], {"keywords": keyword, "experience": int(_cfg()["candidate"].get("experience_years", 0)),
                                         "jobAge": "1", "sort": "f", "limit": limit})
    out = []
    for j in items:
        comp, exp, sal = j.get("company") or {}, j.get("experience") or {}, j.get("salary") or {}
        desc = j.get("description") or {}
        skills = j.get("skills") or {}
        out.append({
            "source": "Naukri", "external_id": str(j.get("id")), "url": j.get("url"), "apply_url": "",
            "title": j.get("title", ""), "company": comp.get("name", ""),
            "location": ", ".join(l.get("label", "") for l in j.get("locations") or []),
            "remote": str(j.get("wfhType")) == "2", "posted": (j.get("createdDateText") or "")[:10],
            "description": strip_html(desc.get("full") if isinstance(desc, dict) else desc),
            "salary": sal.get("label", "") if isinstance(sal, dict) else str(sal),
            "exp_min": _num(exp.get("minimum")), "exp_max": _num(exp.get("maximum")), "company_domain": "",
            "skills": (skills.get("preferred") or []) + (skills.get("other") or []) if isinstance(skills, dict) else [],
            "level": "",
        })
    return out


def foundit(keyword, limit):
    """Foundit (formerly Monster India)."""
    items = apify_run(ACTORS["foundit"], {"searchKeywords": [keyword],
                                          "experienceMaxYears": int(_cfg()["max_experience_years"]),
                                          "postedWithinDays": "3", "maxJobs": limit, "includeJobDescription": True})
    out = []
    for j in items:
        if j.get("_type") == "summary" or not j.get("job_id"):
            continue
        desc = j.get("job_description") or j.get("description") or ""
        skills = j.get("skills") or []
        out.append({
            "source": "Foundit", "external_id": str(j.get("job_id")), "url": j.get("apply_url") or j.get("job_url"),
            "apply_url": "", "title": j.get("title", ""), "company": j.get("company", ""),
            "location": j.get("location", ""), "remote": "remote" in (j.get("location") or "").lower(),
            "posted": _iso((j.get("scraped_at") or "")[:10]),
            "description": strip_html(desc) + ("\nSkills: " + ", ".join(skills) if skills else ""),
            "salary": j.get("salary_text") or "", "exp_min": _num(j.get("experience_min_years")),
            "exp_max": _num(j.get("experience_max_years")), "company_domain": "", "skills": skills, "level": "",
        })
    return out


def wellfound(keyword, limit):
    items = apify_run(ACTORS["wellfound"], {"keyword": keyword, "location": _cfg()["country"].lower(),
                                            "experience": "junior", "maxItems": limit, "maxAgeMinutes": 2 * 1440})
    out = []
    for j in items:
        comp = ""
        if j.get("compensationMin"):
            comp = f"{j.get('compensationCurrency') or ''} {j['compensationMin']}–{j.get('compensationMax') or ''}".strip()
        out.append({
            "source": "Wellfound", "external_id": str(j.get("jobId")), "url": j.get("jobUrl"),
            "apply_url": j.get("applyUrl") or "", "title": j.get("jobTitle", ""), "company": j.get("companyName", ""),
            "location": ", ".join(j.get("locations") or []), "remote": bool(j.get("remote")),
            "posted": _iso(j.get("postedAt")), "description": strip_html(j.get("jobDescription")),
            "salary": j.get("compensation") or comp, "exp_min": _num(j.get("yearsExperienceMin")),
            "exp_max": _num(j.get("yearsExperienceMax")), "company_domain": _domain(j.get("companyWebsiteUrl")),
            "skills": [], "level": "",
        })
    return out


def himalayas(keyword, limit):
    """Remote jobs from the free Himalayas API (no key needed)."""
    country = _cfg()["country"]
    out = []
    for seniority in ("Entry-level", "Internship"):
        r = requests.get("https://himalayas.app/jobs/api/search",
                         params={"q": keyword, "country": country, "seniority": seniority}, timeout=30)
        if not r.ok:
            continue
        for j in r.json().get("jobs", [])[:limit]:
            restr = j.get("locationRestrictions") or []
            if restr and country not in restr:
                continue
            sal = ""
            if j.get("minSalary"):
                sal = f"{j.get('currency') or ''} {j['minSalary']}–{j.get('maxSalary') or ''} / {j.get('salaryPeriod') or ''}"
            out.append({
                "source": "Himalayas", "external_id": j.get("guid"), "url": j.get("applicationLink") or j.get("guid"),
                "apply_url": "", "title": j.get("title", ""), "company": j.get("companyName", ""),
                "location": "Remote (" + (", ".join(restr) or "worldwide") + ")", "remote": True,
                "posted": _iso(j.get("pubDate")), "description": strip_html(j.get("description")),
                "salary": sal.strip(), "exp_min": None, "exp_max": None, "company_domain": "",
                "skills": [], "level": ", ".join(j.get("seniority") or []),
            })
    return out


FETCHERS = {"linkedin": linkedin, "naukri": naukri, "foundit": foundit, "wellfound": wellfound, "himalayas": himalayas}


def google(queries, pages="10"):
    """Run several Google searches in one actor run. Returns {query: [ {url,title,description} ]}."""
    if not queries:
        return {}
    items = apify_run(ACTORS["google"], {"keyword": "\n".join(queries), "limit": pages,
                                         "country": _cfg()["country_code"], "include_merged": False}, max_usd=0.5)
    out = {}
    for it in items:
        res = it.get("results") or []
        out.setdefault(it.get("search_term", ""), []).extend(
            {"url": r.get("url", ""), "title": r.get("title", ""), "description": r.get("description", "")} for r in res)
    # The actor may reorder the words of a query (e.g. moves site: to the end); map back by word set.
    mapped = {}
    for q in queries:
        key = frozenset(q.lower().split())
        for term, res in out.items():
            if frozenset(term.lower().split()) == key:
                mapped[q] = res
    return mapped
