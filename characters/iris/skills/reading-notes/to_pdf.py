"""Print an HTML file to PDF with a headless Chromium browser (Edge / Chrome / Chromium).

Usage: python to_pdf.py <input.html> <output.pdf>
Only uses the standard library.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
NAMES = ["msedge", "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge"]


def find_browser():
    for c in CANDIDATES:
        if c and Path(c).is_file():
            return c
    for n in NAMES:
        p = shutil.which(n)
        if p:
            return p
    return None


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python to_pdf.py <input.html> <output.pdf>")
    src = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    browser = find_browser()
    if not browser:
        sys.exit("未找到 Edge / Chrome / Chromium，无法生成 PDF")
    out.parent.mkdir(parents=True, exist_ok=True)
    args = [browser, "--headless", "--disable-gpu", "--no-pdf-header-footer"]
    # Inside the DeepSeek Harness sandbox the default browser profile isn't
    # writable and Chromium can't nest its own sandbox on Linux.
    if os.environ.get("LIVING_ROOM_HARNESS") == "deepseek" and sys.platform.startswith("linux"):
        args.append("--no-sandbox")
    # A throwaway profile next to the output (always writable) instead of the user's.
    with tempfile.TemporaryDirectory(prefix=".pdf-profile-", dir=out.parent, ignore_cleanup_errors=True) as prof:
        subprocess.run(
            args + [f"--user-data-dir={prof}", f"--print-to-pdf={out}", src.as_uri()],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
        )
    if not out.is_file() or out.stat().st_size == 0:
        sys.exit("PDF 生成失败")
    print(out)


if __name__ == "__main__":
    main()
