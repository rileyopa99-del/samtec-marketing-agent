#!/usr/bin/env python3
"""
Stage 2 — Structure
Reads the raw sources JSON from Stage 1 and extracts a canonical knowledge
object. Every extracted fact must carry a direct citation (source file + page).
Nothing is inferred or synthesized — if a field cannot be populated from
explicit source text, it is left empty and added to `gaps`.

Usage:
    python stage2_structure.py \
        --input magnum_rf_sources.json \
        --output magnum_rf_knowledge.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Citation helpers
# ---------------------------------------------------------------------------

def cite(source: dict, page_number: int | None = None) -> str:
    """Build a short human-readable citation string."""
    if source["source_type"] == "pdf":
        base = source["file_name"]
        return f"{base}, p.{page_number}" if page_number else base
    else:
        return source.get("title") or source.get("url") or "web source"


def page_cite(source: dict, page: dict) -> str:
    return cite(source, page.get("page_number"))


# ---------------------------------------------------------------------------
# Pattern-based extractors
# ---------------------------------------------------------------------------

# Each pattern returns a list of {"value": str, "citation": str, "excerpt": str}

# --- Frequency / performance specs ---
FREQ_PATTERNS = [
    # "up to 65 GHz", "to 67 GHz", "65GHz"
    r"(?:up to |to |through |DC to )?(\d+(?:\.\d+)?)\s*GHz\b[^.\n]{0,120}",
    r"mode.free operation up to (\d+(?:\.\d+)?)\s*GHz[^.\n]{0,80}",
]

# --- Impedance ---
IMPEDANCE_PATTERNS = [
    r"(\d+)\s*[Oo]hm[^.\n]{0,80}",
    r"(\d+)Ω[^.\n]{0,80}",
]

# --- VSWR ---
VSWR_PATTERNS = [
    r"VSWR[^.\n]{0,60}",
]

# --- Insertion loss ---
IL_PATTERNS = [
    r"[Ii]nsertion [Ll]oss[^.\n]{0,80}",
]

# --- Return loss ---
RL_PATTERNS = [
    r"[Rr]eturn [Ll]oss[^.\n]{0,80}",
]

# --- Operating temperature ---
TEMP_PATTERNS = [
    r"(?:operating |storage )?temperature[^.\n]{0,80}[-–]\s*\d+\s*°?C[^.\n]{0,40}",
    r"-\d+\s*°?C\s*to\s*[+]?\d+\s*°?C",
]

# --- Mating cycles ---
MATING_PATTERNS = [
    r"\d+[\,\d]*\s*(?:mating cycles?|mate[s]?|unmating)[^.\n]{0,60}",
]

# --- IP rating / ingress ---
IP_PATTERNS = [
    r"IP\d+[^.\n]{0,60}",
]

# --- Connector interface type ---
INTERFACE_PATTERNS = [
    r"SMPM[^.\n]{0,100}",
    r"SMP[^.\n]{0,100}",
    r"2\.92[^.\n]{0,80}",
    r"2\.4\s*mm[^.\n]{0,80}",
]

# --- Applications (must be explicitly stated) ---
APP_PATTERNS = [
    r"(?:ideal for|designed for|applications?(?:\s+include)?|used in|suitable for)[^.\n]{0,200}",
    r"(?:5G|6G|radar|defense|military|test\s*&?\s*measurement|aerospace|satellite|mmWave)[^.\n]{0,120}",
]

# --- Differentiators (explicit marketing language) ---
DIFF_PATTERNS = [
    r"(?:advantage|benefit|key feature|differentiator|only\s+\w+\s+that|unlike|first\s+to)[^.\n]{0,200}",
    r"(?:blind.?mate|gang(?:ed)?|multi.?port)[^.\n]{0,120}",
    r"(?:high.?density|micro.?miniature|ultra.?small)[^.\n]{0,120}",
    r"(?:IP67|IP68|IP6[0-9])[^.\n]{0,120}",
    r"(?:push.?on|snap.?on)[^.\n]{0,80}",
]

# --- Part numbers / series ---
PART_PATTERNS = [
    r"\bMRF[A-Z0-9\-]+\b",
    r"\bMRF\d[^,\s]{1,20}",
    r"(?:series|family|product)[:\s]+([A-Z]{2,8}-[A-Z0-9\-]+)",
]

# --- Mating / compatible parts ---
MATING_PART_PATTERNS = [
    r"(?:mates? with|compatible with|mating connector|mating part)[^.\n]{0,120}",
    r"SMPM[^.\n]{0,80}",
    r"MRF[A-Z0-9\-]*[^.\n]{0,80}",
]


def extract_matches(pattern_list: list[str], text: str, source: dict,
                    page_number: int | None = None, flags=re.IGNORECASE) -> list[dict]:
    results = []
    seen_excerpts = set()
    for pat in pattern_list:
        for m in re.finditer(pat, text, flags):
            excerpt = m.group(0).strip()
            # Normalise whitespace
            excerpt = re.sub(r"\s+", " ", excerpt)
            if excerpt in seen_excerpts or len(excerpt) < 5:
                continue
            seen_excerpts.add(excerpt)
            results.append({
                "excerpt": excerpt,
                "citation": page_cite(source, {"page_number": page_number}) if page_number else cite(source),
            })
    return results


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove near-duplicate excerpts (same first 60 chars)."""
    seen = set()
    out = []
    for item in items:
        key = item["excerpt"][:60].lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Per-source extraction
# ---------------------------------------------------------------------------

def extract_from_source(source: dict) -> dict:
    """
    Run all extractors over a single source record.
    Returns dict keyed by category, each value is a list of match dicts.
    """
    buckets: dict[str, list] = {
        "frequency": [],
        "impedance": [],
        "vswr": [],
        "insertion_loss": [],
        "return_loss": [],
        "temperature": [],
        "mating_cycles": [],
        "ip_rating": [],
        "interfaces": [],
        "applications": [],
        "differentiators": [],
        "mating_parts": [],
    }

    pages = source.get("pages") or []

    if pages:
        for page in pages:
            pnum = page["page_number"]
            text = page.get("text") or ""
            if not text.strip():
                continue

            def ex(patterns, bucket):
                buckets[bucket].extend(
                    extract_matches(patterns, text, source, pnum)
                )

            ex(FREQ_PATTERNS, "frequency")
            ex(IMPEDANCE_PATTERNS, "impedance")
            ex(VSWR_PATTERNS, "vswr")
            ex(IL_PATTERNS, "insertion_loss")
            ex(RL_PATTERNS, "return_loss")
            ex(TEMP_PATTERNS, "temperature")
            ex(MATING_PATTERNS, "mating_cycles")
            ex(IP_PATTERNS, "ip_rating")
            ex(INTERFACE_PATTERNS, "interfaces")
            ex(APP_PATTERNS, "applications")
            ex(DIFF_PATTERNS, "differentiators")
            ex(MATING_PART_PATTERNS, "mating_parts")
    else:
        # Web source — treat as one block
        text = source.get("raw_text") or ""

        def ex(patterns, bucket):
            buckets[bucket].extend(extract_matches(patterns, text, source))

        ex(FREQ_PATTERNS, "frequency")
        ex(IMPEDANCE_PATTERNS, "impedance")
        ex(VSWR_PATTERNS, "vswr")
        ex(IL_PATTERNS, "insertion_loss")
        ex(RL_PATTERNS, "return_loss")
        ex(TEMP_PATTERNS, "temperature")
        ex(MATING_PATTERNS, "mating_cycles")
        ex(IP_PATTERNS, "ip_rating")
        ex(INTERFACE_PATTERNS, "interfaces")
        ex(APP_PATTERNS, "applications")
        ex(DIFF_PATTERNS, "differentiators")
        ex(MATING_PART_PATTERNS, "mating_parts")

    return buckets


# ---------------------------------------------------------------------------
# Merge & deduplicate across sources
# ---------------------------------------------------------------------------

def merge_buckets(all_buckets: list[dict]) -> dict:
    merged: dict[str, list] = {}
    for buckets in all_buckets:
        for key, items in buckets.items():
            merged.setdefault(key, []).extend(items)
    # Dedup each category
    return {k: deduplicate(v) for k, v in merged.items()}


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "frequency":       "Frequency range / max operating frequency",
    "impedance":       "Characteristic impedance (e.g. 50 Ω)",
    "vswr":            "VSWR specification",
    "insertion_loss":  "Insertion loss specification",
    "return_loss":     "Return loss specification",
    "temperature":     "Operating temperature range",
    "mating_cycles":   "Mating cycle rating",
    "ip_rating":       "IP ingress protection rating",
    "interfaces":      "Connector interface type(s)",
    "applications":    "Target applications (explicitly stated)",
    "differentiators": "Product differentiators / key advantages",
    "mating_parts":    "Compatible / mating connector part numbers",
}

BROCHURE_GAPS = [
    ("pricing",       "Pricing and lead time — not found in any source material"),
    ("stock",         "Inventory / stock availability — not found in any source material"),
    ("case_studies",  "Customer case studies or reference designs — not found in any source material"),
    ("certifications","Certifications (MIL-SPEC, RoHS, REACH, etc.) — not found in any source material"),
    ("packaging",     "Packaging / tape-and-reel options — not found in any source material"),
]


def compute_gaps(merged: dict) -> list[str]:
    gaps = []
    for field, description in REQUIRED_FIELDS.items():
        if not merged.get(field):
            gaps.append(f"MISSING — {description}")
    for _, description in BROCHURE_GAPS:
        gaps.append(f"NOT IN SOURCE MATERIAL — {description}")
    return gaps


# ---------------------------------------------------------------------------
# Assemble knowledge object
# ---------------------------------------------------------------------------

def build_knowledge(family: str, merged: dict, gaps: list[str],
                    source_files: list[str]) -> dict:
    def field(key):
        return merged.get(key) or []

    return {
        "product_family_name": family,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": "1.0",
        "source_files": source_files,
        "compliance_note": (
            "Every entry in this knowledge object is derived from a direct "
            "text match in the listed source files. No facts have been inferred, "
            "summarized, or generated. Each item carries a citation to its source."
        ),
        "key_specs": {
            "frequency":      field("frequency"),
            "impedance":      field("impedance"),
            "vswr":           field("vswr"),
            "insertion_loss": field("insertion_loss"),
            "return_loss":    field("return_loss"),
            "temperature":    field("temperature"),
            "mating_cycles":  field("mating_cycles"),
            "ip_rating":      field("ip_rating"),
            "interfaces":     field("interfaces"),
        },
        "target_applications": field("applications"),
        "differentiators":     field("differentiators"),
        "compatible_products": field("mating_parts"),
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stage 2: Extract structured knowledge object from Stage 1 sources JSON."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to the sources JSON produced by Stage 1 (e.g. magnum_rf_sources.json)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for knowledge JSON (default: <family_slug>_knowledge.json)"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    print(f"\n=== Stage 2: Structure — reading {input_path.name} ===\n")

    with open(input_path, encoding="utf-8") as f:
        doc = json.load(f)

    family = doc["product_family"]
    sources = [s for s in doc["sources"] if not s.get("error")]
    print(f"Product family : {family}")
    print(f"Sources to process : {len(sources)}\n")

    # Extract from each source
    all_buckets = []
    for s in sources:
        label = s.get("file_name") or s.get("url") or "unknown"
        print(f"  Extracting: {label}")
        buckets = extract_from_source(s)
        all_buckets.append(buckets)
        # Brief per-source summary
        for key, items in buckets.items():
            if items:
                print(f"    {key}: {len(items)} match(es)")

    # Merge and deduplicate
    merged = merge_buckets(all_buckets)

    # Compute gaps
    gaps = compute_gaps(merged)

    # Source file labels for provenance header
    source_files = [
        s.get("file_name") or s.get("url") or "unknown" for s in sources
    ]

    knowledge = build_knowledge(family, merged, gaps, source_files)

    # Output path
    family_slug = family.lower().replace(" ", "_")
    output_path = Path(args.output or f"{family_slug}_knowledge.json")
    output_path.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    print(f"\n[SUMMARY]")
    for category, items in knowledge["key_specs"].items():
        status = f"{len(items)} item(s)" if items else "** EMPTY — will be flagged as gap **"
        print(f"  {category:20s}: {status}")
    print(f"  {'applications':20s}: {len(knowledge['target_applications'])} item(s)")
    print(f"  {'differentiators':20s}: {len(knowledge['differentiators'])} item(s)")
    print(f"  {'compatible_products':20s}: {len(knowledge['compatible_products'])} item(s)")
    print(f"\n[GAPS] {len(gaps)} identified:")
    for g in gaps:
        print(f"  - {g}")
    print(f"\n[OUTPUT] Written to: {output_path.resolve()}")
    print("\nStage 2 complete. Run Stage 3 to generate the brochure draft.\n")


if __name__ == "__main__":
    main()
