"""Excel application tracker: data/Applications.xlsx, rebuilt on every queue change."""
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

LABEL = {
    "pending": "Pending", "in_progress": "In progress", "needs_input": "Needs your input",
    "awaiting_approval": "Awaiting your OK", "applied": "Applied", "drafted": "Email drafted",
    "skipped": "Skipped", "failed": "Failed",
}
FILL = {
    "applied": "D1FADF", "drafted": "D1FADF", "awaiting_approval": "FEF0C7", "needs_input": "FEF0C7",
    "in_progress": "D1E0FF", "skipped": "EAECF0", "failed": "FEE4E2", "pending": "F2F4F7",
}
HEADER_FILL = PatternFill("solid", fgColor="1F2A44")
HEADER_FONT = Font(bold=True, color="FFFFFF")
LINK_FONT = Font(color="2F5BEA", underline="single")


def _sheet(ws, headers, widths, rows):
    ws.append(headers)
    for c in ws[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
        c.alignment = Alignment(vertical="center")
    for row in rows:
        values, links, status = row
        ws.append(values)
        r = ws.max_row
        for col, url in links.items():
            if url:
                cell = ws.cell(row=r, column=col)
                cell.hyperlink, cell.font = url, LINK_FONT
        status_cell = ws.cell(row=r, column=headers.index("Status") + 1)
        status_cell.fill = PatternFill("solid", fgColor=FILL.get(status, "FFFFFF"))
        for c in ws[r]:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions


def _file_url(data_dir, rel):
    return "file:///" + os.path.join(data_dir, rel).replace("\\", "/") if rel else None


def _resume_rel(t):
    return t["outputs"].get("resume")


def build(tasks, data_dir):
    tasks = sorted(tasks, key=lambda t: t["created"])  # oldest first, like a log
    wb = Workbook()

    jobs = [t for t in tasks if t["type"] == "job"]
    ws = wb.active
    ws.title = "Applications"
    _sheet(
        ws,
        ["#", "Added", "Applied On", "Company", "Role", "Portal", "Status", "Job Link",
         "Tailored Resume", "Notes / Reason", "Questions Asked", "Task ID"],
        [5, 17, 17, 22, 28, 16, 18, 14, 16, 40, 40, 10],
        [(
            [i, t["created"], t.get("applied_at", ""), t["company"], t["role"], t["portal"],
             LABEL.get(t["status"], t["status"]), "Open posting" if t.get("url") else "",
             "Open PDF" if _resume_rel(t) else "", t["reason"], "\n".join(t["questions_asked"]), t["id"]],
            {8: t.get("url"), 9: _file_url(data_dir, _resume_rel(t))},
            t["status"],
        ) for i, t in enumerate(jobs, 1)],
    )

    emails = [t for t in tasks if t["type"] == "outreach"]
    ws2 = wb.create_sheet("Cold Emails")
    _sheet(
        ws2,
        ["#", "Added", "Company", "Contact Email", "Role / Context", "Status", "Email Draft",
         "Tailored Resume", "Notes / Reason", "Task ID"],
        [5, 17, 22, 30, 30, 16, 14, 16, 40, 10],
        [(
            [i, t["created"], t["company"], t["contact_email"], t["role"] or t["note"],
             LABEL.get(t["status"], t["status"]), "Open draft" if t["outputs"].get("email") else "",
             "Open PDF" if _resume_rel(t) else "", t["reason"], t["id"]],
            {7: _file_url(data_dir, t["outputs"].get("email")), 8: _file_url(data_dir, _resume_rel(t))},
            t["status"],
        ) for i, t in enumerate(emails, 1)],
    )

    ws3 = wb.create_sheet("Summary")
    ws3.append(["Status", "Applications", "Cold Emails"])
    for c in ws3[1]:
        c.fill, c.font = HEADER_FILL, HEADER_FONT
    for key, label in LABEL.items():
        ws3.append([label, sum(t["status"] == key for t in jobs), sum(t["status"] == key for t in emails)])
    ws3.append(["Total", len(jobs), len(emails)])
    for c in ws3[ws3.max_row]:
        c.font = Font(bold=True)
    for col, w in zip("ABC", (20, 14, 14)):
        ws3.column_dimensions[col].width = w
    return wb


def save(tasks, data_dir, path):
    """Write the tracker. Returns False if the file is locked (open in Excel)."""
    wb = build(tasks, data_dir)
    tmp = path + ".tmp.xlsx"
    wb.save(tmp)
    try:
        os.replace(tmp, path)
        return True
    except PermissionError:
        os.remove(tmp)
        return False
