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

def theme():
    st.html("""<style>
    :root {--cyan:#37e7dc;--ink:#07121d;--muted:#94aabd}
    .stApp {background:radial-gradient(ellipse at 85% 0%,#123044 0,transparent 48%),#07111b;color:#eaf2f8}
    [data-testid="stHeader"] {background:transparent}
    [data-testid="stMainBlockContainer"] {padding:2.3rem 2rem 3rem;max-width:1600px}
    [data-testid="stSidebar"] {background:linear-gradient(165deg,#0b1c29,#07111a 75%);border-right:1px solid #203c4e}
    [data-testid="stSidebar"] h1 {font-size:1.4rem;letter-spacing:-.04em}
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
    .ff-empty {color:#91aabc;font-size:.85rem;line-height:1.7;padding:14px 0;min-height:92px}
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
