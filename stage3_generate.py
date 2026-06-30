#!/usr/bin/env python3
"""
Stage 3 — Generate
Takes the knowledge object from Stage 2 plus FSE-provided customer context
and generates a one-page brochure draft in Markdown.

Every claim in the output must trace to a specific source from Stage 1.
Anything that cannot be supported is placed in a NEEDS INPUT section.
A compliance check runs at the end confirming traceability.

Usage:
    python stage3_generate.py \
        --knowledge magnum_rf_knowledge.json \
        --customer "GTRI" \
        --contact "Dr. Jane Smith" \
        --context "RF-heavy design-in, shock and vibe environment, interested in shielding and ruggedization" \
        --angle "Emphasize mechanical robustness and blind-mate density advantage" \
        --output magnum_rf_GTRI_brochure.md
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Keyword maps: customer context terms → knowledge categories/keywords
# ---------------------------------------------------------------------------

# Maps freeform context keywords to spec categories and excerpt keywords.
# Stage 3 only pulls facts whose excerpts contain these keywords.

CONTEXT_KEYWORD_MAP = {
    # Mechanical / environmental
    "shock":          {"categories": ["differentiators", "interfaces", "ip_rating", "mating_cycles"],
                       "excerpt_terms": ["push-on", "snap", "blind", "mate", "cycle", "lock", "secure",
                                         "rugged", "vibrat", "shock", "IP6", "latch", "retention"]},
    "vibe":           {"categories": ["differentiators", "interfaces", "ip_rating", "mating_cycles"],
                       "excerpt_terms": ["push-on", "snap", "blind", "mate", "cycle", "lock", "secure",
                                         "rugged", "vibrat", "shock", "IP6", "latch", "retention"]},
    "vibration":      {"categories": ["differentiators", "interfaces", "ip_rating", "mating_cycles"],
                       "excerpt_terms": ["push-on", "snap", "blind", "mate", "cycle", "rugged",
                                         "vibrat", "shock", "IP6", "latch", "retention"]},
    "rugge":          {"categories": ["differentiators", "ip_rating", "mating_cycles"],
                       "excerpt_terms": ["rugged", "IP6", "mil", "defense", "vibrat", "shock", "latch"]},
    "shield":         {"categories": ["differentiators", "interfaces"],
                       "excerpt_terms": ["shield", "isolation", "density", "port", "gang"]},
    "density":        {"categories": ["differentiators", "interfaces"],
                       "excerpt_terms": ["density", "gang", "multi-port", "miniature", "space", "blind"]},
    "blind":          {"categories": ["differentiators", "interfaces"],
                       "excerpt_terms": ["blind", "mate", "gang", "push-on", "snap"]},
    # RF performance
    "rf":             {"categories": ["frequency", "vswr", "insertion_loss", "return_loss", "impedance"],
                       "excerpt_terms": ["GHz", "VSWR", "insertion loss", "return loss", "50", "mode-free"]},
    "frequency":      {"categories": ["frequency"],
                       "excerpt_terms": ["GHz", "mode-free", "65", "frequency"]},
    "high frequency": {"categories": ["frequency"],
                       "excerpt_terms": ["GHz", "mode-free", "65"]},
    "mmwave":         {"categories": ["frequency"],
                       "excerpt_terms": ["GHz", "mode-free", "65", "mmWave"]},
    "5g":             {"categories": ["frequency", "applications"],
                       "excerpt_terms": ["5G", "6G", "GHz", "frequency"]},
    "6g":             {"categories": ["frequency", "applications"],
                       "excerpt_terms": ["5G", "6G", "GHz"]},
    "radar":          {"categories": ["applications", "frequency"],
                       "excerpt_terms": ["radar", "Radar", "GHz", "military", "defense"]},
    "defense":        {"categories": ["applications", "differentiators"],
                       "excerpt_terms": ["defense", "Defense", "military", "Military", "radar"]},
    "military":       {"categories": ["applications", "differentiators"],
                       "excerpt_terms": ["military", "Military", "defense", "Defense", "radar"]},
    # Adaptor / cross-sell
    "adaptor":        {"categories": ["compatible_products", "interfaces"],
                       "excerpt_terms": ["adaptor", "adapter", "SMPM", "SMP", "cable", "assembly",
                                         "mates", "compatible"]},
    "adapter":        {"categories": ["compatible_products", "interfaces"],
                       "excerpt_terms": ["adaptor", "adapter", "SMPM", "SMP", "cable", "assembly"]},
    "cable":          {"categories": ["compatible_products"],
                       "excerpt_terms": ["cable", "assembly", "assemblies"]},
    # Test & measurement
    "test":           {"categories": ["applications", "frequency"],
                       "excerpt_terms": ["Test", "Measurement", "GHz", "precision"]},
    "measurement":    {"categories": ["applications", "frequency"],
                       "excerpt_terms": ["Test", "Measurement", "precision"]},
}


def tokenize_context(context: str) -> list[str]:
    """Extract lowercase tokens from freeform context string."""
    words = re.findall(r"[a-zA-Z0-9&/]+", context.lower())
    # Also try multi-word phrases
    phrases = []
    for key in CONTEXT_KEYWORD_MAP:
        if key in context.lower():
            phrases.append(key)
    return list(set(words + phrases))


def facts_relevant_to_context(knowledge: dict, context_tokens: list[str]) -> dict:
    """
    For each context token, pull matching facts from the knowledge object.
    Returns a dict keyed by category with lists of relevant, cited excerpts.
    Only includes facts whose excerpt text matches at least one context keyword.
    """
    relevant: dict[str, list] = {}

    def search_items(items: list, excerpt_terms: list) -> list:
        matched = []
        for item in items:
            excerpt_lower = item["excerpt"].lower()
            if any(t.lower() in excerpt_lower for t in excerpt_terms):
                matched.append(item)
        return matched

    def all_items(category: str) -> list:
        specs = knowledge.get("key_specs", {})
        if category in specs:
            return specs[category]
        elif category == "applications":
            return knowledge.get("target_applications", [])
        elif category == "differentiators":
            return knowledge.get("differentiators", [])
        elif category == "compatible_products":
            return knowledge.get("compatible_products", [])
        return []

    for token in context_tokens:
        mapping = CONTEXT_KEYWORD_MAP.get(token)
        if not mapping:
            continue
        for cat in mapping["categories"]:
            items = all_items(cat)
            matched = search_items(items, mapping["excerpt_terms"])
            if matched:
                existing = relevant.get(cat, [])
                seen_excerpts = {e["excerpt"] for e in existing}
                for m in matched:
                    if m["excerpt"] not in seen_excerpts:
                        existing.append(m)
                        seen_excerpts.add(m["excerpt"])
                relevant[cat] = existing

    return relevant


def deduplicate_items(items: list) -> list:
    seen = set()
    out = []
    for item in items:
        key = item["excerpt"][:60].lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# Spec selection helpers
# ---------------------------------------------------------------------------

# Magnum RF-specific frequency anchors to prefer over catalog-wide values
MAGNUM_RF_FREQ_TERMS = ["65 ghz", "mode-free", "magnum"]

def best_frequency_claim(freq_items: list) -> list:
    """
    Prefer items that explicitly mention 65 GHz / mode-free (Magnum RF-specific).
    Return up to 2 items.
    """
    preferred = [i for i in freq_items
                 if any(t in i["excerpt"].lower() for t in MAGNUM_RF_FREQ_TERMS)]
    others = [i for i in freq_items if i not in preferred]
    combined = preferred + others
    return combined[:2]


# ---------------------------------------------------------------------------
# Markdown brochure renderer
# ---------------------------------------------------------------------------

def clean_excerpt(text: str) -> str:
    """Strip trailing PDF line-break artifacts: hanging conjunctions, hyphens, commas."""
    text = text.strip()
    # Remove trailing hyphen (PDF soft-hyphen line wrap)
    text = re.sub(r"\s*-\s*$", "", text)
    # Remove trailing conjunctions / prepositions that signal a cut sentence
    text = re.sub(r"\s+(?:and|or|the|a|an|for|of|with|in|on|to|,)\s*$", "", text, flags=re.IGNORECASE)
    text = text.rstrip(".,;: ")
    return text


def format_item(item: dict, indent: str = "- ") -> str:
    excerpt = clean_excerpt(item["excerpt"])
    return f'{indent}"{excerpt}" *[{item["citation"]}]*'


def generate_brochure(
    knowledge: dict,
    customer: str,
    contact: str | None,
    context: str,
    angle: str | None,
    relevant: dict,
) -> tuple[str, list[str]]:
    """
    Returns (brochure_markdown, list_of_all_cited_sources).
    """
    family = knowledge["product_family_name"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_citations: list[str] = []
    needs_input: list[str] = []
    claims_log: list[dict] = []  # for compliance check

    def emit(item: dict) -> str:
        all_citations.append(item["citation"])
        claims_log.append(item)
        return format_item(item)

    lines = []

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    lines.append(f"# {family}® — Customer Brief")
    lines.append(f"**Prepared for:** {customer}" + (f" — {contact}" if contact else ""))
    lines.append(f"**Date:** {now}")
    lines.append(f"**FSE context:** {context}")
    if angle:
        lines.append(f"**Emphasis:** {angle}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # -----------------------------------------------------------------------
    # Positioning statement
    # -----------------------------------------------------------------------
    # Prefer excerpts that read as a sentence (contain a verb + product description),
    # not section headers (all-caps short strings).
    def is_sentence_like(text: str) -> bool:
        if text == text.upper() and len(text) < 60:
            return False  # all-caps header
        return len(text.split()) >= 6 and any(
            v in text.lower() for v in ["leverages", "designed", "ideal", "provides",
                                         "supports", "enables", "offers", "system"]
        )

    positioning_candidates = [
        i for i in knowledge.get("differentiators", [])
        if is_sentence_like(i["excerpt"])
    ]
    lines.append("## Positioning")
    if positioning_candidates:
        best = positioning_candidates[0]
        lines.append(
            f"Samtec's **{family}®** {clean_excerpt(best['excerpt'])}. "
            f"*[{best['citation']}]*"
        )
        all_citations.append(best["citation"])
        claims_log.append(best)
    else:
        lines.append(
            f"Samtec's **{family}®** is a ganged, multi-port SMPM interconnect system."
        )
        needs_input.append(
            "Positioning statement — no complete sentence found in source material; "
            "draft text above is a paraphrase. FSE should verify wording against official copy."
        )
    lines.append("")

    # -----------------------------------------------------------------------
    # Key specs relevant to this application
    # -----------------------------------------------------------------------
    lines.append("## Key Specifications (Relevant to Your Application)")
    lines.append("")
    spec_count = 0

    # Frequency
    freq_pool = relevant.get("frequency", [])
    freq_items = best_frequency_claim(freq_pool)
    if freq_items:
        lines.append("**Frequency Performance**")
        for item in freq_items[:2]:
            lines.append(emit(item))
            spec_count += 1
        lines.append("")
    else:
        needs_input.append(
            "Frequency spec — not matched to your stated context. "
            "Confirm max operating frequency for Magnum RF in your application band."
        )

    # VSWR
    vswr_items = deduplicate_items(relevant.get("vswr", knowledge["key_specs"].get("vswr", [])))
    # Filter for numeric values only (skip fragmentary matches)
    vswr_items = [i for i in vswr_items if re.search(r"VSWR\s*[=<>as]*\s*1[\.,\d]", i["excerpt"], re.I)]
    if vswr_items:
        lines.append("**VSWR**")
        for item in vswr_items[:2]:
            lines.append(emit(item))
            spec_count += 1
        lines.append("")

    # Insertion / Return loss
    il_items = deduplicate_items(relevant.get("insertion_loss", knowledge["key_specs"].get("insertion_loss", [])))
    rl_items = deduplicate_items(relevant.get("return_loss", knowledge["key_specs"].get("return_loss", [])))
    if il_items or rl_items:
        lines.append("**Signal Integrity**")
        for item in (il_items + rl_items)[:3]:
            lines.append(emit(item))
            spec_count += 1
        lines.append("")

    # Mating cycles (relevant for shock/vibe) — require an actual number, not "Mates With:"
    mc_items = deduplicate_items(
        relevant.get("mating_cycles", knowledge["key_specs"].get("mating_cycles", []))
    )
    # Require "mating cycle(s)" specifically — not just "Mates With:" catalog labels
    mc_items = [i for i in mc_items if re.search(r"\d[\d,]+\s*mating cycles?", i["excerpt"], re.I)
                or re.search(r"mating cycles?[^.\n]{0,30}\d", i["excerpt"], re.I)]
    if mc_items:
        lines.append("**Mechanical Durability**")
        for item in mc_items[:2]:
            lines.append(emit(item))
            spec_count += 1
        lines.append("")

    # IP rating
    ip_items = deduplicate_items(
        relevant.get("ip_rating", knowledge["key_specs"].get("ip_rating", []))
    )
    if ip_items:
        lines.append("**Environmental Protection**")
        for item in ip_items[:2]:
            lines.append(emit(item))
            spec_count += 1
        lines.append("")

    # Temperature (only include if Magnum RF-specific page — catalog p.32 covers all families)
    temp_items = deduplicate_items(knowledge["key_specs"].get("temperature", []))
    # Flag if sourced from catalog only — not product-specific
    temp_from_catalog_only = all(
        "rfcatalog" in i["citation"].lower() for i in temp_items
    )
    if temp_items and not temp_from_catalog_only:
        lines.append("**Operating Temperature**")
        for item in temp_items[:2]:
            lines.append(emit(item))
            spec_count += 1
        lines.append("")
    elif temp_items:
        needs_input.append(
            "Operating temperature range — values found in RF catalog (p.32) but are not "
            "confirmed as Magnum RF-specific. Verify temp range for MRF series before including."
        )

    if spec_count == 0:
        lines.append(
            "_No specs could be directly matched to the provided application context. "
            "See NEEDS INPUT section._"
        )
        lines.append("")

    # -----------------------------------------------------------------------
    # Why this fits your application
    # -----------------------------------------------------------------------
    lines.append("## Why This Fits Your Application")
    lines.append("")
    fit_count = 0

    # Blind-mate / shock-vibe
    blind_items = [
        i for i in relevant.get("differentiators", [])
        if any(t in i["excerpt"].lower() for t in ["blind", "push-on", "snap", "gang", "multi-port", "density"])
    ]
    if blind_items:
        lines.append("**Shock & Vibration Environments**")
        for item in deduplicate_items(blind_items)[:3]:
            lines.append(emit(item))
            fit_count += 1
        lines.append("")

    # Applications match
    app_items = [
        i for i in relevant.get("applications", [])
        if any(t in i["excerpt"].lower()
               for t in ["defense", "military", "radar", "5g", "6g", "test", "measurement"])
    ]
    if app_items:
        lines.append("**Stated Applications Match**")
        for item in deduplicate_items(app_items)[:3]:
            lines.append(emit(item))
            fit_count += 1
        lines.append("")

    # Adaptor / cross-sell relevant
    compat_items = deduplicate_items(relevant.get("compatible_products", []))
    adaptor_items = [
        i for i in compat_items
        if any(t in i["excerpt"].lower() for t in ["adaptor", "adapter", "smpm", "smp", "cable assembly"])
    ]
    if adaptor_items:
        lines.append("**Compatible Adaptors & Accessories**  \n"
                      "_Relevant because customer purchases RF adaptors_")
        for item in adaptor_items[:3]:
            lines.append(emit(item))
            fit_count += 1
        lines.append("")

    if fit_count == 0:
        lines.append(
            "> **NOTE:** Source material does not contain content that directly connects "
            f"to the stated context (\"{context}\"). "
            "Do not add claims here without additional sourced material. "
            "See NEEDS INPUT section."
        )
        lines.append("")

    # -----------------------------------------------------------------------
    # Cross-sell note (Bulls Eye / other products)
    # -----------------------------------------------------------------------
    # Only surfaces if FSE angle mentions cross-sell products
    if angle and any(t in angle.lower() for t in ["bulls eye", "bull", "firefly", "high speed", "cross"]):
        lines.append("## Cross-Sell Note")
        lines.append(
            "> **FSE note:** A team member at this account is familiar with Samtec's Bulls Eye product. "
            "Source material does not include Bulls Eye specs — do not make technical comparisons "
            "without sourced data. Mention the relationship as a conversation opener only."
        )
        lines.append("")

    # -----------------------------------------------------------------------
    # NEEDS INPUT
    # -----------------------------------------------------------------------
    # Append standard gaps from Stage 2
    for g in knowledge.get("gaps", []):
        needs_input.append(g)

    lines.append("---")
    lines.append("")
    lines.append("## ⚠️ NEEDS INPUT — Do Not Distribute Until Resolved")
    lines.append("")
    if needs_input:
        for item in needs_input:
            lines.append(f"- [ ] {item}")
    else:
        lines.append("_No gaps identified._")
    lines.append("")

    # -----------------------------------------------------------------------
    # Compliance check
    # -----------------------------------------------------------------------
    lines.append("---")
    lines.append("")
    lines.append("## Compliance Check")
    lines.append(
        f"_Generated {now}. Every factual claim in this draft must trace to a specific source "
        "from Stage 1 ingestion._"
    )
    lines.append("")

    unique_citations = sorted(set(all_citations))
    lines.append(f"**Sources cited in this draft ({len(unique_citations)}):**")
    for c in unique_citations:
        lines.append(f"- {c}")
    lines.append("")

    # Flag any claim that slipped through without a citation.
    # Only scan lines ABOVE the compliance section (i.e. the brochure body),
    # not the citation list we just emitted.
    body_end_marker = "**Sources cited in this draft"
    body_lines = []
    for line in lines:
        if line.startswith(body_end_marker):
            break
        body_lines.append(line)

    uncited = []
    for line in body_lines:
        if line.startswith("- ") and "*[" not in line and not line.startswith("- ["):
            stripped = line[2:].strip()
            # Skip descriptive/meta lines that aren't factual claims
            if stripped and not stripped.startswith("_") and not stripped.startswith(">"):
                uncited.append(stripped[:80])

    if uncited:
        lines.append("**⚠️ UNCITED ITEMS — Review before sending:**")
        for u in uncited:
            lines.append(f"- {u}")
        lines.append("")
    else:
        lines.append(
            "**✅ All factual claims in this draft carry inline source citations. "
            "No unsourced assertions detected.**"
        )
        lines.append("")

    if needs_input:
        lines.append(
            f"**⚠️ {len(needs_input)} item(s) in NEEDS INPUT section** — "
            "brochure is incomplete until these are resolved."
        )

    brochure = "\n".join(lines)
    return brochure, all_citations, claims_log


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Stage 3: Generate a one-page customer brochure draft from the knowledge object."
    )
    parser.add_argument("--knowledge", required=True,
                        help="Path to knowledge JSON from Stage 2")
    parser.add_argument("--customer", required=True,
                        help='Customer name, e.g. "GTRI"')
    parser.add_argument("--contact", default=None,
                        help='Point of contact name, e.g. "Dr. Jane Smith"')
    parser.add_argument("--context", required=True,
                        help='Application context, e.g. "RF-heavy, shock and vibe environment"')
    parser.add_argument("--angle", default=None,
                        help='FSE emphasis angle, e.g. "Emphasize blind-mate density advantage"')
    parser.add_argument("--output", default=None,
                        help="Output .md file path (default: <family>_<customer>_brochure.md)")
    args = parser.parse_args()

    kpath = Path(args.knowledge)
    if not kpath.exists():
        sys.exit(f"Knowledge file not found: {kpath}")

    with open(kpath, encoding="utf-8") as f:
        knowledge = json.load(f)

    family = knowledge["product_family_name"]
    family_slug = family.lower().replace(" ", "_")
    customer_slug = re.sub(r"[^a-z0-9]", "_", args.customer.lower())
    output_path = Path(args.output or f"{family_slug}_{customer_slug}_brochure.md")

    print(f"\n=== Stage 3: Generate — {family} for {args.customer} ===\n")

    # Tokenize context + angle together
    full_context = (args.context or "") + " " + (args.angle or "")
    context_tokens = tokenize_context(full_context)
    print(f"Context tokens matched: {[t for t in context_tokens if t in CONTEXT_KEYWORD_MAP]}")

    # Find relevant facts
    relevant = facts_relevant_to_context(knowledge, context_tokens)
    print(f"Relevant fact pools:")
    for cat, items in relevant.items():
        print(f"  {cat}: {len(items)} item(s)")

    # Generate
    brochure, citations, claims_log = generate_brochure(
        knowledge=knowledge,
        customer=args.customer,
        contact=args.contact,
        context=args.context,
        angle=args.angle,
        relevant=relevant,
    )

    output_path.write_text(brochure, encoding="utf-8")

    print(f"\n[OUTPUT] Written to: {output_path.resolve()}")
    print(f"  Total cited claims : {len(claims_log)}")
    print(f"  Unique sources used: {len(set(citations))}")
    print(f"  NEEDS INPUT items  : {len(knowledge.get('gaps', []))}")
    print("\nStage 3 complete.\n")


if __name__ == "__main__":
    main()
