"""Rocklin Unified election-results monitor.
Created: 2026-11-03 (America/Los_Angeles)

Fetches Placer County's public results PDF and extracts four tracked contests (three school board races and Measure D).
Does not guess missing vote counts, infer certifications, or scrape unofficial feeds.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from zoneinfo import ZoneInfo

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
HISTORY_FILE = DATA_DIR / "snapshots.jsonl"
LATEST_FILE = DATA_DIR / "latest.json"
RESULTS_PAGE = "https://www.placercountyelections.gov/election-results/"
MEASURE_INFO_URL = "https://www.placercountyelections.gov/Uploads/documents/11032026/measures/11032026_Measure-D.pdf"
ZERO_PDF_URL = "https://www.placercountyelections.gov/Uploads/documents/11032026/11032026_Zero_Report_V2.pdf"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")

CONTESTS = {
    "measure_d": {
        "title": "Measure D · RUSD school bond",
        "kind": "measure",
        "pattern": r"\bMEASURE\s+D\b",
        "choices": ["YES", "NO"],
        "expected_precincts": 28,
    },
    "area_2": {
        "title": "School Board · Trustee Area 2",
        "kind": "trustee",
        "pattern": r"ROCKLIN\s+UNIFIED\s+SCHOOL\s+DISTRICT\s+GOVERNING\s+BOARD\s+MEMBER\s+TRUSTEE\s+AREA\s*2\b",
        "choices": ["TIFFANY SAATHOFF", "MICHELLE SUTHERLAND"],
        "expected_precincts": 8,
    },
    "area_4": {
        "title": "School Board · Trustee Area 4",
        "kind": "trustee",
        "pattern": r"ROCKLIN\s+UNIFIED\s+SCHOOL\s+DISTRICT\s+GOVERNING\s+BOARD\s+MEMBER\s+TRUSTEE\s+AREA\s*4\b",
        "choices": ["REBECCA HOEHNE", "STEVE MAKIS"],
        "expected_precincts": 4,
    },
    "area_5": {
        "title": "School Board · Trustee Area 5",
        "kind": "trustee",
        "pattern": r"ROCKLIN\s+UNIFIED\s+SCHOOL\s+DISTRICT\s+GOVERNING\s+BOARD\s+MEMBER\s+TRUSTEE\s+AREA\s*5\b",
        "choices": ["DERECK COUNTER", "JACOB BOYCE"],
        "expected_precincts": 5,
    },

}


def pacific_now():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def _unique(items):
    return list(dict.fromkeys(items))


def _pdf_links_from_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for tag in soup.find_all(["a", "iframe", "embed", "object"]):
        link = tag.get("href") or tag.get("src") or tag.get("data")
        if not link:
            continue
        target = urljoin(page_url, link)
        if ".pdf" in unquote(target).lower():
            urls.append(target)
    # Also support URLs appearing in HTML scripts or inline PDF viewers.
    for match in re.findall(r"(?:https?://|/)[^\s\"'<>]+?\.pdf(?:\?[^\s\"'<>]*)?", html, flags=re.I):
        urls.append(urljoin(page_url, match.replace("&amp;", "&")))
    # Only trust URLs that appear on the county's official results page.
    urls = [u for u in _unique(urls) if urlparse(u).scheme == "https"]
    def score(u):
        s = u.lower()
        return (
            (20 if "11032026" in s else 0)
            + (10 if "summary" in s or "results" in s else 0)
            + (4 if "report" in s else 0)
            - (35 if "zero" in s else 0)
            - (30 if "measure-d" in s else 0)
        )
    return sorted(urls, key=score, reverse=True)


def discover_pdf_url(session=None, override=None):
    """Find current results PDF. Override a direct URL if county changes page format."""
    if override:
        if urlparse(override).scheme != "https":
            raise ValueError("Custom PDF URL must start with https://")
        return override
    session = session or requests.Session()
    resp = session.get(RESULTS_PAGE, timeout=25, params={"_rocklin_refresh": str(time.time_ns())},
                       headers={"Cache-Control": "no-cache, no-store, max-age=0", "Pragma": "no-cache"})
    resp.raise_for_status()
    candidates = _pdf_links_from_html(resp.text, resp.url)
    # The current public page links to a zero report; don't silently use a stale
    # hardcoded fallback if that link disappears or the page changes entirely.
    if not candidates:
        raise RuntimeError("No PDF was discoverable on the county results page. Paste the current PDF URL in the dashboard sidebar, or upload the county's PDF manually.")
    return candidates[0]


def download_pdf(url, session=None):
    session = session or requests.Session()
    response = session.get(url, timeout=40, params={"_rocklin_refresh": str(time.time_ns())},
                           headers={"Cache-Control": "no-cache, no-store, max-age=0", "Pragma":"no-cache", "Accept": "application/pdf,*/*"})
    response.raise_for_status()
    data = response.content
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"The results link did not return a PDF ({response.headers.get('Content-Type', 'unknown type')}).")
    if len(data) > 30_000_000:
        raise ValueError("Results PDF unexpectedly exceeds 30 MB")
    return data


def _compact(value):
    return " ".join(value.split())


def _get_votes(block, name):
    name_pattern = r"\s+".join(re.escape(part) for part in name.split())
    # PDF readers may put line breaks or tabs between the row label and its two numeric cells.
    pat = rf"Votes\s+cast\s+for\s+(?:[A-Z]{{2,4}}\s*-\s*)?{name_pattern}\s+([\d,]+)(?:\s+\d+(?:\.\d+)?\s*%)?"
    match = re.search(pat, block, flags=re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else None


def extract_results_from_text(text, source_url="file://uploaded-report.pdf"):
    """Parse OCR-free, selectable text from the official WCAG summary PDF.

    `None` signifies missing/unparseable votes; 0 means an actual printed zero.
    """
    flat = _compact(text)
    zero_report = bool(re.search(r"\bZERO\s+REPORT\b", flat, re.I))
    refreshed_match = re.search(
        r"Data\s+Refreshed\s*:\s*([^\n\r]+)", text, re.I
    )
    county_timestamp = refreshed_match.group(1).strip() if refreshed_match else None

    contests = {}
    for key, definition in CONTESTS.items():
        heading = re.search(definition["pattern"], flat, re.I)
        if not heading:
            contests[key] = {"title": definition["title"], "kind": definition["kind"],
                             "present": False, "choices": {c: None for c in definition["choices"]},
                             "precincts_reported": None, "precincts_total": None, "total_votes": None}
            continue
        after_heading = flat[heading.end():]
        total_match = re.search(r"Total\s+Votes\s*:\s*([\d,]+)", after_heading, re.I)
        # Fixed-size cap prevents the parser from reaching another contest when the
        # requested contest is malformed. Failure is surfaced, never filled with zeros.
        region = after_heading[:min(2000, total_match.end() if total_match else 1100)]
        precincts = re.search(r"X\s+of\s+Y\s*:\s*([\d,]+)\s+of\s+([\d,]+)\s+precincts\s+reported", region, re.I)
        votes = {c: _get_votes(region, c) for c in definition["choices"]}
        reported = int(precincts.group(1).replace(",", "")) if precincts else None
        precinct_total = int(precincts.group(2).replace(",", "")) if precincts else None
        total = int(total_match.group(1).replace(",", "")) if total_match else None
        contests[key] = {
            "title": definition["title"],
            "kind": definition["kind"],
            "present": True,
            "choices": votes,
            "precincts_reported": reported,
            "precincts_total": precinct_total,
            "total_votes": total,
        }

    return {"as_of_county": county_timestamp, "zero_report": zero_report,
            "source_pdf": source_url, "contests": contests}


def extract_results_from_pdf(pdf_bytes, source_url):
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            text = "\n".join(page.get_text("text", sort=True) for page in doc)
    except Exception as exc:
        raise ValueError(f"Could not read the PDF: {exc}") from exc
    if not text.strip():
        raise ValueError("PDF has no selectable text. An image-only report cannot be read automatically.")
    results = extract_results_from_text(text, source_url)
    missing = []
    for key, c in results['contests'].items():
        if not c['present'] or c['total_votes'] is None or any(v is None for v in c['choices'].values()):
            missing.append(key)
        elif sum(c['choices'].values()) > c['total_votes']:
            missing.append(key + ' (vote total mismatch)')
    if missing:
        raise ValueError('The county PDF could not be completely parsed for: ' + ', '.join(missing)
                         + '. Previous verified results were preserved.')
    return results


def fingerprint(snapshot):
    relevant = {"as_of_county": snapshot.get("as_of_county"),
                "zero_report": snapshot.get("zero_report"), "contests": snapshot["contests"]}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()


def save_snapshot(snapshot):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    previous = read_latest()
    changed = previous is None or fingerprint(previous) != fingerprint(snapshot)
    snapshot = {**snapshot, "fetched_at": pacific_now()}
    # Save latest even if unchanged to keep the last successful check timestamp.
    temp = LATEST_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    temp.replace(LATEST_FILE)
    if changed:
        with HISTORY_FILE.open("a", encoding="utf-8") as out:
            out.write(json.dumps(snapshot, separators=(",", ":")) + "\n")
    return changed


def read_latest():
    if not LATEST_FILE.exists():
        return None
    try:
        return json.loads(LATEST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_history():
    if not HISTORY_FILE.exists():
        return []
    rows = []
    with HISTORY_FILE.open(encoding="utf-8") as file:
        for line in file:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def history_csv():
    output = io.StringIO()
    fields = ["fetched_at", "county_timestamp", "contest", "option", "votes", "precincts_reported", "precincts_total", "zero_report", "source_pdf"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in read_history():
        for key, contest in row.get("contests", {}).items():
            for option, count in contest["choices"].items():
                writer.writerow({"fetched_at": row["fetched_at"], "county_timestamp": row.get("as_of_county"),
                                 "contest": key, "option": option, "votes": count,
                                 "precincts_reported": contest["precincts_reported"],
                                 "precincts_total": contest["precincts_total"],
                                 "zero_report": row.get("zero_report"), "source_pdf": row.get("source_pdf")})
    return output.getvalue()


def poll_once(pdf_url=None, file_bytes=None):
    """Return (snapshot, changed) and record a new history row if the source changed."""
    if file_bytes is not None:
        src = "Uploaded county results PDF"
        pdf = file_bytes
    else:
        session = requests.Session()
        session.headers.update({"User-Agent": "RocklinElectionTracker/1.0 (public results dashboard)"})
        src = discover_pdf_url(session, override=pdf_url)
        pdf = download_pdf(src, session)
    snapshot = extract_results_from_pdf(pdf, src)
    previous = read_latest()
    # Never overwrite real counted votes with a pre-election placeholder PDF.
    if snapshot.get("zero_report") and previous and any(
        (c.get("total_votes") or 0) > 0 for c in previous.get("contests", {}).values()
    ):
        raise RuntimeError("The county page pointed to its old zero report. Existing counted votes are preserved. Download the current results PDF from the county page and import it in the dashboard.")
    changed = save_snapshot(snapshot)
    snapshot["fetched_at"] = read_latest()["fetched_at"]
    return snapshot, changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="Monitor county-published Rocklin election results")
    ap.add_argument("--once", action="store_true", help="Fetch once (default)")
    ap.add_argument("--watch", action="store_true", help="Keep monitoring in this terminal until Ctrl+C")
    ap.add_argument("--minutes", type=int, default=3, help="Polling interval in minutes when watching (default 3)")
    ap.add_argument("--pdf-url", help="Override auto-discovery with a direct https PDF URL")
    ap.add_argument("--pdf-file", help="Import locally downloaded county results PDF")
    args = ap.parse_args(argv)
    if args.minutes < 1:
        ap.error("--minutes must be 1 or greater")
    print("Rocklin Unified election monitor | November 3, 2026 | Placer County")
    print(f"Writing snapshots to: {HISTORY_FILE}")
    while True:
        try:
            data = Path(args.pdf_file).read_bytes() if args.pdf_file else None
            snapshot, changed = poll_once(pdf_url=args.pdf_url, file_bytes=data)
            status = "pre-election zero report" if snapshot["zero_report"] else "results PDF"
            print(f"[{snapshot['fetched_at']}] {status} | {'UPDATED' if changed else 'unchanged'} | county timestamp: {snapshot.get('as_of_county') or 'not supplied'}", flush=True)
            for key, contest in snapshot["contests"].items():
                counts = ", ".join(f"{name}: {votes if votes is not None else '?'}" for name, votes in contest["choices"].items())
                print(f"  {contest['title']}: {counts}")
        except (requests.RequestException, ValueError, RuntimeError, OSError) as exc:
            print(f"[{pacific_now()}] Update failed: {exc}. Keeping last verified snapshot.", file=sys.stderr, flush=True)
        if not args.watch:
            return
        try:
            time.sleep(args.minutes * 60)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            return


if __name__ == "__main__":
    main()
