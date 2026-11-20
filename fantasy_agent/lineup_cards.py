"""Visual lineup assignments and comparisons; calculations stay in LineupService."""
from datetime import datetime
from html import escape

from .roster_cards import STYLE as PLAYER_STYLE, player_card
from .waiver_cards import STYLE as METRIC_STYLE, fmt, stat, details, tone

STYLE = """<style>
.ff-lineup-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,285px),1fr));gap:12px}.ff-lineup-card{padding:15px;border:1px solid #2a4c60;border-radius:13px;background:linear-gradient(120deg,#142e3f,#0b1b29);min-width:0}.ff-lineup-head{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:13px}.ff-lineup-slot{color:#64e0d3;font-weight:800;font-size:.78rem;letter-spacing:.07em}.ff-lineup-state{font-size:.61rem;color:#a9c4d3;background:#102735;border:1px solid #38576a;padding:3px 7px;border-radius:5px}.ff-lineup-change{color:#78e2c8;border-color:#348271}.ff-lineup-lock{color:#eed19d;border-color:#776543}.ff-lineup-card .ff-player{padding:0;background:none;box-shadow:none;border:0;gap:11px;margin-bottom:12px}.ff-lineup-card .ff-portrait{flex-basis:48px;height:57px;font-size:1rem}.ff-lineup-card .ff-player-name{font-size:.88rem}.ff-lineup-card .ff-player-meta{font-size:.68rem}.ff-lineup-card .ff-health{font-size:.63rem}.ff-lineup-card .ff-player-id{font-size:.58rem}.ff-lineup-match{font-size:.71rem;color:#a9c4d4;line-height:1.7;margin:9px 0}.ff-lineup-card details{border-top:1px solid #294957;margin-top:12px;padding-top:10px}.ff-lineup-card summary{color:#6bded3;cursor:pointer;font-size:.73rem}.ff-lineup-card details p{font-size:.73rem;color:#aac4d3;line-height:1.6}.ff-lineup-empty{border:1px dashed #536678;padding:19px;border-radius:9px;color:#a8c1d1;font-size:.78rem;margin-bottom:12px}.ff-lineup-compare{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,410px),1fr));gap:12px}.ff-lineup-versus{display:grid;grid-template-columns:1fr 1fr;gap:16px}.ff-lineup-versus>div{min-width:0}.ff-lineup-side{font-size:.6rem;letter-spacing:.1em;color:#8eb2c4;margin-bottom:10px}.ff-lineup-versus .ff-player{display:block}.ff-lineup-versus .ff-portrait{width:48px;margin-bottom:8px}.ff-lineup-compare .ff-waiver-stats{grid-template-columns:repeat(3,minmax(0,1fr))}.ff-lineup-compare .ff-waiver-value{font-size:1rem}
</style>"""


def kickoff_text(value):
    if not value:
        return 'Kickoff unverified'
    try:
        from .ui import local_time
        stamp = datetime.fromisoformat(value)
        return local_time(stamp) if stamp.tzinfo else value + ' · timezone unverified'
    except (ValueError, TypeError):
        return str(value) + ' · unverified'


def identity(players, pid):
    if pid in (None, '0'):
        return '<div class="ff-lineup-empty">Unfilled slot</div>'
    player = players.get(pid)
    return player_card(player) if player else f'<div class="ff-lineup-empty">Player details unavailable · ID {escape(str(pid))}</div>'


def state(slot):
    if slot.locked:
        return 'Locked / unverified', 'ff-lineup-lock'
    return ('Suggested swap', 'ff-lineup-change') if slot.current_id != slot.recommended_id else ('Keep starter', '')


def starting_cards(report, players):
    cards = []
    for slot in report.slots:
        label, css = state(slot)
        cards.append(f'<article class="ff-lineup-card"><div class="ff-lineup-head"><span class="ff-lineup-slot">{escape(slot.slot)} · {slot.index + 1:02d}</span><span class="ff-lineup-state {css}">{label}</span></div>'
                     + identity(players, slot.recommended_id)
                     + stat('Expected points', fmt(slot.estimate), 'Statistical estimate · not live scoring')
                     + f'<div class="ff-lineup-match">Opponent · {escape(slot.opponent or "Unverified")}<br>{escape(kickoff_text(slot.kickoff))}</div>'
                     + details('Start / sit reasoning', [slot.reason]) + '</article>')
    return PLAYER_STYLE + METRIC_STYLE + STYLE + '<div class="ff-lineup-grid">' + ''.join(cards) + '</div>'


def comparison_cards(report, players):
    cards = []
    for slot in report.slots:
        label, css = state(slot)
        gain = slot.estimate - slot.current_estimate if not slot.locked and slot.estimate is not None and slot.current_estimate is not None else None
        metrics = stat('Saved estimate', fmt(slot.current_estimate)) + stat('Recommended estimate', fmt(slot.estimate)) + stat('Slot difference', fmt(gain, True), 'Not a full-lineup gain', tone(gain))
        cards.append(f'<article class="ff-lineup-card"><div class="ff-lineup-head"><span class="ff-lineup-slot">{escape(slot.slot)} · {slot.index + 1:02d}</span><span class="ff-lineup-state {css}">{label}</span></div>'
                     + '<div class="ff-lineup-versus"><div><div class="ff-lineup-side">SAVED STARTER</div>' + identity(players, slot.current_id)
                     + '</div><div><div class="ff-lineup-side">RECOMMENDED</div>' + identity(players, slot.recommended_id) + '</div></div>'
                     + '<div class="ff-waiver-stats">' + metrics + '</div>'
                     + f'<div class="ff-lineup-match">Opponent · {escape(slot.opponent or "Unverified")}<br>{escape(kickoff_text(slot.kickoff))}</div>'
                     + details('Decision evidence · strategy score', [slot.reason, f'Strategy score: {fmt(slot.objective)}. Optimizer objective for the selected strategy; this can differ from expected points.',
                         'Locked or unverified slots do not show a comparable slot gain.' if slot.locked else 'Assignments across all eligible slots were optimized together.']) + '</article>')
    return PLAYER_STYLE + METRIC_STYLE + STYLE + '<div class="ff-lineup-compare">' + ''.join(cards) + '</div>'


def evidence_rows(evidence, query=''):
    from .rules_ui import leaves, display, matches
    return [(k, v) for k, v in leaves(evidence) if matches(query, k, display(v))]


def render_evidence(report, players):
    import streamlit as st
    from .evidence_ui import source_cards, limitation_cards
    from .rules_ui import STYLE as FIELD_STYLE, fields_html

    with st.expander(f'Evidence and limitations · {len(report.sources)} sources · {len(report.warnings)} notes'):
        query = st.text_input('Search lineup evidence', placeholder='Player name, source, scoring field, injury, missing data…', key='lineup_evidence_search').strip().casefold()
        sources = [s for s in report.sources if query in f'{s.name} {s.url} {s.source_updated_at or ""} {s.retrieved_at.isoformat()} {"stale cache" if s.stale else "retrieved"}'.casefold()]
        warnings = [w for w in report.warnings if query in w.casefold()]
        matches = {}
        for pid, evidence in report.evidence.items():
            player = players.get(pid)
            name = player.name if player else str(pid)
            rows = evidence_rows(evidence, '' if query in f'{name} {pid}'.casefold() else query)
            if rows:
                matches[pid] = (name, rows)
        provenance, notes, data = st.tabs([f'Sources ({len(sources)})', f'Limitations ({len(warnings)})', f'Player evidence ({len(matches)})'])
        with provenance:
            st.caption('Retrieval time describes the fetch, not the date of every underlying statistic. Catalog injury flags do not establish game-day clearance.')
            if sources:st.html(source_cards(sources))
            else:st.caption('No matching sources.' if query else 'No source provenance returned.')
        with notes:
            if warnings:st.html(limitation_cards(warnings))
            else:st.caption('No matching notes.' if query else 'No additional limitations reported; estimates remain uncertain.')
        with data:
            if matches:
                pid = st.selectbox('Inspect player evidence', list(matches), format_func=lambda p: f'{matches[p][0]} · ID {p}', key='lineup_evidence_player')
                _, rows = matches[pid]
                st.caption('All reported fields are searchable, including weekly forecasts, observed games and scoring assumptions. Raw field paths are retained for precise reference.')
                pages = (len(rows) + 24) // 25
                index = st.selectbox('Evidence page', range(pages), format_func=lambda i: f'{i+1} of {pages}', key='lineup_evidence_page') if pages > 1 else 0
                st.caption(f'{len(rows)} matching fields · showing {index*25+1}–{min(index*25+25,len(rows))}')
                st.html(FIELD_STYLE + fields_html(rows[index*25:index*25+25]))
            else:st.caption('No matching player evidence.' if query else 'No player evidence returned.')
