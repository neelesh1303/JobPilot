"""Secrets and search settings.

Locally, keys come from data/.env (git-ignored). On Render / GitHub Actions they come
from real environment variables. Nothing secret is ever stored in the repo.
"""
import json
import os
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, "data", ".env")
SEARCH_FILE = os.path.join(ROOT, "profile", "search.json")

_loaded = False
_lock = threading.Lock()


def _load_env_file():
    global _loaded
    if _loaded:
        return
    with _lock:  # several fetch threads may ask for a key at the same moment
        if _loaded:
            return
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if v and not os.environ.get(k):
                        os.environ[k] = v
        _loaded = True


def env(name, default=""):
    _load_env_file()
    return os.environ.get(name, default)


def search():
    """Raw profile/search.json. Most code should use search_cfg()."""
    with open(SEARCH_FILE, encoding="utf-8") as f:
        return json.load(f)


MASTER_FILE = os.path.join(ROOT, "profile", "master_resume.json")

# Defaults for every search.json key, so an older or trimmed search.json keeps working.
SEARCH_DEFAULTS = {
    "portals": ["linkedin", "naukri", "foundit", "wellfound", "himalayas"],
    "keywords": ["software engineer"],
    "keywords_per_day": {},
    "limit_per_keyword": {},
    "country": "India",
    "country_code": "IN",
    "allowed_locations": [],
    "candidate": {},
    "max_experience_years": 1,
    "hard_max_years": 2,
    "title_exclude": [],
    "title_exclude_unless": {},
    "min_fit": 80,
    "contacts_for_top": 8,
    "hunter_per_run": 3,
    "hunter_reserve": 5,
    "resumes_for_top": 15,
    "keep_days": 30,
    "alumni": {"college_names": []},
    "referral_message": ("Hi {first}, I'm {me}. I saw the {role} opening at {company}. I've built {pitch}. "
                         "Would you be open to referring me, or pointing me to the right person? "
                         "Happy to share my resume. Thank you!"),
}


def search_cfg():
    """search.json merged over SEARCH_DEFAULTS."""
    cfg = dict(SEARCH_DEFAULTS)
    cfg.update({k: v for k, v in search().items() if not k.startswith("_")})
    return cfg


def master_resume():
    with open(MASTER_FILE, encoding="utf-8") as f:
        return json.load(f)


def candidate_name():
    """Your name from profile/master_resume.json ("" while it is still the placeholder)."""
    name = (master_resume().get("name") or "").strip()
    return "" if name.lower() in ("", "your name") else name
