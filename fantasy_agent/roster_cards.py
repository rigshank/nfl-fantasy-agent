"""Escaped, responsive roster cards. No credentials or API clients."""
from html import escape

STYLE = """<style>
.ff-roster-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,285px),1fr));gap:12px}
.ff-player{display:flex;gap:15px;align-items:center;min-width:0;padding:17px;border:1px solid #29485c;border-radius:13px;background:linear-gradient(130deg,#132b3c,#0b1925);box-shadow:0 6px 16px #0002}
.ff-portrait{position:relative;flex:0 0 76px;height:84px;overflow:hidden;border:1px solid #31556a;border-radius:12px;background:radial-gradient(circle at 50% 30%,#225068,#10232f);display:grid;place-items:center;color:#7bc8d8;font-size:1.4rem;font-weight:750}
.ff-portrait:after{content:"";position:absolute;inset:0;background-image:var(--headshot);background-size:cover;background-position:center top}
.ff-player-copy{min-width:0;flex:1}.ff-player-name{font-size:1rem;font-weight:750;color:#f0f6fb;line-height:1.35;overflow-wrap:anywhere;margin-bottom:7px}
.ff-player-meta{display:flex;gap:7px;align-items:center;flex-wrap:wrap;color:#a8c0cf;font-size:.77rem}
.ff-position{color:#68ebdf;background:#103e43;border:1px solid #24616a;padding:2px 7px;border-radius:5px;font-size:.7rem;font-weight:750}
.ff-position-QB{color:#a3c7ff;background:#163454;border-color:#2c5485}.ff-position-WR{color:#bca8ff;background:#2a2448;border-color:#4d3e77}.ff-position-TE{color:#f1d285;background:#41351d;border-color:#6b5731}
.ff-health{font-size:.7rem;margin-top:9px;color:#9db3c2;line-height:1.4}.ff-health-flag{color:#ffd29a}.ff-player-id{font-size:.65rem;color:#7995a9;margin-top:7px;letter-spacing:.025em}.ff-slot{font-size:.63rem;color:#73c8d0;letter-spacing:.08em;text-transform:uppercase;margin-bottom:5px}
@media(max-width:500px){.ff-player{padding:13px;gap:12px}.ff-portrait{flex-basis:64px;height:74px}}
</style>"""


def player_card(player,slot=None):
    pid=str(player.player_id)
    # Only an exact numeric Sleeper ID can form a CDN URL; no name matching.
    url=f"https://sleepercdn.com/content/nfl/players/thumb/{pid}.jpg" if pid.isascii() and pid.isdecimal() else ""
    initials="".join(part[0] for part in player.name.split()[:2]) or "?"
    position=player.positions[0] if player.positions else ""
    tone=position if position in {"QB","WR","TE"} else "other"
    badges="".join(f'<span class="ff-position ff-position-{tone}">{escape(p)}</span>' for p in player.positions) or '<span class="ff-position">Unknown position</span>'
    injury=player.injury_status
    health=f"Injury: {injury}" if injury else "Injury: no catalog designation"
    slot_html=f'<div class="ff-slot">{escape(slot)}</div>' if slot else ""
    return f'''<article class="ff-player" aria-label="{escape(player.name,quote=True)}">
      <div class="ff-portrait" role="img" aria-label="{escape(player.name,quote=True)} headshot; initials if unavailable" style="--headshot:url('{url}')"><span>{escape(initials)}</span></div>
      <div class="ff-player-copy">{slot_html}<div class="ff-player-name">{escape(player.name)}</div>
      <div class="ff-player-meta">{badges}<span>{escape(player.team or "NFL team unassigned")}</span></div>
      <div class="ff-health{' ff-health-flag' if injury else ''}">{escape(health)}</div>
      <div class="ff-player-id">SLEEPER ID &nbsp; {escape(pid)}</div></div></article>'''


def roster_grid(snapshot,ids,slots=None):
    return STYLE+'<div class="ff-roster-grid">'+''.join(player_card(snapshot.players[pid],(slots or {}).get(pid)) for pid in ids if pid!='0' and pid in snapshot.players)+'</div>'
