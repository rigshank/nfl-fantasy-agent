"""Compact snapshot standings, without inferring official playoff seeds."""
from html import escape
from math import isfinite

from .matchup_cards import STYLE as AVATAR_STYLE, avatar, record


STYLE = """<style>
.ff-standing-list{display:grid;gap:8px}.ff-standing-row{display:grid;grid-template-columns:36px minmax(160px,1fr) repeat(4,minmax(75px,.4fr));gap:14px;align-items:center;padding:13px 16px;border:1px solid #294858;border-radius:12px;background:linear-gradient(110deg,#122b3b,#0b1c29)}
.ff-standing-row.ff-standing-mine{border-color:#35bbae;background:linear-gradient(110deg,#123b3c,#0d2433)}.ff-standing-rank{font-size:1.1rem;font-weight:800;color:#74c8d3}.ff-standing-team{display:flex;align-items:center;gap:12px;min-width:0}.ff-standing-team .ff-avatar{width:42px;height:42px;flex:0 0 42px;font-size:.85rem;margin:0}.ff-standing-name{font-size:.87rem;font-weight:650;color:#eff7fb;overflow-wrap:anywhere}.ff-standing-you{font-size:.57rem;letter-spacing:.08em;border:1px solid #308d82;color:#7aebd5;border-radius:4px;padding:2px 5px;margin-left:6px;white-space:nowrap}.ff-standing-stat{text-align:right;font-size:.86rem;font-variant-numeric:tabular-nums;color:#e4f0f6}.ff-standing-label{display:block;font-size:.6rem;letter-spacing:.05em;color:#9cb6c7;margin-bottom:4px}.ff-standing-positive{color:#64e0ba}.ff-standing-negative{color:#f2a5af}.ff-standing-track{height:3px;background:#284453;border-radius:3px;margin-top:7px;overflow:hidden}.ff-standing-fill{height:100%;background:#42cec6}
@media(max-width:700px){.ff-standing-row{grid-template-columns:28px minmax(0,1fr) 85px;gap:10px;padding:12px}.ff-standing-extra{grid-row:2}.ff-standing-pf{grid-column:1/3;text-align:left}.ff-standing-pa{grid-column:3}.ff-standing-diff{display:none}}
</style>"""


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) else None


def total(settings, key):
    base = number(settings.get(key))
    decimal = number(settings.get(key + "_decimal", 0))
    return base + decimal / 100 if base is not None and decimal is not None else None


def ordered_teams(snapshot):
    # Preserve the existing wins / points-for ordering; absent values sort last.
    return sorted(snapshot.rosters, key=lambda r: (
        number(r.settings.get('wins')) if number(r.settings.get('wins')) is not None else -1,
        total(r.settings, 'fpts') if total(r.settings, 'fpts') is not None else float('-inf'),
    ), reverse=True)


def standings_html(snapshot, selected_id=None, query=""):
    rows = []
    last_key = None
    rank = 0
    for index, team in enumerate(ordered_teams(snapshot), 1):
        pf, pa = total(team.settings, 'fpts'), total(team.settings, 'fpts_against')
        key = (number(team.settings.get('wins')), pf)
        if key != last_key or index == 1:
            rank = index
        last_key = key
        if query.casefold().strip() not in team.manager.casefold():
            continue
        values = [number(team.settings.get(k)) for k in ('wins', 'losses', 'ties')]
        games = sum(values) if all(v is not None and v >= 0 for v in values) else 0
        percentage = (values[0] + values[2] / 2) / games if games else None
        track = '' if percentage is None else f'<div class="ff-standing-track" aria-label="Win percentage {percentage:.1%}"><div class="ff-standing-fill" style="width:{percentage * 100:.2f}%"></div></div>'
        pct = f' · {percentage:.0%}' if percentage is not None else ''
        mine = team.roster_id == selected_id
        difference = pf - pa if pf is not None and pa is not None else None
        diff_class = 'ff-standing-positive' if difference is not None and difference > 0 else 'ff-standing-negative' if difference is not None and difference < 0 else ''
        fmt = lambda value: f'{value:,.2f}' if value is not None else '—'
        rows.append(f'''<article class="ff-standing-row {'ff-standing-mine' if mine else ''}">
<div class="ff-standing-rank">{rank:02d}</div>
<div class="ff-standing-team">{avatar(team)}<div class="ff-standing-name">{escape(team.manager)}{'<span class="ff-standing-you">YOUR TEAM</span>' if mine else ''}</div></div>
<div class="ff-standing-stat"><span class="ff-standing-label">W–L–T{pct}</span>{record(team)}{track}</div>
<div class="ff-standing-stat ff-standing-extra ff-standing-pf"><span class="ff-standing-label">POINTS FOR</span>{fmt(pf)}</div>
<div class="ff-standing-stat ff-standing-extra ff-standing-pa"><span class="ff-standing-label">POINTS AGAINST</span>{fmt(pa)}</div>
<div class="ff-standing-stat ff-standing-diff {diff_class}"><span class="ff-standing-label">DIFFERENTIAL</span>{f'{difference:+,.2f}' if difference is not None else '—'}</div>
</article>''')
    return AVATAR_STYLE + STYLE + '<div class="ff-standing-list">' + ''.join(rows) + '</div>'


def render_standings(snapshot, selected_id=None):
    import streamlit as st

    st.caption('Record order · Wins, then points for. Custom standings and playoff tiebreakers are not modeled. Values reflect the last league refresh.')
    query = st.text_input('Find a team', placeholder='Search team or manager name', key='overview_standings_search')
    if not snapshot.rosters:
        st.info('No team records were returned. Refresh the league to try again.')
    elif not any(query.casefold().strip() in r.manager.casefold() for r in snapshot.rosters):
        st.caption('No matching teams. Clear the search to see the league.')
    else:
        st.html(standings_html(snapshot, selected_id, query))
    with st.expander('How to read these standings'):
        st.caption('Win percentage counts a tie as half a win. Points against and differential describe scoring history, not team strength or projections. Missing data appears as —. Equal wins and points share a displayed rank; this is not an official playoff seed.')
