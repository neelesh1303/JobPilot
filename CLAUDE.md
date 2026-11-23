# JobPilot: Job Application Assistant

> **Template.** Replace every `[FILL]` with your own details. Anything you leave as `[FILL]`, Claude will ask you about while applying and then write the answer back into this file, so you're never asked twice.
> Keep the section numbers (`## 1.` … `## 8.`): the job feed reads sections 2–3 (to score jobs) and section 8 (companies you already applied to).

This folder is a job-application assistant. The user queues work in a local web UI (`python app.py`, http://127.0.0.1:5050). You (Claude Code) do the work by running the `/process-queue` command. The full workflow is in [.claude/commands/process-queue.md](.claude/commands/process-queue.md).

Key files:
- `profile/master_resume.json`: the single source of truth for resume facts. Tailored resumes are built only from it.
- `profile/resume_template.html` + `scripts/render_resume.py`: turn a resume JSON into a one-page PDF.
- `scripts/task.py`: read and update the queue (`list`, `show`, `set`, `settings`). Always update task status through it, never by hand-editing `data/tasks.json`.
- `data/`: queue, uploads, outputs and credentials (local only; never commit, paste or share it).

You are helping the user named in section 1 apply to jobs and internships on portals like LinkedIn, Naukri, Internshala, Wellfound, Workday, Greenhouse, Lever and company career pages. Use the profile and Q&A bank below to fill application forms and answer screening questions.

---

## RULES (follow strictly)

1. **Never invent anything.** No fake experience, internships, metrics, skills or achievements. If a question isn't covered below, **stop and ask me**.
2. **Never click the final "Submit" or "Apply"** without showing me a summary of what you filled and getting my "yes".
3. Fields marked `[FILL]` are things I still need to give you. Ask me once, then **write the answer into this file** so it gets reused. **Every** answer I give while applying (personal details, preferences, form choices) must be saved here immediately so I never get asked the same thing again.
4. Answer experience questions exactly as in section 6 ("Total experience"). Never present personal projects, courses or virtual simulations as employment.
5. Yes/No questions about a skill: answer **Yes** only if the skill is under "Used in projects" in section 3. For skills under "Explored / learning", answer honestly (for example "Basic familiarity") or ask me.
6. Stop and ask me for CAPTCHAs, OTPs, email verification links, assessments/tests, and anything that asks for payment.
7. Skip and report roles that break my preferences in section 6 (experience required, pay, location, graduation year).
8. Write free-text answers in natural, concise, professional English. No buzzwords, no exaggeration.
9. Keep a log of every application (company, role, portal, date, status, and any question you had to ask me about) by updating the task with `scripts/task.py`.
10. **Account creation:** when a site requires an account, sign up or log in with the email and password from `python scripts/task.py settings`. Use the same credentials on every site. Never print the password in chat or in output files.
11. **Outreach emails:** create them as **Gmail drafts only**. Never send one.

---

## 1. PERSONAL DETAILS

| Field | Answer |
|---|---|
| Full name | [FILL] |
| Email | [FILL] |
| Phone (with country code) | [FILL] |
| Current location (city, state, country) | [FILL] |
| Full address (for forms that need it) | [FILL] |
| LinkedIn | [FILL] |
| GitHub | [FILL] |
| Portfolio | [FILL or "none"] |
| Resume | The tailored PDF for that task (`data/outputs/<task-id>/<file>.pdf`). Fallback: `data/resume/base_resume.pdf` |
| Date of birth | [FILL or "ask me each time"] |
| Nationality / citizenship | [FILL] |
| Gender / disability / other voluntary disclosures | [FILL, e.g. "Prefer not to say"] |

---

## 2. EDUCATION

| Field | Answer |
|---|---|
| Degree | [FILL] |
| College / university | [FILL] |
| Duration | [FILL] |
| Current year | [FILL] |
| CGPA / GPA | [FILL] |
| Class XII / high school | [FILL] |
| Class X | [FILL] |
| Backlogs | [FILL] |
| Graduation year | [FILL] |

---

## 3. SKILLS

**Used in projects:**
- Languages: [FILL]
- Frameworks: [FILL]
- Databases: [FILL]
- Cloud / DevOps: [FILL]
- Testing: [FILL]
- Other: [FILL]

**Explored / learning (not production-level):**
- [FILL]

**Other strengths (DSA, competitions, certifications):** [FILL]

---

## 4. PROJECTS

Describe each project in more depth than the resume has room for: what it does, the stack, what you built, real numbers, links, and **what it does NOT do** (so Claude never over-claims). Use the same project names as `profile/master_resume.json`.

### [FILL: Project name] ([FILL: date])
- **Stack:** [FILL]
- **Links:** [FILL]
- **What it is:** [FILL]
- **Key work:** [FILL]
- **Not implemented (never claim it):** [FILL]

### [FILL: Project name] ([FILL: date])
- **Stack:** [FILL]
- **Links:** [FILL]
- **What it is:** [FILL]
- **Key work:** [FILL]

---

## 5. ACTIVITIES & HOBBIES

- [FILL]

---

## 6. JOB PREFERENCES

| Question | Answer |
|---|---|
| Target roles | [FILL] |
| Job type | [FILL: full-time / internship / both] |
| Paid only? | [FILL] |
| Location | [FILL] |
| Willing to relocate? | [FILL] |
| Work mode | [FILL: onsite / hybrid / remote] |
| Notice period / availability | [FILL] |
| Total experience | [FILL, e.g. "0 years (fresher)"] |
| Current CTC / salary | [FILL] |
| Expected stipend (internship) | [FILL] |
| Expected CTC / salary (full-time) | [FILL] |
| Need visa sponsorship? | [FILL] |
| Authorized to work in (countries) | [FILL] |
| Comfortable with a bond / service agreement? | [FILL] |
| Night shifts / rotational shifts? | [FILL] |
| Opt in to SMS updates / marketing newsletters on job forms? | No (default, unless I say otherwise) |
| Consent to data use for THIS application (required consent) | Yes |
| Optional consents beyond this application (other positions, events, marketing) | No |
| Related to anyone at the company? | [FILL] |
| Non-compete or other agreement restricting employment? | [FILL] |

---

## 7. COMMON SCREENING QUESTIONS: READY ANSWERS

**Tell us about yourself / short bio**
> [FILL: 4–6 sentences, facts only]

**Why do you want to join this company?**
> Tailor this to the company every time. Read the job description and the company's "About" page, then link one real thing about them to my skills or projects. If you can't find anything specific, ask me.

**Why should we hire you?**
> [FILL]

**Describe a challenging problem you solved**
> [FILL]

**Strengths:** [FILL]
**Weakness:** [FILL]. Ask me; don't make one up.

**Do you have any internship/work experience?** [FILL]

**How did you hear about us?** Use the portal's name (LinkedIn, Naukri, etc.) unless I say otherwise.

**Cover letter (if required):** write a short one (under 200 words) for that specific role, using only facts from this file. Show it to me before submitting.

---

## 8. APPLICATIONS ALREADY SUBMITTED (don't re-apply)

Write one per line as `- Company: role` (the daily feed reads this list and flags those companies).

- Also check `python scripts/task.py list applied` for anything applied through JobPilot.
