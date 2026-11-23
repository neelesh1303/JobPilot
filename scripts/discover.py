"""Daily job feed: search portals -> filter -> score -> find HR emails/alumni -> tailor resumes -> save leads.

  python scripts/discover.py                      # full run (what the daily schedule does)
  python scripts/discover.py --portals himalayas  # only some portals
  python scripts/discover.py --dry-run            # print results, write nothing
  python scripts/discover.py --no-contacts --no-resumes

Settings: profile/search.json. Keys: data/.env locally, environment variables in CI.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import tempfile
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from jobbot import config, contacts, leads, scoring, sources, tailor  # noqa: E402

MAX_SCORED_PER_RUN = 90


def todays_keywords(cfg, portal):
    kws, n = cfg["keywords"], cfg["keywords_per_day"].get(portal, 1)
    start = (date.today().toordinal() * n) % len(kws)
    return [kws[(start + i) % len(kws)] for i in range(n)]


def claude_md_applied():
    """Companies listed in CLAUDE.md section 8 (already applied), written as "- Company: role"."""
    with open(os.path.join(config.ROOT, "CLAUDE.md"), encoding="utf-8") as f:
        md = f.read()
    m = re.search(r"## 8\..*?(?=\n## |\Z)", md, re.S)
    names = set()
    for line in (m.group(0) if m else "").splitlines():
        mm = re.match(r"- ([^:(]+?)(?:\s*\(.*?\))?:", line)
        if mm:
            names.add(mm.group(1).strip().lower())
    return names


def fetch_all(cfg, portals):
    jobs, report = [], {}

    def one(portal, kw):
        lim = cfg["limit_per_keyword"].get(portal, 15)
        return portal, kw, sources.FETCHERS[portal](kw, lim)

    tasks = [(p, kw) for p in portals for kw in todays_keywords(cfg, p)]
    with cf.ThreadPoolExecutor(6) as ex:
        futs = [ex.submit(one, p, kw) for p, kw in tasks]
        for fut, (p, kw) in zip(futs, tasks):
            try:
                _, _, got = fut.result()
                jobs += [j for j in got if j.get("url") and j.get("title") and j.get("company")]
                report.setdefault(p, {"found": 0, "errors": []})["found"] += len(got)
            except Exception as e:  # noqa: BLE001
                report.setdefault(p, {"found": 0, "errors": []})["errors"].append(f"{kw}: {str(e)[:200]}")
                print(f"[fetch] {p} '{kw}' failed: {e}")
    return jobs, report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--portals", default="", help="comma-separated; default: \"portals\" in profile/search.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-contacts", action="store_true")
    ap.add_argument("--no-resumes", action="store_true")
    ap.add_argument("--force", action="store_true", help="run even if the feed is paused")
    a = ap.parse_args()
    cfg = config.search_cfg()
    if not a.dry_run and not a.force and not leads.feed_enabled():
        print("[feed] paused from the app; nothing to do. Resume it in the JobPilot app.")
        return 0
    t0 = time.time()

    portals = [p.strip() for p in (a.portals.split(",") if a.portals else cfg["portals"]) if p.strip()]
    unknown = [p for p in portals if p not in sources.FETCHERS]
    if unknown:
        print(f"[feed] unknown portals {unknown}; choose from {list(sources.FETCHERS)}")
        return 1
    jobs, report = fetch_all(cfg, portals)
    print(f"[fetch] {len(jobs)} postings")

    # de-duplicate: within this run, against earlier leads, and against jobs already rejected
    for j in jobs:
        j["_id"], j["dedupe_key"] = leads.lead_id(j), leads.dedupe_key(j)
    uniq = {}
    for j in jobs:
        uniq.setdefault(j["dedupe_key"], j)
    jobs = list(uniq.values())
    if not a.dry_run:
        ids = [j["_id"] for j in jobs]
        old = leads.known_ids(ids) | leads.seen_ids(ids)
        old_keys = leads.known_dedupe_keys([j["dedupe_key"] for j in jobs])
        jobs = [j for j in jobs if j["_id"] not in old and j["dedupe_key"] not in old_keys]
    print(f"[dedupe] {len(jobs)} new")

    rejected, candidates = [], []
    for j in jobs:
        why = scoring.prefilter(j, cfg)
        (rejected if why else candidates).append(j)
    print(f"[prefilter] {len(candidates)} pass, {len(rejected)} rejected")
    candidates = candidates[:MAX_SCORED_PER_RUN]

    scoring.score(candidates, cfg)
    passed = []
    for j in candidates:
        s = j.get("score")
        if not s:
            continue  # Gemini failed for this batch: retry on the next run
        why = scoring.hard_fail(s, cfg)
        if why:
            rejected.append(j)
        else:
            passed.append(j)
    passed.sort(key=lambda j: -j["score"]["fit"])
    print(f"[score] {len(passed)} eligible leads")

    applied = claude_md_applied() | (set() if a.dry_run else leads.applied_companies())
    out = []
    for j in passed:
        s = j.pop("score")
        lead = {**j, "fit": s["fit"], "matched": s["matched"], "missing": s["missing"],
                "best_project": s["best_project"], "project_rank": s.get("project_rank", []), "why": s["why"], "keywords": s["keywords"],
                "status": "new", "found_at": leads.utcnow(), "updated_at": leads.utcnow(),
                "hr_emails": [], "alumni": [], "contacts_status": "not_searched", "resume": None}
        if j["company"].strip().lower() in applied:
            lead["note"] = f"You already applied to {j['company']} before. Check the role isn't the same."
        out.append(lead)

    if not a.no_contacts and out:
        top = out[:cfg["contacts_for_top"]]
        budget = 0 if a.dry_run else max(0, min(cfg["hunter_per_run"], contacts.hunter_remaining() - cfg["hunter_reserve"]))
        used = contacts.enrich(top, budget)
        print(f"[contacts] searched {len(top)} companies, Hunter searches used: {used}")

    if not a.no_resumes and out:
        with tempfile.TemporaryDirectory() as d:
            for lead in out[:cfg["resumes_for_top"]]:
                try:
                    r = tailor.build(lead["description"], lead["best_project"], lead["keywords"] + lead["matched"],
                                     lead["company"], lead.get("project_rank", []))
                    name = tailor.file_name(lead["company"])
                    pdf = os.path.join(d, lead["_id"] + ".pdf")
                    final = tailor.render_pdf(r, pdf)
                    lead["resume"] = {"file": name, "projects": [re.split(r" [–—-] ", p["name"])[0] for p in final["projects"]],
                                      "bolded": final["_terms"][:12]}
                    if a.dry_run:
                        os.replace(pdf, os.path.join(config.ROOT, "data", name))
                    else:
                        leads.put_resume(lead["_id"], pdf, name)
                except Exception as e:  # noqa: BLE001
                    print(f"[resume] {lead['company']}: {e}")

    if a.dry_run:
        for l in out:
            print(json.dumps({k: l[k] for k in ("source", "company", "title", "fit", "why", "missing", "best_project",
                                                 "contacts_status", "hr_emails", "alumni", "resume", "url")},
                             ensure_ascii=False, default=str)[:900])
    else:
        for l in out:
            leads.save(l)
        leads.save_skipped([j["_id"] for j in rejected])
        pruned = leads.prune(cfg["keep_days"])
        leads.db().runs.insert_one({"at": leads.utcnow(), "portals": report, "new_leads": len(out),
                                    "rejected": len(rejected), "seconds": round(time.time() - t0), "pruned": pruned})
    print(f"[done] {len(out)} leads in {round(time.time() - t0)}s; portals: {json.dumps(report)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
