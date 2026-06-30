#!/usr/bin/env python3
"""
Stage 1 — Ingest
Fetches Samtec product family pages and local source files (PDF/text),
extracts raw text with full source traceability, and writes a JSON file.

Usage:
    python stage1_ingest.py \
        --family "Magnum RF" \
        --urls "https://www.samtec.com/rf/original/magnum/" \
        --files path/to/file.pdf path/to/other.txt \
        --output magnum_rf_sources.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional heavy imports — give clear errors if missing
# ---------------------------------------------------------------------------
try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependency: pip install requests beautifulsoup4")

try:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer
except ImportError:
    sys.exit("Missing dependency: pip install pdfminer.six")


# ---------------------------------------------------------------------------
# Web fetching
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SamtecBrochureTool/1.0; "
        "+https://github.com/rileyopa99-del/samtec-marketing-agent)"
    )
}

# Sub-paths appended to a base product URL to find spec/product-detail pages.
# These are attempted automatically when --crawl is set.
CRAWL_SUFFIXES = [
    "",          # the base URL itself
    "products/", # product listing sub-page
    "specs/",
    "features/",
]


def fetch_url(url: str, timeout: int = 20) -> dict:
    """
    Download a URL and return a source record.
    Returns a dict with keys: url, title, raw_text, error.
    Never raises — errors are captured in the 'error' field.
    """
    record = {
        "source_type": "web",
        "url": url,
        "title": None,
        "raw_text": None,
        "fetch_timestamp": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Title
        title_tag = soup.find("title")
        record["title"] = title_tag.get_text(strip=True) if title_tag else url

        # Remove nav/footer/script/style noise
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Prefer main content blocks; fall back to full body
        content_candidates = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id="content")
            or soup.find(class_="product-detail")
            or soup.find("body")
        )
        record["raw_text"] = content_candidates.get_text(separator="\n", strip=True) if content_candidates else ""
    except Exception as exc:
        record["error"] = str(exc)
        print(f"  [WARN] Could not fetch {url}: {exc}", file=sys.stderr)

    return record


def crawl_product_family(base_url: str) -> list[dict]:
    """
    Fetch the base URL and attempt common sub-paths.
    Deduplicates by final resolved URL (ignores trailing-slash variants).
    """
    seen = set()
    records = []

    urls_to_try = [base_url.rstrip("/") + "/" + suffix for suffix in CRAWL_SUFFIXES]
    # Remove duplicates while preserving order
    urls_to_try = list(dict.fromkeys(urls_to_try))

    for url in urls_to_try:
        normalized = url.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        print(f"  Fetching: {url}")
        rec = fetch_url(url)
        if rec["error"] is None and rec["raw_text"]:
            records.append(rec)
        time.sleep(0.5)  # polite crawl rate

    return records


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def extract_pdf(file_path: str) -> dict:
    """
    Extract all text from a PDF using pdfminer.six with page-level traceability.
    """
    path = Path(file_path)
    record = {
        "source_type": "pdf",
        "file_path": str(path.resolve()),
        "file_name": path.name,
        "title": path.stem,
        "pages": [],
        "raw_text": None,
        "error": None,
    }

    if not path.exists():
        record["error"] = f"File not found: {file_path}"
        print(f"  [WARN] {record['error']}", file=sys.stderr)
        return record

    try:
        full_text_parts = []
        for page_num, page_layout in enumerate(extract_pages(path), start=1):
            page_text_parts = []
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    page_text_parts.append(element.get_text())
            page_text = "".join(page_text_parts).strip()
            record["pages"].append({"page_number": page_num, "text": page_text})
            if page_text:
                full_text_parts.append(f"[Page {page_num}]\n{page_text}")

        record["raw_text"] = "\n\n".join(full_text_parts)
        total = len(record["pages"])
        print(f"  Read PDF ({total} pages): {path.name}")
    except Exception as exc:
        record["error"] = str(exc)
        print(f"  [WARN] Could not read PDF {file_path}: {exc}", file=sys.stderr)

    return record


# ---------------------------------------------------------------------------
# Plain text / other file extraction
# ---------------------------------------------------------------------------

def extract_text_file(file_path: str) -> dict:
    path = Path(file_path)
    record = {
        "source_type": "text_file",
        "file_path": str(path.resolve()),
        "file_name": path.name,
        "title": path.stem,
        "raw_text": None,
        "error": None,
    }

    if not path.exists():
        record["error"] = f"File not found: {file_path}"
        print(f"  [WARN] {record['error']}", file=sys.stderr)
        return record

    try:
        record["raw_text"] = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Read text file: {path.name}")
    except Exception as exc:
        record["error"] = str(exc)
        print(f"  [WARN] Could not read {file_path}: {exc}", file=sys.stderr)

    return record


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def ingest_file(file_path: str) -> dict:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(file_path)
    else:
        return extract_text_file(file_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stage 1: Ingest Samtec product sources into a traceable JSON file."
    )
    parser.add_argument("--family", required=True, help='Product family name, e.g. "Magnum RF"')
    parser.add_argument(
        "--urls",
        nargs="+",
        default=[],
        help="One or more Samtec product page URLs to fetch",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Local file paths (PDF or .txt) to include as sources",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path (default: <family_snake_case>_sources.json)",
    )
    parser.add_argument(
        "--no-crawl",
        action="store_true",
        help="Disable automatic crawling of sub-paths; fetch only the exact URLs provided",
    )
    args = parser.parse_args()

    family_slug = args.family.lower().replace(" ", "_")
    output_path = args.output or f"{family_slug}_sources.json"

    print(f"\n=== Stage 1: Ingest — {args.family} ===\n")

    sources = []

    # --- Web sources ---
    if args.urls:
        print(f"[WEB] Fetching {len(args.urls)} URL(s)...")
        for url in args.urls:
            if args.no_crawl:
                rec = fetch_url(url)
                if rec["error"] is None:
                    sources.append(rec)
            else:
                records = crawl_product_family(url)
                sources.extend(records)
    else:
        print("[WEB] No URLs provided — skipping web fetch.")

    # --- Local file sources ---
    if args.files:
        print(f"\n[FILES] Processing {len(args.files)} local file(s)...")
        for fpath in args.files:
            rec = ingest_file(fpath)
            sources.append(rec)
    else:
        print("[FILES] No local files provided.")

    # --- Validate we got something ---
    successful = [s for s in sources if not s.get("error")]
    failed = [s for s in sources if s.get("error")]

    print(f"\n[SUMMARY]")
    print(f"  Sources ingested successfully : {len(successful)}")
    print(f"  Sources with errors           : {len(failed)}")
    if failed:
        for f in failed:
            label = f.get("url") or f.get("file_path") or "unknown"
            print(f"    FAILED: {label} — {f['error']}")

    if not successful:
        print("\n[ERROR] No sources were successfully ingested. Cannot write output.", file=sys.stderr)
        sys.exit(1)

    # --- Build output document ---
    output_doc = {
        "product_family": args.family,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": "1.0",
        "sources_count": len(successful),
        "sources": sources,
        "ingestion_notes": (
            "Each source record contains raw extracted text only. "
            "No summarization or inference has been applied. "
            "All claims in downstream stages must trace back to a source record here."
        ),
    }

    out = Path(output_path)
    out.write_text(json.dumps(output_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OUTPUT] Written to: {out.resolve()}")
    print(f"  Total source records : {len(sources)}")
    print(f"  Successful           : {len(successful)}")
    print(f"  Failed               : {len(failed)}")
    print("\nStage 1 complete. Run Stage 2 to extract the knowledge object.\n")


if __name__ == "__main__":
    main()
