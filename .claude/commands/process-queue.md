---
description: Process the JobPilot queue: tailor resumes and apply to job links, draft outreach emails from screenshots
argument-hint: "[task-id]  (optional: process only this task)"
---

Process the JobPilot queue. Follow every rule in CLAUDE.md. Today's date matters for the log; use the system date.

## 0. Setup
1. Run `python scripts/task.py list pending` (or `show $ARGUMENTS` if a task id was given). If nothing is pending, also check `needs_input` and `awaiting_approval` tasks and offer to resume them. If there's still nothing, say so and stop.
2. Run `python scripts/task.py settings`. If `account_email` or `account_password` is empty, ask the user to set them under **Profile** in the UI before doing any sign-ups. If `resume_needs_sync` is true, the user uploaded a new resume: read `data/resume/base_resume.pdf`, update `profile/master_resume.json` so it matches the PDF exactly (keep the schema; use `<b>` for bold), tell the user what changed, then run `python scripts/task.py synced`.
3. Load the Chrome tools in one ToolSearch call (tabs_context_mcp, tabs_create_mcp, navigate, get_page_text, read_page, find, form_input, computer, file_upload, javascript_tool). Call tabs_context_mcp first and work in a new tab.
4. Work through tasks one at a time, oldest first. Before starting each one: `python scripts/task.py set <id> status=in_progress`.

All outputs for a task go in `data/outputs/<id>/`. Paths given to `output.<name>=` are relative to `data/` (for example `outputs/<id>/resume.pdf`).

---

## A. Job link (type = "job")

**1. Scan the posting.** Open the URL and read the full job description (expand "show more" if needed). Save a clean copy to `data/outputs/<id>/jd.md`: company, role, location, work mode, job type, stipend/salary, experience required, batch/graduation-year requirements, deadline, responsibilities, requirements. Then record it:
`python scripts/task.py set <id> company="..." role="..." portal="..." output.jd=outputs/<id>/jd.md`

**2. Check eligibility** against CLAUDE.md sections 6 and 8 and the applied tasks. Skip if the role breaks the preferences in section 6 (experience required, pay, location, graduation year) or is a duplicate:
`python scripts/task.py set <id> status=skipped reason="<short reason>"`, then move on. If paid status or experience is unclear, it's fine to continue, but mention it in the summary.

**Tasks from the job feed** have a `lead_id` and usually an `outputs.feed_resume` PDF that the daily feed already tailored (it only reorders and bolds master-resume content). Use it as your starting point: if it already fits the JD well, you may reuse it (copy and rename it per step 3) instead of re-tailoring from scratch. The lead's HR emails and alumni are in MongoDB: `python -c "from jobbot import leads; import json; print(json.dumps(leads.get('<lead_id>'), default=str, indent=1))"`. After a successful submit, if the lead has an HR email, offer to create a short follow-up **Gmail draft** to it (section B.5 rules; never send).

**3. Tailor the resume.** Copy `profile/master_resume.json` to `data/outputs/<id>/resume.json` and tailor it to the JD:
- Reorder projects so the most relevant one comes first. Reorder bullets within a project and items within each skill line so the JD's keywords come first.
- Bold (`<b>`) the terms that match the JD. You may lightly reword a bullet to use the JD's terminology **only when it describes the same fact** (for example "REST API" for a bullet describing HTTP endpoints).
- You may set `summary` to 1–2 lines aimed at the role, built only from facts in CLAUDE.md.
- You may swap a less relevant project for one from `extra_projects` (move it into `projects`) when it fits the role better. Keep the same number of projects. Only `projects` is rendered.
- You may drop a weak bullet to keep it to one page. Never add a skill, metric, project or claim that isn't in `master_resume.json` or CLAUDE.md. Skills listed as "Explored / learning" must not appear in the resume.
- Render with `python scripts/render_resume.py data/outputs/<id>/resume.json`. Exit code 2 means it's over one page: trim and re-render.
- Rename the PDF to `<Your_Name>_Resume_<Company>.pdf` (the `name` in `master_resume.json`, spaces as underscores) in the same folder, then record it: `output.resume=outputs/<id>/<that file name>`.
- Write `data/outputs/<id>/tailoring.md`: 3–5 lines on what you changed and why.

**4. Apply.**
- Click Apply. If the posting redirects to an external ATS (Workday, Greenhouse, Lever and so on), follow it and set `portal`.
- **Account needed:** sign up (or log in if the account already exists) using `account_email` / `account_password` from settings. Use the name and phone from CLAUDE.md. If a "forgot password" or a different existing password blocks you, ask the user.
- **OTP, email-verification link, CAPTCHA, or "sign in with Google/LinkedIn" only:** set `status=needs_input reason="<what you need>"`, tell the user exactly what to do, and wait. If they don't respond, move on to the next task. For an email verification link you may search Gmail for it with the Gmail tools (search only, never send), but ask before clicking it.
- Upload the tailored PDF with `file_upload`, using the absolute path.
- Fill every field from CLAUDE.md. For screening questions, use section 7, tailored to this company. For "Why this company", read the company's About/Careers page and connect one real, specific thing to a real project.
- Any question not covered by CLAUDE.md: ask the user and record it (`question="<the question>"`). Once answered, add the answer to CLAUDE.md if it's reusable.
- Save every free-text answer and the cover letter (if any) to `data/outputs/<id>/answers.md` and record it with `output.answers=outputs/<id>/answers.md`.

**5. Approval gate (mandatory).** Stop **before** the final Submit/Apply click. Set `status=awaiting_approval`, then show the user:
- Company, role, link, portal, and the account used (email only)
- Eligibility notes (paid? location? experience?)
- What you tailored in the resume
- Every free-text answer, in full

Ask: "Submit this application? (yes / edit / skip)".
- **yes:** click Submit, confirm the success screen (take a screenshot if useful), then `status=applied --msg "submitted"`.
- **edit:** make the changes and show the summary again.
- **skip:** `status=skipped reason="user declined"`.

---

## B. Recruiter screenshot (type = "outreach")

**1. Read the screenshot** at `data/<screenshot>` with the Read tool, along with the user's `note`. Extract the recipient's email (and name or title if visible), the company, the role or hiring context, and any instructions in the post (subject line format, what to attach, and so on). Record with `contact_email=... company=... role=...`. If no email is visible or it's ambiguous, set `needs_input` and ask.

**2. Research the company (5–10 minutes, no more).** Use WebSearch and fetch the company site or blog for: what they build, their tech stack, a recent launch, a blog post, funding or a specific engineering challenge. Keep 2–3 concrete, verifiable facts with their sources in `data/outputs/<id>/research.md`. Never fabricate a fact. If you can't find anything specific, say so and keep the email general.

**3. Pick the best-aligned project** from CLAUDE.md §4 by matching it to what the company does (for example, an AI product → your most relevant AI project; a consumer platform → your project with auth, caching and scale work).

**4. Tailor a resume** exactly as in A.3, aimed at the role or company.

**5. Draft the email** and save it to `data/outputs/<id>/email.md` (`output.email=...`):
- Subject: specific and short, for example `Backend Intern application – <Your Name> (<College> '<year>)`, or the format the post asks for.
- Body under 170 words, addressed by name if known:
  1. One line on who I am (degree, college, graduation year, grade from CLAUDE.md §2).
  2. "I saw that <company> <specific researched thing>…", then how my <project> relates to it (one or two concrete facts from that project), and what I could help them with.
  3. One line of proof: the most relevant concrete number or result from CLAUDE.md (a project metric, DSA count, a ranking).
  4. Links: GitHub, portfolio, live demo if relevant. Say the resume is attached. Close with a polite, low-pressure ask (a short call, or to be considered for the role).
  - Plain, natural English: no "I am thrilled", no buzzwords, no exaggeration.
- Create a **Gmail draft** with the Gmail `create_draft` tool, addressed to the contact. If the tool can attach files, attach the tailored PDF; if not, tell the user to attach `data/outputs/<id>/<pdf>` before sending. **Never send.**
- `status=drafted --msg "gmail draft created"`, then show the user the email, the research facts it's based on, and the resume path.

---

## 6. Wrap-up
After the last task, print a short table: id, type, company, role, final status, and anything waiting on the user (OTPs, approvals, `[FILL]` questions). Remind the user that results and files are visible in the JobPilot UI.
