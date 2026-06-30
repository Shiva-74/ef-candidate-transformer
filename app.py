from __future__ import annotations
import json
import logging
import os
import pathlib
import re
import tempfile
from typing import Optional

import streamlit as st

from pipeline import load_config, run_pipeline

logging.basicConfig(level=logging.WARNING)

st.set_page_config(
    page_title="Candidate Profile Transformer",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #F7F7F8 !important;
    color: #1A1A1A;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

[data-testid="stAppViewContainer"] > .main > .block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1080px;
}

#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 1px solid #E5E7EB;
    background: transparent;
    padding: 0;
    margin-bottom: 1.5rem;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    padding: 0.55rem 1.2rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: #6B7280;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    border-radius: 0;
    margin-bottom: -1px;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #1A1A1A;
    border-bottom: 2px solid #2563EB !important;
    background: transparent;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display: none; }

/* ── Primary button ── */
[data-testid="stButton"] > button {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 4px !important;
    padding: 0.5rem 1.25rem !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    box-shadow: none !important;
    transition: background 150ms ease !important;
    width: 100%;
}
[data-testid="stButton"] > button:hover {
    background: #1D4ED8 !important;
}

/* ── Download button ── */
[data-testid="stDownloadButton"] > button {
    background: #FFFFFF !important;
    color: #2563EB !important;
    border: 1px solid #DBEAFE !important;
    border-radius: 4px !important;
    padding: 0.4rem 1rem !important;
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    box-shadow: none !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: #EFF6FF !important;
}

/* ── File uploader — hide default label, fix browse button ── */
[data-testid="stFileUploader"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 4px;
    padding: 0.5rem 0.75rem;
}
[data-testid="stFileUploader"] > label { display: none !important; }
[data-testid="stFileUploaderDropzone"] {
    background: #FFFFFF !important;
    border: 1px dashed #D1D5DB !important;
    border-radius: 4px !important;
    padding: 0.5rem !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span {
    font-size: 0.8125rem !important;
    color: #6B7280 !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: #FFFFFF !important;
    color: #2563EB !important;
    border: 1px solid #DBEAFE !important;
    border-radius: 4px !important;
    font-size: 0.8125rem !important;
    font-weight: 500 !important;
    padding: 0.3rem 0.75rem !important;
    box-shadow: none !important;
}

/* ── Text input ── */
[data-testid="stTextInput"] > label {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: #374151 !important;
}
[data-testid="stTextInput"] input {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 4px !important;
    font-size: 0.875rem !important;
    color: #1A1A1A !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 2px #BFDBFE !important;
}

/* ── Selectbox ── */
[data-testid="stSelectbox"] > label {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: #374151 !important;
}
[data-testid="stSelectbox"] > div > div {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 4px !important;
    font-size: 0.875rem !important;
}

/* ── Expander — fix arrow/text overlap ── */
[data-testid="stExpander"] {
    border: 1px solid #E5E7EB !important;
    border-radius: 4px !important;
    background: #FFFFFF !important;
    box-shadow: none !important;
}
[data-testid="stExpander"] > details > summary {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: #6B7280 !important;
    padding: 0.6rem 0.875rem !important;
    list-style: none !important;
}
[data-testid="stExpander"] > details > summary::-webkit-details-marker {
    display: none !important;
}
[data-testid="stExpander"] > details > summary::after {
    content: "▾" !important;
    float: right !important;
    color: #9CA3AF !important;
    font-size: 0.75rem !important;
}

/* ── JSON viewer ── */
[data-testid="stJson"] {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 4px !important;
    font-size: 0.8rem !important;
}

/* ── Text area ── */
[data-testid="stTextArea"] textarea {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 4px !important;
    font-size: 0.875rem !important;
    font-family: 'Inter', monospace !important;
}

/* ── Divider ── */
hr { border: none; border-top: 1px solid #E5E7EB; margin: 1.25rem 0; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _divider():
    st.markdown('<hr>', unsafe_allow_html=True)


def _section_label(title: str):
    st.markdown(f"""
    <div style="font-size:0.6875rem; font-weight:600; text-transform:uppercase;
                letter-spacing:0.08em; color:#6B7280; padding-bottom:0.5rem;
                border-bottom:1px solid #E5E7EB; margin:1.5rem 0 0.875rem 0;">
        {title}
    </div>""", unsafe_allow_html=True)


def _notice(msg: str, kind: str = "info"):
    palette = {
        "info":    ("#2563EB", "#EFF6FF"),
        "warning": ("#B45309", "#FFFBEB"),
        "error":   ("#6B7280", "#F9FAFB"),
    }
    bc, bg = palette.get(kind, palette["info"])
    st.markdown(f"""
    <div style="border-left:3px solid {bc}; background:{bg};
                padding:0.625rem 0.875rem; border-radius:0 3px 3px 0;
                font-size:0.875rem; color:#374151; margin:0.75rem 0;">
        {msg}
    </div>""", unsafe_allow_html=True)


def _skill_chip(name: str, confidence: float, sources: list) -> str:
    pct = int(confidence * 100)
    src = ", ".join(sources) if sources else "—"
    return f"""<div title="Sources: {src}" style="display:inline-flex;
        flex-direction:column; gap:1px; border:1px solid #E5E7EB;
        border-radius:3px; padding:4px 9px; margin:3px 4px 3px 0;
        background:#FFFFFF; vertical-align:top;">
        <span style="font-size:0.8125rem; color:#1A1A1A; font-weight:500;
                     line-height:1.3;">{name}</span>
        <span style="font-size:0.6875rem; color:#9CA3AF;
                     font-variant-numeric:tabular-nums;">{pct}%</span>
    </div>"""


def _meta_row(label: str, value: str) -> str:
    return f"""<div style="display:flex; gap:0.5rem; align-items:baseline;
                           padding:4px 0; border-bottom:1px solid #F3F4F6;">
        <span style="font-size:0.75rem; font-weight:500; color:#6B7280;
                     text-transform:uppercase; letter-spacing:0.04em;
                     min-width:110px; flex-shrink:0;">{label}</span>
        <span style="font-size:0.875rem; color:#1A1A1A;">{value or "—"}</span>
    </div>"""


def _provenance_table(provenance: list):
    if not provenance:
        st.markdown('<p style="font-size:0.875rem; color:#9CA3AF;">No provenance data.</p>',
                    unsafe_allow_html=True)
        return
    rows = ""
    for e in provenance:
        pct = int(e.confidence * 100)
        col = "#2563EB" if e.confidence >= 0.75 else "#9CA3AF"
        rows += f"""<tr>
            <td style="padding:5px 10px 5px 0; font-size:0.8125rem; color:#374151;
                       border-bottom:1px solid #F3F4F6;">{e.field}</td>
            <td style="padding:5px 10px 5px 0; font-size:0.8125rem; color:#6B7280;
                       border-bottom:1px solid #F3F4F6;">{e.source}</td>
            <td style="padding:5px 10px 5px 0; font-size:0.8125rem; color:#6B7280;
                       border-bottom:1px solid #F3F4F6;">{e.method}</td>
            <td style="padding:5px 0; font-size:0.8125rem; font-weight:500; color:{col};
                       border-bottom:1px solid #F3F4F6;
                       font-variant-numeric:tabular-nums;">{pct}%</td>
        </tr>"""
    st.markdown(f"""<table style="width:100%; border-collapse:collapse;">
        <thead><tr>
            {''.join(f'<th style="text-align:left; font-size:0.6875rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#9CA3AF; padding:0 10px 8px 0;">{h}</th>' for h in ['Field','Source','Method','Confidence'])}
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_output_field_map(config: dict) -> dict:
    """
    Build {canonical_base → output_key} from config["fields"].
    e.g. {"emails": "primary_email", "skills": "skills", "full_name": "full_name"}
    Strips bracket notation: "emails[0]" → "emails", "skills[].name" → "skills".
    """
    result = {}
    for f in config.get("fields", []):
        out_key = f.get("path")
        src = f.get("from", out_key)
        if not src or not out_key:
            continue
        canonical = src.split("[")[0]  # strip [0] / [] / [].attr
        result.setdefault(canonical, out_key)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Input panel
# ─────────────────────────────────────────────────────────────────────────────

def _render_input_panel():
    st.markdown("""
    <div style="margin-bottom:1.25rem;">
        <div style="font-size:1.125rem; font-weight:600; color:#1A1A1A;
                    letter-spacing:-0.01em;">Candidate Profile Transformer</div>
        <div style="font-size:0.8125rem; color:#6B7280; margin-top:3px;">
            Ingest structured and unstructured candidate data from multiple sources
            into a single canonical profile.
        </div>
    </div>
    <hr style="border:none; border-top:1px solid #E5E7EB; margin:0 0 1.25rem 0;">
    """, unsafe_allow_html=True)

    # Row 1 — inputs
    col1, col2, col3 = st.columns(3, gap="medium")

    with col1:
        st.markdown('<p style="font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#374151; margin:0 0 4px 0;">Recruiter CSV</p>', unsafe_allow_html=True)
        csv_file = st.file_uploader("csv", type=["csv"], label_visibility="collapsed", key="csv_upload")

    with col2:
        st.markdown('<p style="font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:#374151; margin:0 0 4px 0;">Resume PDF</p>', unsafe_allow_html=True)
        pdf_file = st.file_uploader("pdf", type=["pdf"], label_visibility="collapsed", key="pdf_upload")

    with col3:
        github_input = st.text_input(
            "GitHub Profile",
            placeholder="username or https://github.com/username",
            key="github_input",
        )

    st.markdown('<div style="height:0.375rem;"></div>', unsafe_allow_html=True)

    # Row 2 — config + button
    col4, col5, col6 = st.columns([2, 2, 1], gap="medium")

    with col4:
        config_choice = st.selectbox(
            "Output Config",
            options=["Default", "Custom", "Paste JSON"],
            key="config_choice",
        )

    with col5:
        custom_config_str = ""
        if config_choice == "Paste JSON":
            custom_config_str = st.text_area(
                "Config JSON",
                height=80,
                placeholder='{"fields": [...], "include_confidence": true}',
                key="config_paste",
            )
        else:
            cfg_file = "default_config.json" if config_choice == "Default" else "custom_config.json"
            st.markdown(
                f'<div style="padding-top:1.8rem; font-size:0.8125rem; color:#9CA3AF;">Using configs/{cfg_file}</div>',
                unsafe_allow_html=True,
            )

    with col6:
        st.markdown('<div style="height:1.8rem;"></div>', unsafe_allow_html=True)
        generate_clicked = st.button("Generate Profile", key="generate_btn")

    return csv_file, pdf_file, github_input, config_choice, custom_config_str, generate_clicked


# ─────────────────────────────────────────────────────────────────────────────
# Profile tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_profile_tab(candidate, output: dict, config: dict):
    # Build a map so we know which canonical fields are included in the config
    field_map = _get_output_field_map(config)

    def _shown(canonical: str) -> bool:
        """True if this canonical field is in the config AND has a non-null value in output."""
        out_key = field_map.get(canonical)
        if out_key is None:
            return False
        return out_key in output and output.get(out_key) is not None

    conf     = candidate.overall_confidence
    conf_pct = int(conf * 100)
    conf_col = "#2563EB" if conf >= 0.75 else "#9CA3AF"

    # Header — always shown (name / headline / confidence bar)
    st.markdown(f"""
    <div style="padding:1rem 0 0.75rem 0;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
                <div style="font-size:1.5rem; font-weight:600; color:#1A1A1A;
                            letter-spacing:-0.02em; line-height:1.2;">
                    {candidate.full_name or "Name not found"}
                </div>
                <div style="font-size:0.9375rem; color:#6B7280; margin-top:5px;
                            max-width:620px; line-height:1.5;">
                    {candidate.headline or ""}
                </div>
            </div>
            <div style="text-align:right; flex-shrink:0; padding-left:2rem;">
                <div style="font-size:0.6875rem; font-weight:600; text-transform:uppercase;
                            letter-spacing:0.06em; color:#9CA3AF; margin-bottom:4px;">
                    Profile Confidence
                </div>
                <div style="font-size:1.375rem; font-weight:600; color:{conf_col};
                            font-variant-numeric:tabular-nums;">{conf_pct}%</div>
                <div style="height:3px; width:80px; background:#F3F4F6; border-radius:2px;
                            margin-top:5px; margin-left:auto;">
                    <div style="height:3px; width:{conf_pct}%; background:{conf_col};
                                border-radius:2px;"></div>
                </div>
            </div>
        </div>
    </div>
    <hr style="border:none; border-top:1px solid #E5E7EB; margin:0;">
    """, unsafe_allow_html=True)

    # Contact — only show rows whose canonical field is included in the config
    contact_canonicals = ["emails", "phones", "location", "links", "years_experience"]
    if any(_shown(f) for f in contact_canonicals):
        _section_label("Contact")
        rows = ""
        if _shown("emails") and candidate.emails:
            rows += _meta_row("Email", " · ".join(candidate.emails))
        if _shown("phones") and candidate.phones:
            rows += _meta_row("Phone", " · ".join(candidate.phones))
        loc = candidate.location
        loc_str = ", ".join(filter(None, [loc.city, loc.region, loc.country]))
        if _shown("location") and loc_str:
            rows += _meta_row("Location", loc_str)
        if _shown("links") and candidate.links.linkedin:
            rows += _meta_row("LinkedIn", candidate.links.linkedin)
        if _shown("links") and candidate.links.github:
            rows += _meta_row("GitHub", candidate.links.github)
        if _shown("links") and candidate.links.portfolio:
            rows += _meta_row("Portfolio", candidate.links.portfolio)
        if _shown("years_experience") and candidate.years_experience is not None:
            rows += _meta_row("Experience", f"{int(candidate.years_experience)} years")
        if rows:
            st.markdown(f'<div>{rows}</div>', unsafe_allow_html=True)
        else:
            _notice("No contact information found in the provided sources.", "warning")

    # Skills
    if _shown("skills") and candidate.skills:
        _section_label("Skills")
        chips = "".join(
            _skill_chip(s.name, s.confidence, s.sources)
            for s in sorted(candidate.skills, key=lambda x: -x.confidence)
        )
        st.markdown(f'<div style="display:flex; flex-wrap:wrap; padding:0.25rem 0 0.5rem 0;">{chips}</div>',
                    unsafe_allow_html=True)

    # Experience
    if _shown("experience") and candidate.experience:
        _section_label("Experience")
        for exp in candidate.experience:
            date_str = ""
            if exp.start or exp.end:
                date_str = f"{exp.start or '?'} — {exp.end or 'Present'}"
            st.markdown(f"""
            <div style="padding:0.625rem 0 0.625rem 0.75rem; border-left:2px solid #E5E7EB; margin-bottom:0.875rem;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; gap:1rem;">
                    <div>
                        <span style="font-size:0.9375rem; font-weight:600; color:#1A1A1A;">
                            {exp.company or "—"}
                        </span>
                        {f'<span style="font-size:0.875rem; color:#6B7280; margin-left:0.5rem;">{exp.title}</span>' if exp.title else ""}
                    </div>
                    <div style="font-size:0.8125rem; color:#9CA3AF; flex-shrink:0;
                                font-variant-numeric:tabular-nums;">{date_str}</div>
                </div>
                {f'<div style="font-size:0.8125rem; color:#6B7280; margin-top:4px; line-height:1.5;">{exp.summary}</div>' if exp.summary else ""}
            </div>""", unsafe_allow_html=True)

    # Education
    if _shown("education") and candidate.education:
        _section_label("Education")
        for edu in candidate.education:
            degree_field = " · ".join(filter(None, [edu.degree, edu.field]))
            # Build date range: "2021 – 2023", "2021 – Present", or just the end year
            if edu.start_year and edu.end_year:
                date_str = f"{edu.start_year} – {edu.end_year}"
            elif edu.start_year:
                date_str = f"{edu.start_year} – Present"
            else:
                date_str = edu.end_year or ""
            st.markdown(f"""
            <div style="padding:0.625rem 0 0.625rem 0.75rem; border-left:2px solid #E5E7EB; margin-bottom:0.875rem;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; gap:1rem;">
                    <div>
                        <span style="font-size:0.9375rem; font-weight:600; color:#1A1A1A;">
                            {edu.institution or '—'}
                        </span>
                        {f'<span style="font-size:0.875rem; color:#6B7280; margin-left:0.5rem;">{degree_field}</span>' if degree_field else ''}
                    </div>
                    <div style="font-size:0.8125rem; color:#9CA3AF; flex-shrink:0;
                                font-variant-numeric:tabular-nums;">{date_str}</div>
                </div>
            </div>""", unsafe_allow_html=True)

    # Projects — parse title / tech-stack / bullet lines for rich display
    if _shown("projects") and candidate.projects:
        _section_label("Projects")

        # Regex helpers
        _BULLET_RE = re.compile(r"^[\u2022\u2013\-\*\u25cf]")   # starts with bullet char
        _TECH_RE   = re.compile(                                   # 3+ separator-joined tokens
            r"^[A-Za-z0-9\.\+\#\/\s]+(?:\s*[·,/|]\s*[A-Za-z0-9\.\+\#\/\s]+){2,}$"
        )

        # Group lines into project cards.
        # A new card starts when the line is NOT:
        #   - a bullet line (•, -, *, –)
        #   - a tech-stack line (handled as continuation of current card)
        #   - a lowercase continuation (PDF word-wrap mid-sentence)
        cards: list = []
        for line in candidate.projects:
            is_bullet       = bool(_BULLET_RE.match(line))
            is_tech         = bool(cards and _TECH_RE.match(line))
            is_lower_cont   = bool(cards and line and line[0].islower())
            is_continuation = is_bullet or is_tech or is_lower_cont
            if is_continuation and cards:
                cards[-1].append(line)
            else:
                cards.append([line])

        for card in cards:
            if not card:
                continue
            title      = card[0]
            rest       = card[1:]
            tech_html  = ""
            body_parts = []

            for i, ln in enumerate(rest):
                if i == 0 and _TECH_RE.match(ln):
                    tags = [t.strip() for t in re.split(r"[·,/|]", ln) if t.strip()]
                    tech_html = "".join(
                        f'<span style="display:inline-block;background:#EFF6FF;color:#2563EB;'
                        f'border:1px solid #DBEAFE;border-radius:3px;font-size:0.75rem;'
                        f'padding:1px 7px;margin:0 4px 4px 0;font-weight:500;">{t}</span>'
                        for t in tags
                    )
                else:
                    body_parts.append(
                        f'<div style="font-size:0.8125rem;color:#6B7280;line-height:1.6;'
                        f'padding-left:0.25rem;">{ln}</div>'
                    )

            # Build the full HTML as a flat string (no indentation) to avoid
            # Streamlit treating 4-space-indented lines as code blocks.
            html = (
                '<div style="padding:0.625rem 0 0.75rem 0.75rem;border-left:2px solid #E5E7EB;margin-bottom:1rem;">'
                f'<div style="font-size:0.9375rem;font-weight:600;color:#1A1A1A;line-height:1.4;margin-bottom:0.3rem;">{title}</div>'
                + (f'<div style="margin-bottom:0.4rem;">{tech_html}</div>' if tech_html else "")
                + "".join(body_parts)
                + "</div>"
            )
            st.markdown(html, unsafe_allow_html=True)


    # Certifications
    if _shown("certifications") and candidate.certifications:
        _section_label("Certifications")
        for cert in candidate.certifications:
            st.markdown(f"""
            <div style="padding:0.375rem 0; border-bottom:1px solid #F3F4F6;
                        font-size:0.875rem; color:#374151;">{cert}</div>
            """, unsafe_allow_html=True)

    # Achievements
    if _shown("achievements") and candidate.achievements:
        _section_label("Achievements")
        st.markdown(
            f'<div style="font-size:0.875rem; color:#374151; line-height:1.6;">'
            + "<br>".join(candidate.achievements) + "</div>",
            unsafe_allow_html=True,
        )

    # Data sources — always shown
    sources_used = list({p.source for p in candidate.provenance})
    if sources_used:
        _section_label("Data Sources")
        st.markdown(
            " &nbsp;·&nbsp; ".join(
                f'<span style="font-size:0.8125rem; color:#374151; font-weight:500;">{s}</span>'
                for s in sources_used
            ),
            unsafe_allow_html=True,
        )

    with st.expander("Provenance detail"):
        _provenance_table(candidate.provenance)


# ─────────────────────────────────────────────────────────────────────────────
# JSON tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_json_tab(candidate, output: dict):
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(
            '<div style="font-size:0.8125rem; color:#6B7280; padding-bottom:0.75rem;">'
            'Projected output shaped by the selected config.</div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.download_button(
            label="Download JSON",
            data=json.dumps(output, indent=2, ensure_ascii=False).encode(),
            file_name="candidate_profile.json",
            mime="application/json",
            use_container_width=True,
        )

    st.json(output)
    _divider()

    with st.expander("Full canonical record with provenance"):
        col_a, col_b = st.columns([4, 1])
        with col_b:
            st.download_button(
                label="Download full",
                data=json.dumps(candidate.model_dump(), indent=2, ensure_ascii=False).encode(),
                file_name="candidate_full.json",
                mime="application/json",
                use_container_width=True,
                key="dl_full",
            )
        with col_a:
            st.markdown(
                '<div style="font-size:0.8125rem; color:#6B7280; padding-bottom:0.5rem;">'
                'Complete canonical Candidate with all provenance entries.</div>',
                unsafe_allow_html=True,
            )
        st.json(candidate.model_dump())


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    csv_file, pdf_file, github_input, config_choice, custom_config_str, generate_clicked = (
        _render_input_panel()
    )

    def get_config() -> Optional[dict]:
        if config_choice == "Paste JSON" and custom_config_str.strip():
            try:
                return json.loads(custom_config_str)
            except json.JSONDecodeError as e:
                _notice(f"Invalid config JSON: {e}", "error")
                return None
        elif config_choice == "Custom":
            return load_config("configs/custom_config.json")
        return load_config("configs/default_config.json")

    # ── Detect file changes and auto-clear stale results ──────────────────
    # Build a fingerprint from currently uploaded files + github input so we
    # can tell when the user has swapped to a different candidate.
    current_fingerprint = "|".join([
        f"{csv_file.name}:{csv_file.size}" if csv_file else "",
        f"{pdf_file.name}:{pdf_file.size}" if pdf_file else "",
        github_input.strip(),
    ])
    if st.session_state.get("_input_fingerprint") != current_fingerprint:
        # Inputs changed — wipe previous results so they don't bleed through
        for _k in ("candidate", "output", "_input_fingerprint"):
            st.session_state.pop(_k, None)
    # Also clear stored config so stale config doesn't bleed through
    st.session_state.pop("output_config", None)

    if generate_clicked:
        if not any([csv_file, pdf_file, github_input.strip()]):
            _notice(
                "No input provided. Upload a CSV, a resume PDF, "
                "or enter a GitHub username to generate a profile.",
                "warning",
            )
        else:
            config = get_config()
            if config is not None:
                # Clear any previously stored results before running fresh
                st.session_state.pop("candidate", None)
                st.session_state.pop("output", None)

                csv_path    = None
                resume_path = None

                with tempfile.TemporaryDirectory() as tmpdir:
                    if csv_file:
                        csv_path = os.path.join(tmpdir, "upload.csv")
                        # Seek to start in case the file was already read
                        csv_file.seek(0)
                        pathlib.Path(csv_path).write_bytes(csv_file.read())

                    if pdf_file:
                        resume_path = os.path.join(tmpdir, "resume.pdf")
                        pdf_file.seek(0)
                        pathlib.Path(resume_path).write_bytes(pdf_file.read())

                    with st.spinner("Processing..."):
                        try:
                            candidate, output = run_pipeline(
                                csv_path=csv_path,
                                resume_path=resume_path,
                                github_url=github_input.strip() or None,
                                config_dict=config,
                            )
                            st.session_state["candidate"]          = candidate
                            st.session_state["output"]             = output
                            st.session_state["output_config"]      = config
                            st.session_state["_input_fingerprint"] = current_fingerprint
                        except ValueError as e:
                            _notice(str(e), "error")
                        except Exception as e:
                            _notice(
                                f"Processing error: {e}. Check that your files are valid.",
                                "error",
                            )

    if "candidate" not in st.session_state:
        _divider()
        _notice("Upload at least one source above and click Generate Profile to begin.", "info")
        return

    candidate     = st.session_state["candidate"]
    output        = st.session_state["output"]
    output_config = st.session_state.get("output_config", load_config())

    _divider()
    tab_profile, tab_json = st.tabs(["Profile", "JSON"])
    with tab_profile:
        _render_profile_tab(candidate, output, output_config)
    with tab_json:
        _render_json_tab(candidate, output)


if __name__ == "__main__":
    main()