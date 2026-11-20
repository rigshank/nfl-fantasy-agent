"""Presentation for measured waiver evidence; no changes to player evaluation."""
from html import escape
from math import isfinite

from .roster_cards import STYLE as PLAYER_STYLE, player_card


STYLE = """<style>
.ff-waiver-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,350px),1fr));gap:12px}.ff-waiver-card{min-width:0;padding:16px;border:1px solid #2b4d60;border-radius:14px;background:linear-gradient(125deg,#132c3d,#0b1b28)}
.ff-waiver-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px;font-size:.68rem;color:#91bdcb}.ff-waiver-rank{color:#62ded3;font-weight:750;letter-spacing:.07em}.ff-waiver-tag{border:1px solid #35586a;border-radius:5px;padding:3px 7px;color:#b9cfda}.ff-waiver-card .ff-player{border:0;box-shadow:none;padding:0;background:none;gap:12px;margin-bottom:14px}.ff-waiver-card .ff-portrait{flex-basis:52px;height:60px;font-size:1rem}.ff-waiver-card .ff-player-name{font-size:.94rem}.ff-waiver-card .ff-player-id{font-size:.58rem}.ff-waiver-card .ff-health{font-size:.65rem;margin-top:5px}
.ff-waiver-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.ff-waiver-stat{border:1px solid #274655;background:#0a1e2a;border-radius:8px;padding:11px;min-width:0}.ff-waiver-stat small{display:block;color:#9fbaca;font-size:.63rem;line-height:1.45;margin-bottom:5px}.ff-waiver-value{font-size:1.1rem;font-weight:750;color:#e7f5fa;font-variant-numeric:tabular-nums}.ff-waiver-stat em{display:block;font-style:normal;font-size:.63rem;color:#94afbe;line-height:1.5;margin-top:4px}.ff-waiver-positive{color:#66e1c1}.ff-waiver-negative{color:#f3acb4}.ff-waiver-drop{margin:12px 0 0;padding:10px 12px;border-left:2px solid #d8aa74;background:#302c253d;font-size:.77rem;color:#dce9ef;border-radius:0 6px 6px 0}.ff-waiver-drop small{color:#b8a48c;margin-right:8px}.ff-waiver-note{font-size:.72rem;color:#a0bbcb;line-height:1.6;margin:10px 0 0}.ff-waiver-card details{margin-top:12px;border-top:1px solid #294858;padding-top:10px;font-size:.74rem;color:#b0c8d5}.ff-waiver-card summary{cursor:pointer;color:#6fddd7}.ff-waiver-card details p{font-size:.74rem;margin:8px 0;color:#b0c8d5}.ff-waiver-scorebar{height:4px;background:#294452;border-radius:3px;overflow:hidden;margin:10px 0}.ff-waiver-scorebar span{display:block;height:100%;background:linear-gradient(90deg,#2195c1,#50dcc6)}
.ff-evidence-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr));gap:10px}.ff-evidence-title{font-size:.73rem;color:#67ddd1;margin-bottom:10px;letter-spacing:.03em}.ff-usage-values{display:flex;justify-content:space-between;align-items:center;gap:8px;font-variant-numeric:tabular-nums}.ff-usage-values small{display:block;color:#9cb7c8;font-size:.62rem;margin-bottom:5px}.ff-week-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:10px}.ff-week-head{display:flex;justify-content:space-between;align-items:center;font-size:.85rem;color:#dff5fa;margin-bottom:10px}.ff-week-field{display:flex;justify-content:space-between;gap:12px;padding:5px 0;font-size:.7rem;color:#aac2d0;border-bottom:1px solid #24414f}.ff-week-field:last-child{border:0}
@media(max-width:500px){.ff-waiver-card{padding:12px}.ff-waiver-stat{padding:8px}.ff-waiver-value{font-size:.96rem}}
</style>"""


def fmt(value, signed=False, share=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
        return '—'
    if share:
        return f'{value * 100:+.1f} pp' if signed else f'{value:.1%}'
    return f'{value:+,.2f}' if signed else f'{value:,.2f}'


def tone(value):
    return 'ff-waiver-positive' if isinstance(value, (int, float)) and value > 0 else 'ff-waiver-negative' if isinstance(value, (int, float)) and value < 0 else ''


def stat(label, value, note='', css=''):
    return f'<div class="ff-waiver-stat"><small>{escape(label)}</small><div class="ff-waiver-value {css}">{escape(value)}</div>{"<em>" + escape(note) + "</em>" if note else ""}</div>'


def details(label, paragraphs):
    return '<details><summary>' + escape(label) + '</summary>' + ''.join('<p>' + escape(str(p)) + '</p>' for p in paragraphs) + '</details>'


def pickup_cards(snapshot, pickups, offset=0):
    cards = []
    for rank, pickup in enumerate(pickups, offset + 1):
        bid = pickup.faab.get('range')
        bid_text = '–'.join(str(x) for x in bid) if bid is not None else 'Not established'
        metrics = ''.join([
            stat('Next-week lineup Δ', fmt(pickup.next_week_gain, True), 'Model estimate', tone(pickup.next_week_gain)),
            stat('ROS lineup Δ', fmt(pickup.ros_gain, True), 'Model estimate', tone(pickup.ros_gain)),
            stat('FAAB range', bid_text, 'Subjective bid guidance'),
        ])
        drop = snapshot.players[pickup.drop_id].name if pickup.drop_id else 'Open roster spot · no drop needed'
        extra = [f'Bench surplus Δ: {fmt(pickup.bench_change, True)}', f'Dynasty index Δ: {fmt(pickup.dynasty_change, True)}',
                 f'Opportunity signal: {fmt(pickup.breakout_score)} / 100 (heuristic, not probability)']
        extra += pickup.reasons + ['Risk: ' + x for x in pickup.risks]
        extra += [pickup.faab[k] for k in ('basis', 'limitation') if pickup.faab.get(k)]
        cards.append(f'<article class="ff-waiver-card"><div class="ff-waiver-top"><span class="ff-waiver-rank">#{rank:02d} · {escape(pickup.kind)}</span><span class="ff-waiver-tag">{escape(pickup.confidence.title())} confidence</span></div>'
                     + player_card(snapshot.players[pickup.player_id], 'ADD')
                     + '<div class="ff-waiver-stats">' + metrics + '</div>'
                     + f'<div class="ff-waiver-drop"><small>{"DROP" if pickup.drop_id else "ROSTER MOVE"}</small>{escape(drop)}</div>'
                     + details('Why this move · value and risks', extra) + '</article>')
    return PLAYER_STYLE + STYLE + '<div class="ff-waiver-grid">' + ''.join(cards) + '</div>'


def signal_cards(snapshot, signals, offset=0):
    cards = []
    for rank, signal in enumerate(signals, offset + 1):
        metrics = {c.metric: c for c in signal.changes}
        opportunity = metrics.get('opportunities')
        snap = metrics.get('snap_share')
        stats = stat('Opportunity / game', fmt(opportunity.recent if opportunity else None),
                     'Prior: ' + fmt(opportunity.prior if opportunity else None))
        stats += stat('Snap-share change', fmt(snap.change if snap else None, True, True), 'Percentage points')
        stats += stat('Verified games', f'{signal.prior_games} → {signal.recent_games}', 'Prior → recent window')
        cards.append(f'<article class="ff-waiver-card"><div class="ff-waiver-top"><span class="ff-waiver-rank">#{rank:02d} · OPPORTUNITY WATCH</span><span class="ff-waiver-tag">{escape(signal.confidence.title())} confidence</span></div>'
                     + player_card(snapshot.players[signal.player_id])
                     + f'<div class="ff-week-head"><span>{escape(signal.label)}</span><strong>{fmt(signal.score)} / 100</strong></div>'
                     + f'<div class="ff-waiver-scorebar" aria-hidden="true"><span style="width:{max(0, min(100, signal.score)):.2f}%"></span></div>'
                     + '<div class="ff-waiver-stats">' + stats + '</div>'
                     + details('Why watch · evidence and uncertainty', signal.reasons + signal.limitations) + '</article>')
    return PLAYER_STYLE + STYLE + '<div class="ff-waiver-grid">' + ''.join(cards) + '</div>'


def ppg_cards(value):
    return STYLE + '<div class="ff-evidence-grid">' + ''.join([
        stat('Season fantasy PPG', fmt(value.season_ppg), f'Observed · {value.games} verified games'),
        stat('Recent fantasy PPG', fmt(value.recent_ppg), 'Observed recent appearances'),
        stat('Forecast fantasy PPG', fmt(value.projected_ppg), 'Prediction · uncalibrated'),
    ]) + '</div>'


def usage_cards(signal):
    cards = []
    for change in signal.changes:
        share = change.metric.endswith('_share')
        label = change.metric.replace('_', ' ').title()
        cards.append(f'<article class="ff-waiver-card"><div class="ff-evidence-title">{escape(label)}{" · / game" if not share else ""}</div><div class="ff-usage-values">'
                     + f'<div><small>PRIOR · {signal.prior_games} GAMES</small>{fmt(change.prior, share=share)}</div><span>→</span><div><small>RECENT · {signal.recent_games} GAMES</small>{fmt(change.recent, share=share)}</div></div>'
                     + f'<p class="ff-waiver-note {tone(change.change)}">Change: {fmt(change.change, True, share)}</p></article>')
    return STYLE + '<div class="ff-evidence-grid">' + ''.join(cards) + '</div>'


def weekly_cards(rows):
    cards = []
    for row in sorted(rows, key=lambda r: r['week'], reverse=True):
        fields = ''.join(f'<div class="ff-week-field"><span>{escape(k.replace("_", " ").title())}</span><strong>{fmt(v, share=k.endswith("_share"))}</strong></div>'
                         for k, v in row.items() if k not in {'week', 'fantasy_points'})
        cards.append(f'<article class="ff-waiver-card"><div class="ff-week-head"><strong>Week {escape(str(row["week"]))}</strong><span>{fmt(row.get("fantasy_points"))} pts</span></div>{fields}</article>')
    return STYLE + '<div class="ff-week-grid">' + ''.join(cards) + '</div>'


def page(items, key, noun):
    """Paginate display only; every evaluated result remains accessible."""
    import streamlit as st
    size = 6
    pages = (len(items) + size - 1) // size
    index = st.selectbox(f'{noun} page', range(pages), format_func=lambda i: f'{i + 1} of {pages}', key=key) if pages > 1 else 0
    offset = index * size
    st.caption(f'Showing {offset + 1}–{min(offset + size, len(items))} of {len(items)} {noun.lower()}.')
    return items[offset:offset + size], offset


def render_player_evidence(snapshot, player_id, value, signal=None, key_prefix='waiver'):
    import streamlit as st
    import altair as alt
    import pandas as pd

    st.html(PLAYER_STYLE + STYLE + player_card(snapshot.players[player_id]))
    st.html(ppg_cards(value))
    st.caption('Fantasy points use this league’s scoring. Observed averages describe past games; forecast PPG is a model estimate, not a verified future result.')
    if signal:
        st.markdown('**Opportunity changes**')
        st.html(usage_cards(signal))
        if signal.limitations:
            with st.expander(f'Signal limitations · {len(signal.limitations)} notes'):
                for warning in signal.limitations:
                    st.caption(warning)
    if value.weekly_observed:
        with st.expander('Weekly performance · observed games', expanded=False):
            chart = alt.Chart(pd.DataFrame(value.weekly_observed)).mark_line(point=True, color='#4edacf').encode(
                x=alt.X('week:O', title='NFL week'), y=alt.Y('fantasy_points:Q', title='Observed fantasy points'),
                tooltip=['week:O', alt.Tooltip('fantasy_points:Q', format='.2f')])
            st.altair_chart(chart.properties(height=180).configure(background='transparent'), width='stretch')
            st.caption('Only verified appearances are shown; missing weeks are not filled with zeroes. Expand a page of game evidence below.')
            rows, _ = page(sorted(value.weekly_observed, key=lambda r: r['week'], reverse=True), key_prefix + '_week_page', 'Games')
            st.html(weekly_cards(rows))
    else:
        st.caption('No verified weekly game evidence is available.')
