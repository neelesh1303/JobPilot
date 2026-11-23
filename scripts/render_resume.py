"""Render a resume JSON (same schema as profile/master_resume.json) to HTML + PDF.

  python scripts/render_resume.py <resume.json> [out.pdf]

Writes <name>.html and <name>.pdf next to the JSON (or to out.pdf).
Exit code 2 = the PDF is longer than one page (trim bullets and re-render).
"""
import json
import os
import subprocess
import sys

from jinja2 import Environment, FileSystemLoader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser():
    for b in BROWSERS:
        if os.path.exists(b):
            return b
    import shutil  # Linux / macOS (GitHub Actions has google-chrome on PATH)
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        if shutil.which(name):
            return shutil.which(name)
    raise SystemExit("No Chrome/Edge found for PDF rendering")


def page_count(pdf):
    try:
        import pypdfium2 as pdfium
        return len(pdfium.PdfDocument(pdf))
    except Exception:
        return None


def render(json_path, pdf_path=None):
    json_path = os.path.abspath(json_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    base = os.path.splitext(json_path)[0]
    html_path = base + ".html"
    pdf_path = os.path.abspath(pdf_path or base + ".pdf")

    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "profile")), autoescape=True)
    html = env.get_template("resume_template.html").render(r=data)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    subprocess.run([
        find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        *([] if sys.platform == "win32" else ["--no-sandbox"]),
        "--print-to-pdf-no-header", f"--print-to-pdf={pdf_path}",
        __import__("pathlib").Path(html_path).as_uri(),
    ], check=True, capture_output=True, timeout=90)
    if not os.path.exists(pdf_path):
        raise SystemExit("PDF was not produced")

    pages = page_count(pdf_path)
    print(json.dumps({"html": html_path, "pdf": pdf_path, "pages": pages}))
    return 2 if pages and pages > 1 else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(render(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
