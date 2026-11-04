"""Build and refresh Rocklin Votes static website for GitHub Pages.
Created: 2026-11-03 (America/Los_Angeles).

The web page only reads latest.json. This GitHub Actions job is the server-side
component: it checks Placer County's currently linked PDF and publishes updated
counts. Failure preserves the last verified public counts and exposes an error.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rocklin_tracker as parser

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "public"
LATEST = ROOT / "latest.json"
HISTORY = ROOT / "history.json"
TZ = ZoneInfo("America/Los_Angeles")
REPORT_PDF = "https://www.placercountyelections.gov/Uploads/documents/11032026/11032026_results.pdf"


def timestamp():
    return datetime.now(TZ).isoformat(timespec="seconds")


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def county_date(text):
    """Parse a printed local date, preserving California local time semantics."""
    if not text:
        return None
    for format_string in ("%A, %B %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(text, format_string).replace(tzinfo=TZ)
        except ValueError:
            pass
    return None


def assert_snapshot(snapshot):
    """Never publish blanks, a zero report, or a different election."""
    assert isinstance(snapshot, dict)
    if snapshot.get("zero_report"):
        raise ValueError("Official page returned a pre-election zero report; keeping verified totals")
    if not county_date(snapshot.get("as_of_county")):
        raise ValueError("County results PDF has an unrecognized report timestamp")
    for key in ("measure_d", "area_2", "area_4", "area_5"):
        r = snapshot.get("contests", {}).get(key)
        if not r or not r.get("present") or not isinstance(r.get("total_votes"), int):
            raise ValueError(f"Missing or unparseable county contest: {key}")
        votes = r.get("choices", {})
        if any(not isinstance(n, int) or n < 0 for n in votes.values()) or not votes:
            raise ValueError(f"Invalid votes for {key}")
        if sum(votes.values()) > r["total_votes"]:
            raise ValueError(f"Votes exceed total reported votes for {key}")
        if r["total_votes"] == 0:
            raise ValueError(f"No votes yet in county PDF for {key}")
    if not snapshot["source_pdf"].startswith("https://www.placercountyelections.gov/"):
        raise ValueError("Unexpected county source URL")


def current_report(session=None):
    session = session or requests.Session()
    session.headers.update({"User-Agent": "RocklinVotesPublicElectionDashboard/1.1 (+noncommercial election tracker)"})
    urls = []
    errors = []
    try:
        urls.append(parser.discover_pdf_url(session=session))
    except (requests.RequestException, RuntimeError) as exc:
        errors.append(f"Results-page discovery: {exc}")
    # Critical fallback: the county has previously linked a zero report on
    # its results page even after publishing actual returns at this stable URL.
    # Prefer its current link but also check the verified election-night PDF.
    if REPORT_PDF not in urls:
        urls.append(REPORT_PDF)
    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.hostname != "www.placercountyelections.gov" or "11032026" not in parsed.path.lower():
                raise ValueError("Unexpected/non-November-2026 official PDF address")
            raw = parser.download_pdf(url, session=session)
            import fitz
            with fitz.open(stream=raw, filetype="pdf") as doc:
                preface = " ".join(doc[i].get_text("text")[:1500] for i in range(min(len(doc), 2)))
            if "2026 General Election" not in preface or "November 3, 2026" not in preface:
                raise ValueError("The PDF does not identify the November 3, 2026 general election")
            snapshot = parser.extract_results_from_pdf(raw, url)
            assert_snapshot(snapshot)
            return snapshot
        except (requests.RequestException, ValueError, RuntimeError, AssertionError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("Could not retrieve and verify an election-night PDF. " + " | ".join(errors)[:950])


def semantic_snapshot(snap):
    return {
        "as_of_county": snap.get("as_of_county"),
        "zero_report": snap.get("zero_report"),
        "contests": snap.get("contests"),
    }


def run(offline=False, fetcher=None):
    baseline = load_json(LATEST)
    if baseline is None:
        raise RuntimeError("latest.json seed is missing; cannot publish unverifiable data")
    assert_snapshot(baseline)
    outcome = {"checked_at": timestamp() if not offline else None, "success": False,
               "error": "Local build only; no county refresh performed." if offline else None,
               "changed": False, "source_pdf": baseline.get("source_pdf")}

    if not offline:
        try:
            incoming = (fetcher or current_report)()
            assert_snapshot(incoming)
            old_date = county_date(baseline.get("as_of_county"))
            new_date = county_date(incoming.get("as_of_county"))
            if old_date and new_date and new_date < old_date:
                raise ValueError("County returned an older report; previous verified counts preserved")
            changed = semantic_snapshot(incoming) != semantic_snapshot(baseline)
            outcome.update(success=True, changed=changed, error=None, source_pdf=incoming["source_pdf"])
            if changed:
                incoming["fetched_at"] = timestamp()
                LATEST.write_text(json.dumps(incoming, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                history = load_json(HISTORY, default=[])
                history.append({"as_of_county": incoming["as_of_county"],
                                "source_pdf": incoming["source_pdf"],
                                "contests": incoming["contests"]})
                write_json(HISTORY, history[-60:])
                baseline = incoming
        except Exception as exc:
            # Preserving verified counts on failures is a deliberate requirement.
            outcome.update(success=False, error=str(exc)[:450], changed=False)
            print("WARNING: county check failed; verified votes preserved:", exc, file=sys.stderr)

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copyfile(ROOT / "index.html", SITE / "index.html")
    shutil.copyfile(LATEST, SITE / "latest.json")
    shutil.copyfile(HISTORY, SITE / "history.json")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    outcome["county_as_of"] = baseline.get("as_of_county")
    write_json(SITE / "status.json", outcome)
    print(json.dumps(outcome, indent=2))
    return outcome


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true", help="Build without checking the county (for tests or offline preview)")
    opts = p.parse_args()
    run(offline=opts.offline)
