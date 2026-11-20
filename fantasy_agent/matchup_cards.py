"""Snapshot scoreboards and team summaries; no predictions or API credentials."""
from collections import defaultdict
from html import escape
import re

STYLE="""<style>
.ff-match-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,390px),1fr));gap:15px}.ff-match{padding:20px;border:1px solid #2d4d61;border-radius:15px;background:linear-gradient(130deg,#142d3e,#0b1925)}
.ff-match-label{font-size:.64rem;letter-spacing:.14em;color:#68d9d2;text-transform:uppercase;margin-bottom:16px}.ff-versus{display:grid;grid-template-columns:1fr 28px 1fr;gap:10px;align-items:center}.ff-team{text-align:center;min-width:0}.ff-team h4{font-size:.94rem;line-height:1.4;overflow-wrap:anywhere;margin:9px 0 4px;color:#eff7fb}.ff-vs{font-size:.7rem;color:#799bad;text-align:center}.ff-record{font-size:.72rem;color:#9bb5c7}.ff-score{font-size:2.2rem;font-weight:800;letter-spacing:-.04em;color:#f1f7fb;margin-top:8px}.ff-leading .ff-score{color:#59e1c9}
.ff-avatar{width:65px;height:65px;position:relative;display:grid;place-items:center;margin:auto;border-radius:50%;border:1px solid #3c697a;background:#153646;color:#89d3dc;font-weight:800;font-size:1.25rem;overflow:hidden}.ff-avatar:after{content:"";position:absolute;inset:0;background-image:var(--avatar);background-size:cover;background-position:center}
.ff-match-note{margin-top:16px;border-top:1px solid #294453;padding-top:11px;font-size:.73rem;color:#9dbaca;text-align:center}.ff-record-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:12px}.ff-record-card{padding:17px;background:#102332;border:1px solid #274758;border-radius:12px;display:flex;gap:13px;align-items:center}.ff-record-card .ff-avatar{width:48px;height:48px;flex:0 0 48px;font-size:1rem}.ff-record-card h4{font-size:.86rem;margin:0 0 6px;overflow-wrap:anywhere;color:#eff7fb}.ff-record-card p{font-size:.73rem;color:#9dbaca;margin:3px 0}.ff-record-rank{color:#55dacf;font-size:.69rem;letter-spacing:.08em;margin-bottom:4px}
</style>"""


def avatar(roster):
    raw=roster.avatar or ""
    if re.fullmatch(r"[a-zA-Z0-9_-]+",raw):url="https://sleepercdn.com/avatars/thumbs/"+raw
    elif re.fullmatch(r"https://sleepercdn\.com/[a-zA-Z0-9_./-]+",raw):url=raw
    else:url=""
    initials="".join(x[0] for x in roster.manager.split()[:2]) or "?"
    return f'<div class="ff-avatar" role="img" aria-label="{escape(roster.manager,quote=True)} team avatar" style="--avatar:url(\'{url}\')">{escape(initials)}</div>'


def record(roster):
    return escape(" – ".join(str(roster.settings.get(k,"—")) for k in ("wins","losses","ties")))


def points(matchup):
    return matchup.get("custom_points") if matchup.get("custom_points") is not None else matchup.get("points")


def scoreboard(snapshot):
    teams={r.roster_id:r for r in snapshot.rosters};groups=defaultdict(list)
    for i,m in enumerate(snapshot.matchups):groups[('match',m['matchup_id']) if m.get('matchup_id') is not None else ('unpaired',i)].append(m)
    cards=[]
    for key,entries in groups.items():
        valid=[m for m in entries if m.get('roster_id') in teams]
        paired=len(entries)==2 and len(valid)==2 and key[0]=='match'
        scores=[points(m) for m in valid]
        known=paired and all(isinstance(v,(int,float)) for v in scores)
        note='Scores as of league refresh'
        if known:
            delta=abs(scores[0]-scores[1]);note=f'Snapshot lead: {delta:.2f} points' if delta else 'Level on points at this snapshot'
        elif not paired:note='Opponent pairing unavailable in this snapshot'
        sides=[]
        for i,m in enumerate(valid):
            team=teams[m['roster_id']];score=points(m)
            value=f'{score:.2f}' if isinstance(score,(int,float)) else '—'
            leading=known and scores[i]>scores[1-i]
            sides.append(f'<div class="ff-team {"ff-leading" if leading else ""}">{avatar(team)}<h4>{escape(team.manager)}</h4><div class="ff-record">{record(team)} · W–L–T</div><div class="ff-score">{value}</div>{"<div class=ff-record>Commissioner score</div>" if m.get("custom_points") is not None else ""}</div>')
        body='<div class="ff-vs">VS</div>'.join(sides)
        layout='ff-versus' if paired else ''
        cards.append(f'<article class="ff-match"><div class="ff-match-label">Week {snapshot.week} · {"Head to head" if paired else "Unpaired team"}</div><div class="{layout}">{body}</div><div class="ff-match-note">{note}</div></article>')
    return STYLE+'<div class="ff-match-grid">'+''.join(cards)+'</div>'


def team_records(snapshot):
    ordered=sorted(snapshot.rosters,key=lambda r:(r.settings.get('wins',0),r.settings.get('fpts',0)+r.settings.get('fpts_decimal',0)/100),reverse=True)
    cards=[]
    for i,team in enumerate(ordered,1):
        pf=team.settings.get('fpts');total=f"{pf+team.settings.get('fpts_decimal',0)/100:,.2f}" if isinstance(pf,(int,float)) else '—'
        cards.append(f'<article class="ff-record-card">{avatar(team)}<div><div class="ff-record-rank">#{i:02d} · RECORD ORDER</div><h4>{escape(team.manager)}</h4><p>{record(team)} · W–L–T</p><p>Points for <strong>{total}</strong></p></div></article>')
    return STYLE+'<div class="ff-record-grid">'+''.join(cards)+'</div>'
