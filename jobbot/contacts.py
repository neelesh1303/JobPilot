"""Find HR / recruiter emails and alumni of your college at a company.

Sources, cheapest first:
  - Google search via Apify (emails in public snippets; LinkedIn profiles of alumni)
  - Hunter.io domain search (verified company emails; limited free credits, so only for top jobs)
Nothing is guessed: if no email turns up, the lead is marked "not_found".

The alumni search runs only when profile/search.json lists your college under "alumni" -> "college_names".
The referral message is the "referral_message" template in search.json; each project's "pitch" comes from
profile/master_resume.json.
"""
import re

import requests

from jobbot import config
from jobbot.config import env
from jobbot.sources import google

# Snippets often glue words together ("hr@acme.comRegistered office"), so the TLD must be a known one
# and the match stops right after it.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*?\."
                      r"(?:co\.in|co\.uk|org\.in|net\.in|ac\.in|com|in|ai|io|co|org|net|tech|app|dev|xyz|us|uk|so|me|info|biz|gg|cloud)"
                      r"(?![A-Za-z0-9-]*\.[a-z])", re.I)
HR_WORDS = re.compile(r"recruit|talent|hr\b|human resource|people|hiring|careers?|campus|acquisition", re.I)
JUNK = re.compile(r"\.(png|jpe?g|gif|webp|svg)$|example\.|sentry|wixpress|@2x|noreply|no-reply|privacy|abuse|support@|sales@|press@|legal@", re.I)


def college_names():
    return [n for n in (config.search_cfg().get("alumni") or {}).get("college_names", []) if n.strip()]


def pitches():
    """{project key: one-line pitch} from the master resume. Falls back to the project's name."""
    out = {}
    for p in config.master_resume()["projects"] + config.master_resume().get("extra_projects", []):
        name = re.sub(r"<.*?>", "", re.split(r" [–—-] ", p["name"])[0])
        out[p["key"]] = p.get("pitch") or name
    return out


def _name_token(company):
    words = [w for w in re.findall(r"[a-z0-9]+", (company or "").lower())
             if w not in ("pvt", "ltd", "private", "limited", "inc", "technologies", "technology", "solutions",
                          "india", "labs", "the", "and", "software", "services", "systems", "llp", "corp")]
    return words[0] if words else ""


def queries_for(company):
    c = company.replace('"', "")
    q = {"email": f'"{c}" (HR OR recruiter OR "talent acquisition" OR careers OR hiring) email "@"'}
    names = college_names()
    if names:
        q["alumni"] = "site:linkedin.com/in (" + " OR ".join(f'"{n}"' for n in names) + f') "{c}"'
    return q


def emails_from_results(results, company, domain=""):
    tok = _name_token(company)
    found = {}
    for r in results:
        text = f"{r.get('title', '')} {r.get('description', '')}"
        for e in EMAIL_RE.findall(text):
            e = e.strip(".").lower()
            if JUNK.search(e):
                continue
            dom = e.split("@")[1]
            related = (domain and dom.endswith(domain)) or (tok and tok in dom) or (tok and tok in text.lower())
            if not related:
                continue
            hr = bool(HR_WORDS.search(e.split("@")[0]) or HR_WORDS.search(text))
            found.setdefault(e, {"email": e, "name": "", "position": "", "source": "web search", "verified": False,
                                 "hr": hr, "evidence": r.get("url", "")})
    return sorted(found.values(), key=lambda x: not x["hr"])[:4]


def alumni_from_results(results, company):
    names = college_names()
    if not names:
        return []
    college_re = re.compile("|".join(rf"\b{re.escape(n.lower())}\b" for n in names))
    tok = _name_token(company)
    out = []
    for r in results:
        url, title, desc = r.get("url", ""), r.get("title", ""), r.get("description", "")
        if "linkedin.com/in/" not in url:
            continue
        blob = (title + " " + desc).lower()
        if not college_re.search(blob):
            continue
        # must currently work there: company in the headline, or "Experience: <company>" in the snippet
        at_company = re.search(rf"\b{re.escape(tok)}\b", title.lower()) or re.search(
            rf"experience:\s*{re.escape(company.lower())}", desc.lower())
        if not tok or not at_company:
            continue
        if re.search(rf"\b(ex|former|formerly|previously)\b[\s\-–@:]*{re.escape(tok)}", title.lower()):
            continue  # left the company
        if re.search(r"\bstudent\b|undergraduate", title.lower()):
            continue
        name = re.split(r"\s[-–|]\s", title)[0].strip()
        headline = title[len(name):].strip(" -–|").replace("| LinkedIn", "").strip()
        out.append({"name": name, "headline": headline[:120], "url": url.split("?")[0]})
    return out[:5]


def _hunter_call(company, domain, **extra):
    params = {"api_key": env("HUNTER_API_KEY"), "limit": 10, **extra}
    params.update({"domain": domain} if domain else {"company": company})
    r = requests.get("https://api.hunter.io/v2/domain-search", params=params, timeout=30)
    if not r.ok:
        print(f"[hunter] {company}: {r.status_code} {r.text[:120]}")
        return {}
    return r.json().get("data") or {}


def hunter(company, domain=""):
    """HR people first, then generic inboxes (careers@, hr@), then anyone. Empty Hunter results cost no credit."""
    if not env("HUNTER_API_KEY"):
        return [], ""
    d = _hunter_call(company, domain, department="hr")
    domain = d.get("domain") or domain
    if not d.get("emails"):
        d = _hunter_call(company, domain, type="generic") or d
        domain = d.get("domain") or domain
    if not d.get("emails"):
        d = _hunter_call(company, domain) or d
    rows = []
    for e in d.get("emails") or []:
        pos = e.get("position") or ""
        dept = e.get("department") or ""
        hr = dept == "hr" or bool(HR_WORDS.search(pos)) or bool(HR_WORDS.search(e.get("value", "").split("@")[0]))
        rank = 0 if hr else (1 if e.get("type") == "generic" else (2 if dept in ("executive", "management") else 3))
        rows.append((rank, -(e.get("confidence") or 0), {
            "email": e.get("value"), "name": " ".join(x for x in (e.get("first_name"), e.get("last_name")) if x),
            "position": pos, "source": "Hunter.io", "verified": (e.get("verification") or {}).get("status") == "valid",
            "confidence": e.get("confidence"), "hr": hr, "evidence": (e.get("sources") or [{}])[0].get("uri", "") if e.get("sources") else ""}))
    rows.sort(key=lambda x: (x[0], x[1]))
    return [r[2] for r in rows[:4]], d.get("domain") or domain


def hunter_remaining():
    key = env("HUNTER_API_KEY")
    if not key:
        return 0
    try:
        d = requests.get("https://api.hunter.io/v2/account", params={"api_key": key}, timeout=30).json()["data"]
        return int(d["requests"]["searches"]["available"] - d["requests"]["searches"]["used"])
    except Exception:  # noqa: BLE001
        return 0


def referral_message(person_name, company, role, best_project):
    first = (person_name or "").split(" ")[0].title() or "there"
    p = pitches()
    pitch = p.get(best_project) or next(iter(p.values()), "a few projects related to this role")
    me = config.candidate_name() or "a candidate interested in this role"
    return config.search_cfg()["referral_message"].format(first=first, me=me, role=role, company=company, pitch=pitch)


def enrich(leads, hunter_budget):
    """Add hr_emails, alumni and contacts_status to each lead. Spends at most hunter_budget Hunter searches."""
    if not leads:
        return 0
    qs = {}
    for l in leads:
        q = queries_for(l["company"])
        l["_q"] = q
        for v in q.values():
            qs[v] = True
    try:
        results = google(list(qs))
    except Exception as e:  # noqa: BLE001
        print(f"[contacts] web search failed: {e}")
        results = {}
    used = 0
    for l in leads:
        q = l.pop("_q")
        emails = emails_from_results(results.get(q["email"], []), l["company"], l.get("company_domain", ""))
        if not any(e["hr"] for e in emails) and used < hunter_budget:
            h, dom = hunter(l["company"], l.get("company_domain", ""))
            used += 1
            if dom:
                l["company_domain"] = dom
            seen = {e["email"] for e in emails}
            emails = [e for e in h if e["email"] not in seen] + emails
        l["hr_emails"] = emails[:4]
        # found = at least one HR/recruiting/careers address; other_only = only founders/other staff
        l["contacts_status"] = ("found" if any(e["hr"] for e in emails) else "other_only") if emails else "not_found"
        alumni = alumni_from_results(results.get(q.get("alumni"), []), l["company"]) if q.get("alumni") else []
        for a in alumni:
            a["message"] = referral_message(a["name"], l["company"], l["title"], l.get("best_project"))
        l["alumni"] = alumni
    return used
