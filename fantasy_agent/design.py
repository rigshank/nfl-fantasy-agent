"""Shared dark dashboard presentation; all values come from application evidence."""
from html import escape
import streamlit as st

ICONS = {"Overview":"◈", "My League":"♜", "Trade Finder":"⇄", "Waiver Wire":"◇", "Breakout Radar":"↗", "Lineup Optimizer":"◎", "AI Analyst":"✧", "Settings":"⚙"}
COPY = {
 "Overview": ("YOUR LEAGUE. YOUR EDGE.", "The big picture, with the evidence one click away."),
 "My League": ("LEAGUE INTELLIGENCE", "Know the rosters. Understand the competition."),
 "Trade Finder": ("BUILD A BETTER ROSTER", "Find the overlap between your needs and their incentives."),
 "Waiver Wire": ("THE NEXT OPPORTUNITY", "Available talent. Measured impact. A clear next move."),
 "Breakout Radar": ("FOLLOW THE OPPORTUNITY", "Spot growing roles before the box score tells the story."),
 "Lineup Optimizer": ("MAKE EVERY SLOT COUNT", "Your strongest legal lineup, grounded in league scoring."),
 "AI Analyst": ("YOUR PERSONAL WAR ROOM", "Ask a question. Follow the evidence. Make your move."),
 "Settings": ("MISSION CONTROL", "Connections, preferences and data freshness in one place.")}


def brand_html(snapshot=None):
    tagline = f'{snapshot.league_type.upper()} ANALYTICS' if snapshot else 'FANTASY INTELLIGENCE'
    league = ''
    if snapshot:
        league = f'<div class="sl-league"><div class="sl-league-label"><span></span> LEAGUE</div><div class="sl-league-context"><div class="sl-league-name">{escape(snapshot.name)}</div><span class="sl-format">{escape(snapshot.league_type.upper())}</span></div></div>'
    return f'''<div class="sl-brand" aria-label="Sideline · {escape(tagline,quote=True)}"><div class="sl-brand-lockup"><div class="sl-brand-mark" aria-hidden="true">🏈</div><div class="sl-brand-copy"><div class="sl-brand-name">Sideline</div><div class="sl-brand-tagline">{escape(tagline)}</div></div></div><div class="sl-brand-rule"></div>{league}</div>'''


def brand(snapshot=None):
    st.html(brand_html(snapshot))

def theme():
    st.html("""<style>
    :root {--cyan:#37e7dc;--ink:#07121d;--muted:#94aabd}
    .stApp {background:radial-gradient(ellipse at 85% 0%,#123044 0,transparent 48%),#07111b;color:#eaf2f8}
    [data-testid="stHeader"] {background:transparent}
    [data-testid="stMainBlockContainer"] {padding:2.3rem 2rem 3rem;max-width:1600px}
    [data-testid="stSidebar"] {background:linear-gradient(165deg,#0b1c29,#07111a 75%);border-right:1px solid #203c4e}
    [data-testid="stSidebar"] h1 {font-size:1.4rem;letter-spacing:-.04em}
    .sl-brand{padding:4px 0 0;margin-bottom:0}.sl-brand-lockup{display:flex;align-items:center;gap:13px;padding:3px 0 18px}.sl-brand-mark{width:57px;height:59px;flex:0 0 57px;display:grid;place-items:center;border:1.5px solid #26ddcf;border-radius:17px;background:radial-gradient(ellipse at 80% 100%,#00cbbb45,transparent 65%),linear-gradient(145deg,#103942,#071a27);box-shadow:0 0 22px #03cfc325,inset 0 0 12px #1dd7cc18;font-size:35px;line-height:1}.sl-brand-copy{min-width:0}.sl-brand-name{font-size:2rem;font-weight:850;letter-spacing:-.055em;color:#f3f8fc;line-height:1.12}.sl-brand-tagline{font-size:.5rem;letter-spacing:.19em;font-weight:650;color:#9ebdce;margin-top:8px;line-height:1.5}.sl-brand-rule{height:1px;background:linear-gradient(90deg,#254251,#3ccebd,#254251);opacity:.8}.sl-league{margin-top:12px;padding:10px 12px;border:1px solid #284653;border-radius:10px;background:#102b353d}.sl-league-label{display:flex;gap:7px;align-items:center;font-size:.55rem;font-weight:650;letter-spacing:.19em;color:#9ebfce;margin-bottom:6px}.sl-league-label span{width:6px;height:6px;background:#3ae0c4;border-radius:50%;box-shadow:0 0 8px #36d9c655}.sl-league-context{display:flex;align-items:center;justify-content:flex-start;gap:10px;flex-wrap:wrap}.sl-league-name{font-size:1.13rem;font-weight:750;letter-spacing:-.025em;color:#eaf5fa;line-height:1.4;overflow-wrap:anywhere;min-width:0}.sl-format{color:#52decc;border:1px solid #2c998e;border-radius:20px;font-size:.55rem;letter-spacing:.1em;font-weight:700;padding:4px 8px;white-space:nowrap}
    [data-testid="stSidebar"] [role="radiogroup"] {gap:5px;margin:18px 0 24px}
    [data-testid="stSidebar"] [role="radiogroup"] label {padding:10px 12px;border:1px solid transparent;border-radius:10px;width:100%;transition:background .15s}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {background:linear-gradient(100deg,#087c80aa,#133044);border-color:#36dbd878;box-shadow:inset 3px 0 #39eee0}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {background:#173144}
    h1,h2,h3 {letter-spacing:-.035em} h3 {font-size:1.05rem!important}
    [data-testid="stCaptionContainer"] {color:#9aafc0;line-height:1.6}
    [data-testid="stMetric"] {background:linear-gradient(135deg,#16304799,#0d1b28);border:1px solid #2a4a60;border-radius:13px;padding:17px 20px;min-height:115px;box-shadow:0 8px 24px #0002}
    [data-testid="stMetricLabel"] {color:#b0c8d7;font-size:.82rem}
    [data-testid="stMetricValue"] {font-weight:750;letter-spacing:-.04em;font-size:2rem}
    [data-testid="stVerticalBlockBorderWrapper"]>div {border-color:#264557!important;border-radius:14px!important;background:linear-gradient(140deg,#122635b3,#0b1722);}
    [data-testid="stForm"] {border:1px solid #27485b;border-radius:14px;background:#0e202dc2;padding:22px}
    [data-testid="stDataFrame"] {border:1px solid #244153;border-radius:10px;overflow:hidden}
    [data-testid="stExpander"] {border-color:#233e50;background:#0b1c2880;border-radius:10px}
    button[kind="primary"],button[data-testid="stBaseButton-primaryFormSubmit"] {background:linear-gradient(110deg,#008e98,#087bac);border:1px solid #44e5e5;color:white;box-shadow:0 3px 14px #00c2cb20}
    button[kind="secondary"] {border-color:#2e5368;background:#102535;border-radius:9px}
    [data-baseweb="select"]>div,[data-baseweb="input"],textarea {background:#091925!important;border-color:#2b4a5e!important}
    [data-testid="stAlert"] {border-radius:10px;border:1px solid #2c5060}
    [data-testid="stChatMessage"] {background:#102332;border:1px solid #254253;border-radius:14px}
    .ff-hero {position:relative;overflow:hidden;padding:25px 28px 27px;border:1px solid #2c5367;border-radius:17px;background:radial-gradient(ellipse at 100% 0,#0f76834d,transparent 65%),linear-gradient(110deg,#102b3c,#091723);margin-bottom:5px}
    .ff-hero:after {content:"";position:absolute;right:3%;top:-80px;width:360px;height:260px;border:1px solid #4bdcd324;border-radius:50%;transform:rotate(-28deg);box-shadow:0 0 0 26px #4bdcd308,0 0 0 64px #4bdcd306;pointer-events:none}
    .ff-eyebrow {font-size:.65rem;letter-spacing:.24em;color:#55e4d8;font-weight:750;margin-bottom:8px}
    .ff-hero h1 {font-size:2.25rem;padding:0;margin:0 0 7px;line-height:1.2}
    .ff-hero p {color:#b1c7d6;margin:0;font-size:.9rem}
    .ff-context {font-size:.74rem;color:#8ca9bb;margin-top:15px;position:relative;z-index:1}
    .ff-sync {border:1px solid #1f605f;border-left:3px solid #31d4b1;border-radius:10px;padding:12px 17px;background:linear-gradient(90deg,#0c39343d,#10222f);font-size:.78rem;color:#aec7cf;margin:4px 0 10px}
    .ff-sync strong {color:#61e8c7;margin-right:12px}
    .ff-kicker {color:#4bded7;font-size:.66rem;letter-spacing:.18em;text-transform:uppercase;margin:5px 0 12px}
    .ff-row {padding:12px 0;border-bottom:1px solid #254150;display:flex;justify-content:space-between;gap:14px;align-items:center}
    .ff-row:last-child {border-bottom:0}.ff-row b {font-size:.86rem}.ff-row small {display:block;color:#91aabc;font-size:.72rem;margin-top:3px}.ff-pill {font-size:.72rem;color:#58ecce;background:#124138;border:1px solid #226655;border-radius:6px;padding:4px 8px;white-space:nowrap}
    .ff-mix-legend{display:flex;justify-content:center;flex-wrap:wrap;gap:8px 12px;color:#a6bdcc;font-size:.72rem;line-height:1.4}.ff-mix-legend span{display:inline-flex;align-items:center;gap:5px}.ff-mix-legend i{width:9px;height:9px;border-radius:50%;display:inline-block}
    .ff-empty {color:#91aabc;font-size:.85rem;line-height:1.7;padding:14px 0;min-height:92px}
    .ff-opportunity-content{display:grid;grid-template-rows:repeat(3,66px)}
    .ff-opportunity-content .ff-row{padding:6px 0;gap:10px;min-width:0;margin:0}
    .ff-opportunity-copy{min-width:0;flex:1}
    .ff-opportunity-content b,.ff-opportunity-content small{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;overflow-wrap:anywhere;line-height:1.35}
    .ff-opportunity-content b{font-size:.84rem;-webkit-line-clamp:1}.ff-opportunity-content small{font-size:.73rem;margin-top:3px}
    .ff-opportunity-content .ff-pill{flex-shrink:0;font-size:.69rem;padding:4px 7px}
    .ff-opportunity-note{color:#91aabc;font-size:.73rem;line-height:1.5;min-height:3.1em;margin:12px 0 0}
    [class*="st-key-overview_opportunity_"] [data-testid="stCaptionContainer"]{min-height:2.9em;font-size:.76rem;line-height:1.45}
    [class*="st-key-overview_opportunity_"].stVerticalBlock{gap:12px}
    @media(max-width:850px){[data-testid="stMainBlockContainer"]{padding:1.2rem}.ff-hero{padding:20px}.ff-hero h1{font-size:1.8rem}[data-testid="stMetric"]{padding:12px;min-height:95px}[data-testid="stMetricValue"]{font-size:1.5rem}}
    </style>""")

def header(section,snapshot,roster):
    eyebrow,subtitle=COPY[section]
    st.html(f'<div class="ff-hero"><div class="ff-eyebrow">{eyebrow}</div><h1>{ICONS[section]} {escape(section)}</h1><p>{subtitle}</p><div class="ff-context">{escape(snapshot.name)} &nbsp; / &nbsp; {snapshot.season} SEASON &nbsp; / &nbsp; WEEK {snapshot.week} &nbsp; / &nbsp; {escape(roster.manager)}</div></div>')

def row(title,detail,value):
    st.html(f'<div class="ff-row"><div><b>{escape(str(title))}</b><small>{escape(str(detail))}</small></div><span class="ff-pill">{escape(str(value))}</span></div>')

def navigate(page):
    st.session_state['workspace']=page

def link(label,page,key):
    st.button(label,on_click=navigate,args=(page,),key=key,width='stretch')
