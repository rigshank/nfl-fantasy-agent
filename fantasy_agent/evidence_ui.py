"""Compact, searchable source provenance and complete limitation disclosures."""
from html import escape
from urllib.parse import urlsplit

STYLE = """<style>
.ff-source-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:10px}.ff-source-card{border:1px solid #2b4b5c;border-radius:11px;padding:15px;background:linear-gradient(120deg,#132c3c,#0b1d29);min-width:0}.ff-source-top{display:flex;justify-content:space-between;gap:12px;align-items:start;margin-bottom:12px}.ff-source-title{color:#e5f4fa;font-size:.85rem;font-weight:700;overflow-wrap:anywhere}.ff-source-state{font-size:.6rem;white-space:nowrap;color:#82dcd1;border:1px solid #33746d;padding:3px 6px;border-radius:4px}.ff-source-stale{color:#edc591;border-color:#7a6541}.ff-source-card p{font-size:.72rem;color:#a7c1d0;margin:6px 0;line-height:1.6}.ff-source-card a{display:inline-block;margin-top:9px;font-size:.73rem;color:#64e0d6!important;overflow-wrap:anywhere}.ff-source-card details{font-size:.75rem;color:#b3ccda}.ff-source-card summary{cursor:pointer;color:#d8e9f1;font-size:.77rem;line-height:1.6;overflow-wrap:anywhere}.ff-source-card details p{white-space:pre-wrap}
</style>"""


def source_cards(sources):
    from .ui import local_time
    cards = []
    for source in sources:
        parsed = urlsplit(source.url)
        link = f'<a href="{escape(source.url, quote=True)}" target="_blank" rel="noopener noreferrer">Open source ↗ · {escape(parsed.netloc)}</a>' if parsed.scheme in {'http', 'https'} and parsed.netloc else '<p>Source link unavailable</p>'
        cards.append(f'<article class="ff-source-card"><div class="ff-source-top"><div class="ff-source-title">{escape(source.name)}</div><span class="ff-source-state {"ff-source-stale" if source.stale else ""}">{"STALE CACHE" if source.stale else "RETRIEVED"}</span></div>'
                     + f'<p>Retrieved · {escape(local_time(source.retrieved_at))}</p><p>Source update · {escape(source.source_updated_at or "Not provided; inspect the source’s data dates")}</p>{link}</article>')
    return STYLE + '<div class="ff-source-grid">' + ''.join(cards) + '</div>'


def limitation_cards(warnings):
    cards = []
    for warning in warnings:
        summary = warning.splitlines()[0]
        if len(summary) > 115:
            summary = summary[:112] + '…'
        cards.append('<article class="ff-source-card"><details><summary>' + escape(summary)
                     + '</summary><p>' + escape(warning) + '</p></details></article>')
    return STYLE + '<div class="ff-source-grid">' + ''.join(cards) + '</div>'


def render_sources(sources, warnings, key_prefix):
    import streamlit as st
    with st.expander(f'Sources and limitations · {len(sources)} sources · {len(warnings)} notes'):
        query = st.text_input('Search evidence sources or limitations', placeholder='Source, date, missing data, caveat…', key=key_prefix + '_source_search').strip().casefold()
        matching_sources = [s for s in sources if query in ' '.join([s.name, s.url, s.source_updated_at or '', s.retrieved_at.isoformat(), 'stale cache' if s.stale else 'retrieved']).casefold()]
        matching_warnings = [w for w in warnings if query in w.casefold()]
        source_tab, note_tab = st.tabs([f'Sources ({len(matching_sources)})', f'Limitations ({len(matching_warnings)})'])
        with source_tab:
            st.caption('Retrieval time is when the app fetched the data; it does not establish when the underlying statistics were updated.')
            if matching_sources:
                st.html(source_cards(matching_sources))
            else:
                st.caption('No sources match this search.' if query else 'No source provenance was returned.')
        with note_tab:
            if matching_warnings:
                st.caption('Expand a note to read its full text.')
                st.html(limitation_cards(matching_warnings))
            else:
                st.caption('No limitations match this search.' if query else 'No additional source limitations were reported. This does not establish predictive accuracy.')
