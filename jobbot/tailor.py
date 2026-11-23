"""Build a one-page resume tailored to one JD, using ONLY master_resume.json content.

Tailoring here never writes new text. It only:
  - picks which 3 projects to show (best match first),
  - orders bullets within each project and items within each skill line by JD relevance,
  - bolds JD terms that already appear in a bullet,
  - drops the least relevant bullets if the PDF runs over one page.
verify() re-checks the result against the master, so nothing invented can slip in.
"""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile

from jobbot.config import ROOT

MASTER = os.path.join(ROOT, "profile", "master_resume.json")


def master():
    with open(MASTER, encoding="utf-8") as f:
        return json.load(f)


def plain(s):
    return re.sub(r"</?b>", "", s or "")


def _term_re(t):
    return re.compile(r"(?<![\w+#.])" + re.escape(t) + r"(?![\w+#])", re.I)


def _hits(text, terms):
    text = plain(text)
    return sum(1 for t in terms if _term_re(t).search(text))


def bold(html, terms):
    """Wrap JD terms in <b>, but only in text that is not already bold."""
    terms = sorted({t for t in terms if len(t) >= 2}, key=len, reverse=True)
    if not terms:
        return html
    rx = re.compile("|".join(_term_re(t).pattern for t in terms), re.I)
    out, depth = [], 0
    for part in re.split(r"(</?b>)", html):
        if part == "<b>":
            depth += 1
            out.append(part)
        elif part == "</b>":
            depth -= 1
            out.append(part)
        elif depth == 0:
            out.append(rx.sub(lambda m: f"<b>{m.group(0)}</b>", part))
        else:
            out.append(part)
    return "".join(out)


def jd_terms(jd_text, extra=()):
    """Terms worth emphasising: resume skill items found in the JD, plus Gemini's keywords that are in the resume."""
    m = master()
    jd = jd_text or ""
    resume_text = plain(json.dumps(m, ensure_ascii=False))
    terms = set()
    for s in m["skills"]:
        for item in s["items"]:
            base = re.sub(r"\s*\(.*?\)", "", item)  # "AWS (EC2)" -> "AWS"
            for cand in {item, base}:
                if _term_re(cand).search(jd):
                    terms.add(cand)
    for k in extra:
        k = k.strip()
        # only real tech terms ("RAG", "Node.js", "C++"), not plain words like "testing" or "cloud"
        if k and k != k.lower() and _term_re(k).search(resume_text) and _term_re(k).search(jd):
            terms.add(k)
    return sorted(terms)


def build(jd_text, best_project=None, keywords=(), company="", project_rank=()):
    """project_rank: Gemini's top project keys for this JD (most relevant first). Keyword overlap breaks ties."""
    m = master()
    terms = jd_terms(jd_text, keywords)
    pool = m["projects"] + m.get("extra_projects", [])
    rank = [k for k in ([best_project] if best_project else []) + list(project_rank) if k]
    rank = list(dict.fromkeys(rank))  # de-duplicate, keep order

    def relevance(p):
        return _hits(p["name"] + " " + p["stack"] + " " + " ".join(p["bullets"]), terms)

    default_rank = {id(p): i for i, p in enumerate(pool)}
    ranked = sorted(pool, key=lambda p: (rank.index(p["key"]) if p.get("key") in rank else len(rank),
                                         -relevance(p), default_rank[id(p)]))
    chosen = [copy.deepcopy(p) for p in ranked[:3]]
    for p in chosen:
        p.pop("key", None)
    for p in chosen:
        order = sorted(range(len(p["bullets"])), key=lambda i: (-_hits(p["bullets"][i], terms), i))
        p["bullets"] = [bold(p["bullets"][i], terms) for i in order]

    r = copy.deepcopy(m)
    r.pop("_comment", None)
    r["projects"] = chosen
    r.pop("extra_projects", None)
    for s in r["skills"]:
        s["items"] = sorted(s["items"], key=lambda it: (-_hits(it, terms), s["items"].index(it)))
    r["_tailored_for"] = company
    r["_terms"] = terms
    return r


def verify(r):
    """Every project bullet, skill item and achievement must exist in the master (ignoring <b> tags)."""
    m = master()
    bullets = {plain(b) for p in m["projects"] + m.get("extra_projects", []) for b in p["bullets"]}
    items = {i for s in m["skills"] for i in s["items"]}
    names = {p["name"] for p in m["projects"] + m.get("extra_projects", [])}
    for p in r["projects"]:
        assert p["name"] in names, f"unknown project {p['name']}"
        for b in p["bullets"]:
            assert plain(b) in bullets, f"bullet not in master: {plain(b)[:80]}"
    for s in r["skills"]:
        for i in s["items"]:
            assert i in items, f"skill not in master: {i}"
    assert [plain(a) for a in r["achievements"]] == [plain(a) for a in m["achievements"]]
    assert r["education"] == m["education"] and r["contact"] == m["contact"] and r["name"] == m["name"]
    assert r.get("summary", "") == m.get("summary", "")


def render_pdf(r, out_pdf):
    """Render with scripts/render_resume.py; trim the least relevant bullets until it fits one page."""
    script = os.path.join(ROOT, "scripts", "render_resume.py")
    work = copy.deepcopy(r)
    for _ in range(6):
        verify(work)
        with tempfile.TemporaryDirectory() as d:
            jp = os.path.join(d, "resume.json")
            with open(jp, "w", encoding="utf-8") as f:
                json.dump(work, f, ensure_ascii=False)
            code = subprocess.run([sys.executable, script, jp, out_pdf], capture_output=True, text=True).returncode
        if code == 0:
            return work
        if code != 2:
            raise RuntimeError("resume render failed")
        # over one page: drop the last (least relevant) bullet of the project with the most bullets
        p = max(work["projects"], key=lambda p: len(p["bullets"]))
        if len(p["bullets"]) <= 2:
            break
        p["bullets"].pop()
    raise RuntimeError("could not fit resume on one page")


def _safe(s, n=40):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")[:n]


def file_name(company):
    """<Your_Name>_Resume_<Company>.pdf, using the name in master_resume.json."""
    from jobbot.config import candidate_name
    me = _safe(candidate_name(), 60)
    return f"{me + '_' if me else ''}Resume_{_safe(company) or 'Company'}.pdf"
