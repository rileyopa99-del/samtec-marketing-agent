"""
Samtec Marketing Materials Generator
Internal FSE Tool — generates customer-ready marketing briefs from verified source material.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Marketing Materials Generator — Samtec",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS — Samtec brand
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Fonts & base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Hide default Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 1300px; }

/* ── Samtec brand colors ── */
:root {
    --samtec-red:    #C8102E;
    --samtec-dark:   #1A1A2E;
    --samtec-gray:   #F4F5F7;
    --samtec-border: #E0E3EA;
    --samtec-text:   #1C1C1E;
    --samtec-muted:  #6B7280;
}

/* ── Top header bar ── */
.header-bar {
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    padding: 18px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: -1rem -1rem 0 -1rem;
    border-bottom: 3px solid var(--samtec-red);
}
.header-bar .brand { color: white; font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
.header-bar .brand span { color: var(--samtec-red); }
.header-bar .subtitle { color: #9CA3AF; font-size: 13px; font-weight: 400; margin-top: 2px; }
.header-bar .badge {
    background: rgba(200,16,46,0.15);
    border: 1px solid rgba(200,16,46,0.4);
    color: #F87171;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

/* ── Section cards ── */
.card {
    background: white;
    border: 1px solid var(--samtec-border);
    border-radius: 12px;
    padding: 24px 28px;
    margin-bottom: 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.card-title {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: var(--samtec-red);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ── Inputs ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    border-radius: 8px !important;
    border: 1.5px solid var(--samtec-border) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    color: var(--samtec-text) !important;
    transition: border-color 0.2s;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--samtec-red) !important;
    box-shadow: 0 0 0 3px rgba(200,16,46,0.08) !important;
}

/* ── Labels ── */
.stTextInput label, .stTextArea label, .stSelectbox label,
.stMultiSelect label, .stRadio label, .stFileUploader label {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: var(--samtec-text) !important;
    letter-spacing: 0.1px;
}

/* ── Primary button ── */
.stButton > button[kind="primary"] {
    background: var(--samtec-red) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 12px 32px !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    letter-spacing: 0.2px !important;
    transition: all 0.2s !important;
    width: 100%;
    box-shadow: 0 2px 8px rgba(200,16,46,0.3) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #a80d26 !important;
    box-shadow: 0 4px 16px rgba(200,16,46,0.4) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="secondary"] {
    border-radius: 8px !important;
    border: 1.5px solid var(--samtec-border) !important;
    font-weight: 500 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: var(--samtec-gray);
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
    border-bottom: none !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: var(--samtec-muted) !important;
    padding: 8px 18px !important;
    border: none !important;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: var(--samtec-red) !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1) !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: var(--samtec-gray);
    border-radius: 10px;
    padding: 14px 18px;
    border: 1px solid var(--samtec-border);
}
[data-testid="metric-container"] label {
    font-size: 11px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.6px !important;
    color: var(--samtec-muted) !important;
}

/* ── Pill tags ── */
.pill {
    display: inline-block;
    background: rgba(200,16,46,0.08);
    color: var(--samtec-red);
    border: 1px solid rgba(200,16,46,0.2);
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 12px;
    font-weight: 600;
    margin: 3px 3px 3px 0;
}

/* ── Divider ── */
hr { border-color: var(--samtec-border) !important; margin: 20px 0 !important; }

/* ── Warning / info callouts ── */
.stAlert { border-radius: 8px !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    border: 2px dashed var(--samtec-border) !important;
    border-radius: 10px !important;
    background: var(--samtec-gray) !important;
    transition: border-color 0.2s;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--samtec-red) !important;
}

/* ── Multiselect tags ── */
[data-baseweb="tag"] {
    background: rgba(200,16,46,0.1) !important;
    color: var(--samtec-red) !important;
    border: 1px solid rgba(200,16,46,0.25) !important;
    border-radius: 6px !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: var(--samtec-muted) !important;
    border-radius: 8px !important;
}

/* ── Step indicator ── */
.step-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px; height: 24px;
    background: var(--samtec-red);
    color: white;
    border-radius: 50%;
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
}

/* ── Caption / helper text ── */
.caption { font-size: 12px; color: var(--samtec-muted); margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("""
<div class="header-bar">
  <div>
    <div class="brand">Samtec <span>Marketing Materials Generator</span></div>
    <div class="subtitle">Field Sales Engineer Tool &nbsp;·&nbsp; Internal Use Only</div>
  </div>
  <div class="badge">🔒 Confidential</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMTEC_INDUSTRIES = [
    "Military / Aerospace",
    "Automotive",
    "Medical / Healthcare",
    "Data Center / Cloud",
    "Test & Measurement",
    "Industrial Automation",
    "Consumer Electronics",
    "Telecommunications / 5G",
    "Space",
    "Semiconductor / ATE",
    "Broadcasting / Video",
    "Transportation / Rail",
]

DECISION_DRIVERS = [
    "Performance (signal integrity, frequency)",
    "Ruggedization (shock, vibe, IP rating)",
    "Size / Density (board space, height)",
    "Compatibility (mating parts, ecosystem)",
    "Price / Lead Time",
    "Speed to Market (standard parts, fast delivery)",
]

OUTPUT_LANGUAGES = [
    "English",
    "Spanish (Español)",
    "French (Français)",
    "German (Deutsch)",
    "Japanese (日本語)",
    "Korean (한국어)",
    "Mandarin Chinese (普通话)",
]

KNOWN_FAMILIES = [
    "Magnum RF", "Firefly", "Bulls Eye", "SEARAY", "LSHM", "HSPD",
    "TSM", "URSA I/O", "RF Adaptors", "VNX 90+", "HSEC8", "Tiger Eye",
    "Edge Rate", "Z-Pack HM", "QSE", "QMSS", "Optics / FireFly",
    "High-Speed Board-to-Board", "Mezzanine / Stacking",
]

KNOWN_CONTEXTS = [
    "Shock and vibration environment (MIL-STD-810)",
    "High-density board layout, space-constrained chassis",
    "mmWave / 5G above 40 GHz",
    "Ruggedized field deployment, extreme temperature range",
    "Precision test & measurement lab environment",
    "High-speed data rates above 56 Gbps PAM4",
    "Blind-mate backplane in rackmount chassis",
    "Mission-critical uptime, no field-serviceable connections",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def discover_knowledge_files() -> dict[str, str]:
    """Return {display_name: file_path} for all *_knowledge.json files found."""
    files = sorted(Path(".").glob("*_knowledge.json"))
    out = {}
    for f in files:
        name = f.stem.replace("_knowledge", "").replace("_", " ").title()
        out[name] = str(f)
    return out


def run_stage3(knowledge_path: str, customer: str, contact: str,
               context: str, angle: str, language: str) -> str:
    lang_note = f" Output language: {language}." if language != "English" else ""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as tmp:
        out_path = tmp.name
    result = subprocess.run(
        [sys.executable, "stage3_generate.py",
         "--knowledge", knowledge_path,
         "--customer", customer,
         "--contact", contact or "—",
         "--context", context + lang_note,
         "--angle", angle,
         "--output", out_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return f"**Generator error:**\n```\n{result.stderr}\n```"
    return Path(out_path).read_text(encoding="utf-8")


def ingest_and_build_knowledge(family: str, uploaded_files: list) -> tuple[str | None, str]:
    """
    Run Stage 1 + 2 for uploaded files and return (knowledge_path, status_message).
    Returns (None, error_msg) on failure.
    """
    slug = re.sub(r"[^a-z0-9]", "_", family.lower()).strip("_")
    sources_path = f"{slug}_sources.json"
    knowledge_path = f"{slug}_knowledge.json"

    # Save uploaded files to temp paths
    saved_paths = []
    for uf in uploaded_files:
        suffix = Path(uf.name).suffix
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(uf.read())
        tmp.close()
        saved_paths.append(tmp.name)

    if not saved_paths:
        return None, "No source files provided. Upload at least one PDF or text file."

    # Stage 1
    r1 = subprocess.run(
        [sys.executable, "stage1_ingest.py",
         "--family", family,
         "--files", *saved_paths,
         "--output", sources_path],
        capture_output=True, text=True,
    )
    if r1.returncode != 0:
        return None, f"Stage 1 failed:\n{r1.stderr}"

    # Stage 2
    r2 = subprocess.run(
        [sys.executable, "stage2_structure.py",
         "--input", sources_path,
         "--output", knowledge_path],
        capture_output=True, text=True,
    )
    if r2.returncode != 0:
        return None, f"Stage 2 failed:\n{r2.stderr}"

    return knowledge_path, "Knowledge base built successfully."


def count_needs_input(md: str) -> int:
    return len(re.findall(r"^- \[ \]", md, re.MULTILINE))


def count_cited_claims(md: str) -> int:
    return len(re.findall(r"\*\[.+?\]\*", md))


def compliance_passed(md: str) -> bool:
    return "✅" in md and "UNCITED ITEMS" not in md


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
if "knowledge_path" not in st.session_state:
    st.session_state.knowledge_path = None
if "knowledge_family" not in st.session_state:
    st.session_state.knowledge_family = None
if "results" not in st.session_state:
    st.session_state.results = []

known_files = discover_knowledge_files()

# ---------------------------------------------------------------------------
# Layout — two column main
# ---------------------------------------------------------------------------
left, right = st.columns([5, 7], gap="large")

# ═══════════════════════════════════════════════════════════════════════════
# LEFT COLUMN — Inputs
# ═══════════════════════════════════════════════════════════════════════════
with left:

    # ── STEP 1: Product ──────────────────────────────────────────────────
    st.markdown("""
    <div class="card-title">
      <span class="step-badge">1</span> Product Family or Series
    </div>""", unsafe_allow_html=True)

    family_input = st.text_input(
        "Product family or series",
        placeholder="e.g. Magnum RF, TSM, LSHM, Firefly, VNX 90+…",
        label_visibility="collapsed",
    )

    # Suggestion pills for known families
    st.markdown("**Quick select:**")
    pill_html = "".join(f'<span class="pill">{f}</span>' for f in KNOWN_FAMILIES)
    st.markdown(f'<div>{pill_html}</div>', unsafe_allow_html=True)
    st.markdown("<div class='caption'>Click a pill or type above — you can enter any Samtec series.</div>",
                unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Source material upload
    st.markdown("""
    <div class="card-title" style="margin-top:20px">
      <span class="step-badge">2</span> Source Materials
    </div>""", unsafe_allow_html=True)

    if family_input and family_input.title() in known_files:
        st.success(f"✅ Pre-built knowledge found for **{family_input}** — no upload needed.")
        st.session_state.knowledge_path = known_files[family_input.title()]
        st.session_state.knowledge_family = family_input
        uploaded_files = []
    else:
        st.markdown(
            "<div class='caption' style='margin-bottom:8px'>Upload datasheets, brochures, or blog posts. "
            "PDFs and .txt accepted. The tool will never generate claims beyond what's in these files.</div>",
            unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            "Drop marketing materials here",
            type=["pdf", "txt"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded_files:
            st.markdown(f"<div class='caption'>📎 {len(uploaded_files)} file(s) ready</div>",
                        unsafe_allow_html=True)

    st.markdown("---")

    # ── STEP 3: Customer ─────────────────────────────────────────────────
    st.markdown("""
    <div class="card-title">
      <span class="step-badge">3</span> Customer Details
    </div>""", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        customer = st.text_input("Account / Company", placeholder="e.g. GTRI, Raytheon")
    with c2:
        contact = st.text_input("Point of Contact", placeholder="e.g. Dr. Jane Smith")

    industry = st.selectbox(
        "Industry / Vertical",
        options=["— Select industry —"] + SAMTEC_INDUSTRIES + ["Other (describe below)"],
    )

    if industry == "Other (describe below)":
        industry = st.text_input("Describe the industry", placeholder="e.g. Quantum Computing")

    st.markdown("---")

    # ── STEP 4: Application context ──────────────────────────────────────
    st.markdown("""
    <div class="card-title">
      <span class="step-badge">4</span> Application Context
    </div>""", unsafe_allow_html=True)

    context_select = st.selectbox(
        "Common scenarios",
        options=["— Choose a starting point or type below —"] + KNOWN_CONTEXTS + ["Custom — describe below"],
        label_visibility="collapsed",
    )

    if context_select not in ("— Choose a starting point or type below —", "Custom — describe below"):
        context_base = st.text_area(
            "Application context",
            value=context_select,
            height=80,
            help="Edit this text or add more detail.",
        )
    else:
        context_base = st.text_area(
            "Describe the application",
            placeholder="e.g. Airborne radar pod, shock-rated to MIL-STD-810, needs blind-mate for field swap…",
            height=80,
        )

    st.markdown("---")

    # ── STEP 5: Emphasis ─────────────────────────────────────────────────
    st.markdown("""
    <div class="card-title">
      <span class="step-badge">5</span> Key Decision Drivers
    </div>""", unsafe_allow_html=True)

    st.markdown("<div class='caption' style='margin-bottom:8px'>Select up to 3 — each becomes a separate brochure variant.</div>",
                unsafe_allow_html=True)

    selected_drivers = []
    driver_cols = st.columns(2)
    for i, driver in enumerate(DECISION_DRIVERS):
        with driver_cols[i % 2]:
            if st.checkbox(driver, key=f"driver_{i}"):
                selected_drivers.append(driver)

    custom_angle = st.text_input(
        "Additional FSE angle (optional)",
        placeholder="e.g. Contact loves Bulls Eye — use as conversation opener",
    )

    st.markdown("---")

    # ── STEP 6: Additional options ───────────────────────────────────────
    with st.expander("Additional Options"):
        language = st.selectbox("Output language", OUTPUT_LANGUAGES)
        cross_sell = st.text_area(
            "Cross-sell / relationship notes",
            placeholder="e.g. Account buys lots of RF adaptors. Engineer on their team knows Bulls Eye.",
            height=72,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Generate button ──────────────────────────────────────────────────
    angles_to_run = selected_drivers[:3] + ([custom_angle.strip()] if custom_angle.strip() else [])
    if len(angles_to_run) > 3:
        angles_to_run = angles_to_run[:3]

    ready = bool(
        family_input.strip()
        and customer.strip()
        and context_base.strip()
        and angles_to_run
        and (st.session_state.knowledge_path or uploaded_files)
    )

    generate_clicked = st.button(
        "Generate Marketing Materials",
        type="primary",
        disabled=not ready,
    )

    if not ready:
        missing = []
        if not family_input.strip(): missing.append("product family")
        if not customer.strip(): missing.append("customer name")
        if not context_base.strip(): missing.append("application context")
        if not angles_to_run: missing.append("at least one decision driver")
        if not (st.session_state.knowledge_path or uploaded_files): missing.append("source materials")
        if missing:
            st.markdown(f"<div class='caption'>Still needed: {', '.join(missing)}</div>",
                        unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — Output
# ═══════════════════════════════════════════════════════════════════════════
with right:

    if not generate_clicked and not st.session_state.results:
        st.markdown("""
        <div style="display:flex; flex-direction:column; align-items:center; justify-content:center;
                    height:500px; text-align:center; color:#9CA3AF;">
          <div style="font-size:56px; margin-bottom:16px;">📋</div>
          <div style="font-size:18px; font-weight:600; color:#374151; margin-bottom:8px;">
            Ready to generate
          </div>
          <div style="font-size:14px; max-width:340px; line-height:1.6;">
            Fill in the details on the left, select your decision drivers,
            and hit <strong style="color:#C8102E">Generate</strong>.
            Each driver produces a separate, citation-verified variant.
          </div>
        </div>
        """, unsafe_allow_html=True)

    if generate_clicked:
        # Build knowledge base from uploads if needed
        kpath = st.session_state.knowledge_path

        if not kpath or st.session_state.knowledge_family != family_input.strip():
            if uploaded_files:
                with st.spinner(f"Building knowledge base for **{family_input}** from uploaded files…"):
                    kpath, msg = ingest_and_build_knowledge(family_input.strip(), uploaded_files)
                if kpath:
                    st.session_state.knowledge_path = kpath
                    st.session_state.knowledge_family = family_input.strip()
                else:
                    st.error(msg)
                    st.stop()
            else:
                st.error("No source files found. Upload PDFs or select a product family with a pre-built knowledge base.")
                st.stop()

        # Build full context string
        context_parts = [context_base.strip()]
        if industry and industry not in ("— Select industry —",):
            context_parts.append(f"Industry: {industry}")
        if cross_sell.strip():
            context_parts.append(f"Cross-sell context: {cross_sell.strip()}")
        full_context = ". ".join(context_parts)

        # Generate one variant per angle
        results = []
        for angle in angles_to_run:
            with st.spinner(f"Generating: *{angle[:60]}*…"):
                md = run_stage3(
                    knowledge_path=kpath,
                    customer=customer.strip(),
                    contact=contact.strip(),
                    context=full_context,
                    angle=angle,
                    language=language if "language" in dir() else "English",
                )
                results.append({"angle": angle, "md": md})

        st.session_state.results = results

    # ── Display results ──────────────────────────────────────────────────
    if st.session_state.results:
        results = st.session_state.results
        tabs = st.tabs([f"Variant {i+1}" for i in range(len(results))])

        for i, (tab, res) in enumerate(zip(tabs, results)):
            with tab:
                angle_label = res["angle"]
                md = res["md"]

                # Sub-header
                st.markdown(
                    f"<div style='font-size:13px; font-weight:600; color:#C8102E; "
                    f"margin-bottom:12px; padding:8px 14px; background:#FFF0F2; "
                    f"border-radius:8px; border-left:3px solid #C8102E;'>"
                    f"📌 {angle_label}</div>",
                    unsafe_allow_html=True,
                )

                # Metrics row
                needs = count_needs_input(md)
                cited = count_cited_claims(md)
                passed = compliance_passed(md)

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Cited Claims", cited)
                m2.metric("Needs Input", needs)
                m3.metric("Compliance", "Pass ✅" if passed else "Review ⚠️")
                m4.metric("Variant", f"{i+1} of {len(results)}")

                st.divider()

                # Brochure body (above compliance section)
                compliance_split = md.split("## Compliance Check")
                brochure_body = compliance_split[0]
                compliance_section = ("## Compliance Check" + compliance_split[1]
                                      if len(compliance_split) > 1 else "")

                st.markdown(brochure_body)

                with st.expander("🔍 Source Trace & Compliance Check"):
                    st.markdown(compliance_section)

                st.divider()

                slug_customer = re.sub(r"[^a-z0-9]", "_",
                                       (customer if "customer" in dir() else "customer").lower())
                slug_family = re.sub(r"[^a-z0-9]", "_", family_input.lower() if family_input else "product")

                st.download_button(
                    label=f"⬇️ Download Variant {i+1} (.md)",
                    data=md,
                    file_name=f"{slug_customer}_{slug_family}_variant{i+1}.md",
                    mime="text/markdown",
                    key=f"dl_{i}",
                )
