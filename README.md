# JobPilot

An open-source job-search assistant you run for yourself.

- **Every morning** a GitHub Actions job searches LinkedIn, Naukri, Foundit, Wellfound and Himalayas, filters out roles that don't match your rules, scores the rest against your profile with Gemini, finds HR emails and alumni at each company, and builds a **one-page resume tailored to each job**.
- **On your phone** (Android app or any browser) you swipe through the matches: open the job, view the tailored PDF, copy the HR email, or send it to your PC.
- **On your PC**, [Claude Code](https://claude.com/claude-code) applies for you: it reads the posting, tailors your resume, signs up on the portal, fills the form, and **stops to ask you before every submit**. Drop in a screenshot of a recruiter's post and it researches the company and drafts a personalised cold email in Gmail (it never sends anything).

Everything is logged in a dashboard and an Excel tracker that updates itself.

### 📱 [Download the Android app (APK)](../../releases/latest/download/JobPilot.apk)

The app has no server built in. On first launch you enter your own inbox address and passcode (see [step 4](#4-phone-inbox-and-android-app-optional)).

---

## Contents

- [What you need](#what-you-need)
- [Setup guide](#setup-guide)
  1. [Get the code](#1-get-the-code)
  2. [Add your profile](#2-add-your-profile)
  3. [Desktop: apply with Claude](#3-desktop-apply-with-claude)
  4. [Phone inbox and Android app](#4-phone-inbox-and-android-app-optional)
  5. [Daily job feed](#5-daily-job-feed-optional)
- [Customise the job feed](#customise-the-job-feed)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Privacy and safety](#privacy-and-safety)

## What you need

| For | You need | Cost |
|---|---|---|
| Desktop auto-apply | Python 3.10+, Google Chrome or Microsoft Edge, [Claude Code](https://claude.com/claude-code) with the **Claude in Chrome** extension. Optional: the Gmail connector in Claude, for cold-email drafts | Claude plan |
| Daily job feed | A GitHub account, a [Gemini API key](https://aistudio.google.com/apikey), an [Apify](https://apify.com) token, a [MongoDB Atlas](https://www.mongodb.com/atlas) database. Optional: a [Hunter.io](https://hunter.io) key | Free tiers work |
| Phone inbox | A [Render](https://render.com) account (or any host that runs Python) | Free tier works |

You can use only the desktop part. The feed and phone inbox are optional.

## Setup guide

### 1. Get the code

**Fork** this repository (button at the top right of GitHub). Your fork is where your profile and your daily feed live. Then clone your fork:

```bash
git clone https://github.com/<your-username>/<your-fork>.git
cd <your-fork>
pip install -r requirements.txt
```

> Your fork is public by default, and your resume facts go in `profile/` and `CLAUDE.md`. If you don't want those public, make the repository private (Settings → General → Danger Zone → Change visibility), or create a private copy using **Use this template** / a fresh private repo instead of a fork.

### 2. Add your profile

Three files describe you. Claude, the scorer and the resume builder use **only** what's in them, and never invent anything.

1. **`profile/master_resume.json`**: your resume. The file ships with example data ("Your Name", example projects); replace all of it. Each project needs a unique `key` and an optional one-line `pitch`. Put projects you only want on some resumes in `extra_projects`.
2. **`CLAUDE.md`**: your details, skills, project write-ups, job preferences, ready answers to screening questions, and companies you've already applied to. Replace every `[FILL]`. Anything you leave as `[FILL]`, Claude asks you once while applying and writes the answer back.
3. **`profile/search.json`**: what the daily feed searches for and how it filters (see [Customise the job feed](#customise-the-job-feed)).

Check your resume renders on one page:

```bash
python scripts/render_resume.py profile/master_resume.json data/preview.pdf
```

Exit code `2` means it's longer than one page. You can restyle it in `profile/resume_template.html`.

### 3. Desktop: apply with Claude

1. **Start the UI.** On Windows, double-click `start.bat`. On macOS/Linux, run `./start.sh` (or `python app.py`) and open http://127.0.0.1:5050.
2. **Profile card.** Optionally upload your resume PDF (Claude then re-syncs `master_resume.json` from it), and set the email and password Claude should use when a portal needs an account. These are saved to `data/settings.json`, which is never committed.
3. **Queue work.**
   - *Apply to jobs:* paste one link per line and click **Add to queue**.
   - *Cold email:* drop or paste (Ctrl+V) a screenshot showing a recruiter's email, add an optional note, and click **Add to queue**.
4. **Process.** Click **▶ Process queue with Claude** (it opens a terminal), or run this in the project folder:
   ```bash
   claude --chrome "/process-queue"
   ```
5. **Answer Claude** when it needs an OTP or CAPTCHA, an answer it doesn't have, or your **yes / edit / skip** before submitting.
6. **Track.** The dashboard refreshes every 5 seconds. Click **⬇ Excel tracker** for `Applications.xlsx` (sheets for Applications, Cold Emails and a Summary), or **CSV**.

Task statuses: `pending` → `in_progress` → `needs_input` / `awaiting_approval` → `applied` · `drafted` · `skipped` · `failed`.

### 4. Phone inbox and Android app (optional)

The phone inbox shows each day's matches. It needs the MongoDB database from step 5 (set that up first, or at the same time).

**Deploy it on Render (free):**

1. In Render, choose **New → Blueprint** and pick your fork. It reads [`render.yaml`](render.yaml).
2. When asked, set:
   - `MONGODB_URI`: your MongoDB Atlas connection string (the same one the feed uses)
   - `APP_PASSCODE`: a passcode you'll type to open the inbox (make it long)
   - `SECRET_KEY` is generated for you
3. Optional: set `TIMEZONE` (for example `Asia/Kolkata`) and `KEEP_AWAKE_HOURS` (for example `10-23`). Render's free plan sleeps after 15 idle minutes; with these set, the app keeps itself awake only during those hours, which saves free hours for your other services.
4. Open your Render URL (for example `https://jobpilot-inbox-xxxx.onrender.com`) and log in with your passcode. In a phone browser you can also use **Add to Home screen**.

**Android app:**

1. [Download JobPilot.apk](../../releases/latest/download/JobPilot.apk) on your phone and install it (allow "install unknown apps" for your browser when asked).
2. Open it, enter your Render URL and passcode, and tap **Connect**. The ⚙ button disconnects or switches servers.
3. Allow notifications to get an alert when a feed run finds new jobs. The app checks about every 15 minutes, even when closed.

To build the APK yourself, push a tag (`git tag v1.0.1 && git push --tags`) and the **Build Android app** workflow attaches `JobPilot.apk` to a GitHub Release. You can also run the workflow from the Actions tab and download the APK from the run. Builds are debug-signed, so installing a build from a different source over an existing install needs an uninstall first.

**In the app:** swipe right (or tap **💻 Apply from PC**) to send a job to your PC, swipe left to hide it, and filter by HR email, internship, remote, fit or resume. On the desktop dashboard, **From phone → ⚡ Auto-apply all** queues those jobs and starts Claude.

### 5. Daily job feed (optional)

1. **Create the services** (all have free tiers):
   - **MongoDB Atlas**: create a free cluster, a database user, and allow access from anywhere (`0.0.0.0/0`, since GitHub Actions and Render have changing IPs). Copy the connection string and add `/jobpilot` as the database name.
   - **Gemini**: create an API key at https://aistudio.google.com/apikey.
   - **Apify**: copy your API token (Settings → Integrations). It runs the LinkedIn, Naukri, Foundit, Wellfound and Google search scrapers.
   - **Hunter.io** (optional): your API key, for verified HR emails on the top matches.
2. **Add GitHub secrets** in your fork: Settings → Secrets and variables → Actions → **New repository secret**: `MONGODB_URI`, `GEMINI_API_KEY`, `APIFY_TOKEN`, and optionally `HUNTER_API_KEY`.
3. **Optional repository variables** (same page, **Variables** tab):
   - `TIMEZONE`: your time zone, for example `Asia/Kolkata`
   - `INBOX_URL`: your Render URL, so each run wakes the inbox first
4. **Enable Actions** in your fork (Actions tab → "I understand my workflows, go ahead and enable them"), then open **Daily job feed** → **Run workflow** to test it. It takes about 5–10 minutes.
5. **Pick the time.** The schedule is in [`.github/workflows/discover.yml`](.github/workflows/discover.yml) and uses UTC (default 04:30 UTC, with two backup runs that skip themselves if the feed already ran that day). You can pause and resume the feed from the toggle in the phone app.

To run the feed on your PC instead, copy `.env.example` to `data/.env`, fill in the keys, and run:

```bash
python scripts/discover.py --dry-run     # prints results, writes nothing
python scripts/discover.py               # full run
python scripts/discover.py --portals himalayas --no-contacts
```

With `MONGODB_URI` in `data/.env`, the desktop dashboard also shows the feed, so you can queue a job straight from it.

## Customise the job feed

Everything is in `profile/search.json`:

| Key | What it does |
|---|---|
| `portals` | Which boards to search: `linkedin`, `naukri`, `foundit`, `wellfound`, `himalayas`. Naukri and Foundit are India-only. |
| `country`, `country_code` | Where LinkedIn, Wellfound and Himalayas search, and the Google region for contact search. |
| `allowed_locations` | Non-remote jobs whose location contains none of these words are skipped. `[]` allows any location. |
| `candidate` | Tells the scorer about you: `about`, `experience_years`, `graduation_year` (or `null`), `location_rule`, and `paid_only`. |
| `keywords`, `keywords_per_day` | Search terms. Each day uses the next few per portal, so a long list is covered over several days. |
| `limit_per_keyword` | Max postings fetched per keyword per portal (this controls Apify cost). |
| `title_exclude`, `title_exclude_unless` | Skip titles like "senior", unless an allowed phrase is present. |
| `max_experience_years`, `hard_max_years` | Skip jobs whose stated minimum is above `max_experience_years`, and jobs Gemini reads as needing `hard_max_years` or more. |
| `min_fit` | Minimum Gemini fit score (0–100) to show a job. |
| `contacts_for_top`, `hunter_per_run`, `hunter_reserve` | How many top jobs get an HR-email search, and how many Hunter credits a run may use or must leave unused. |
| `resumes_for_top` | How many top jobs get a tailored resume PDF. |
| `keep_days` | Untouched leads older than this are deleted. |
| `alumni.college_names` | Your college's names (for example `["Example Institute of Technology", "EIT"]`) to find alumni at each company, each with a ready referral message. Empty means no alumni search. |
| `referral_message` | The referral template. Placeholders: `{first}`, `{me}`, `{role}`, `{company}`, `{pitch}`. |

To change how Claude applies (tone, approval rules, what it may tailor), edit `CLAUDE.md` and [`.claude/commands/process-queue.md`](.claude/commands/process-queue.md).

## How it works

```
 GitHub Actions (daily)                 MongoDB Atlas                 Phone (app / browser)
 scripts/discover.py      ──leads──▶    leads, resume PDFs   ◀──────▶  cloud_app.py on Render
 search → filter → Gemini score                │                      swipe: apply from PC / hide
 → HR emails, alumni → tailored PDFs           │
                                               ▼
 Desktop: app.py (127.0.0.1:5050)  ──tasks.json──▶  Claude Code /process-queue
 queue links & screenshots, dashboard,              + Claude in Chrome + Gmail
 Excel tracker                      ◀─status/files─ scan JD → check rules → tailor resume
                                                    → apply → ask you → submit
```

- **Tailored resumes** ([jobbot/tailor.py](jobbot/tailor.py)) only reorder, select and bold content from `master_resume.json`. A verification step rejects any line that isn't in the master, so nothing invented can get in. PDFs are rendered with headless Chrome and trimmed to one page.
- **Scoring** ([jobbot/scoring.py](jobbot/scoring.py)) runs cheap rules first, then Gemini (with a model fallback chain) on the survivors. Rejected jobs are remembered so they aren't scored twice.
- **Contacts** ([jobbot/contacts.py](jobbot/contacts.py)) come from public search snippets first, then Hunter.io for the top jobs. Nothing is guessed.

## Project structure

```
app.py                         Desktop UI + JSON API (queue, dashboard, feed actions)
cloud_app.py                   Hosted phone inbox (passcode login, app tokens, signed resume links)
templates/                     index.html (desktop), mobile.html (phone inbox + Android app), mobile_login.html
jobbot/store.py                Task and settings storage (JSON)
jobbot/excel.py                Excel tracker
jobbot/sources.py              Portal fetchers (Apify, Himalayas API)
jobbot/scoring.py              Filters + Gemini fit scoring
jobbot/contacts.py             HR emails, alumni, referral messages
jobbot/tailor.py               Tailored one-page resumes
jobbot/leads.py                Leads and PDFs in MongoDB
scripts/discover.py            The daily feed
scripts/task.py                CLI Claude uses to read and update tasks
scripts/render_resume.py       Resume JSON → HTML → PDF
profile/                       master_resume.json, resume_template.html, search.json
.claude/commands/              /process-queue workflow for Claude Code
CLAUDE.md                      Your profile, rules and screening answers
mobile/                        Capacitor Android app (bundles templates/mobile.html)
.github/workflows/             discover.yml (daily feed), apk.yml (Android build + release)
render.yaml                    Render blueprint for the phone inbox
data/                          Local only, git-ignored: queue, uploads, outputs, settings, keys
```

## Privacy and safety

- Your queue, uploads, outputs, credentials and API keys stay in `data/`, which is git-ignored. Keys for the cloud parts live in GitHub secrets and Render environment variables, never in code.
- Claude never submits an application or sends an email without your explicit "yes". Outreach is only ever a Gmail **draft**.
- The phone inbox is protected by your passcode (with rate-limited login). Resume links are signed per job.
- Automated applying may be against some job portals' terms of service. Use it responsibly and review every application.

## License

[MIT](LICENSE)
