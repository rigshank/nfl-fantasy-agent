"""Searchable league rules, preserving raw Sleeper keys and values."""
from collections import Counter,defaultdict
from html import escape
import streamlit as st
from .analysis import FLEX_POSITIONS

STYLE="""<style>
.ff-rules-summary{display:flex;gap:9px;flex-wrap:wrap;margin:8px 0 16px}.ff-rule-pill{padding:7px 11px;border:1px solid #315164;border-radius:8px;background:#122a39;color:#a7c4d2;font-size:.76rem}.ff-rule-pill b{color:#61ded3;margin-right:6px}
.ff-rules-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,285px),1fr));gap:8px}.ff-rule{display:flex;gap:15px;justify-content:space-between;align-items:center;border:1px solid #294554;background:#102432;border-radius:9px;padding:11px 14px;min-width:0}.ff-rule strong{color:#67e0d2;font-size:.95rem;white-space:nowrap}.ff-rule.negative strong{color:#ffbaab}.ff-rule-name{font-size:.8rem;color:#d4e4ed;line-height:1.4}.ff-rule-key{font-size:.64rem;color:#85a3b6;margin-top:4px;overflow-wrap:anywhere}.ff-fields{margin:0}.ff-field{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:18px;padding:9px 3px;border-bottom:1px solid #203d4c}.ff-field:last-child{border:0}.ff-field dt{font-size:.77rem;color:#9dbacb;overflow-wrap:anywhere}.ff-field dd{margin:0;font-size:.8rem;color:#edf4f8;text-align:right;overflow-wrap:anywhere}
</style>"""
WORDS={'yd':'yards','td':'touchdown','cmp':'completion','att':'attempt','int':'interception','rec':'receiving','rush':'rushing','pass':'passing','fum':'fumble','xp':'extra point','fg':'field goal','pts':'points','def':'defense','tkl':'tackle','st':'special teams','yds':'yards','te':'TE','rb':'RB','wr':'WR','qb':'QB','idp':'IDP','ppr':'PPR','faab':'FAAB'}


def label(key):
    return {'rec':'Reception (PPR)','fum_lost':'Fumble lost','pass_int':'Passing interception'}.get(key,' '.join(WORDS.get(part,part) for part in key.split('_')).capitalize())


def category(key):
    if key.startswith('bonus_'):return 'Bonuses & position premiums'
    if key.startswith('pass_'):return 'Passing'
    if key.startswith('rush_'):return 'Rushing'
    if key=='rec' or key.startswith('rec_'):return 'Receiving'
    if key.startswith(('fg','xp')):return 'Kicking'
    if key.startswith(('fum','kr_','pr_','st_')):return 'Ball security & returns'
    return 'Defense & other rules'


def matches(query,*values):
    return query.strip().casefold() in ' '.join(str(x) for x in values).casefold()


def leaves(value,prefix=''):
    if isinstance(value,dict) and value:
        for k,v in value.items():yield from leaves(v,f'{prefix} / {k}' if prefix else str(k))
    elif isinstance(value,list) and value:
        for i,v in enumerate(value):yield from leaves(v,f'{prefix} / {i+1}')
    else:yield prefix,value


def display(value):
    if value is None:return 'Not provided'
    if value is True:return 'Yes'
    if value is False:return 'No'
    if value=={} or value==[]:return 'Empty'
    return str(value)


def fields_html(rows):
    return '<dl class="ff-fields">'+''.join(f'<div class="ff-field"><dt>{escape(label(k))}<div class="ff-rule-key">{escape(k)}</div></dt><dd>{escape(display(v))}</dd></div>' for k,v in rows)+'</dl>'


def scoring_html(rows):
    return '<div class="ff-rules-grid">'+''.join(f'<div class="ff-rule {"negative" if v<0 else ""}"><div><div class="ff-rule-name">{escape(label(k))}</div><div class="ff-rule-key">{escape(k)}</div></div><strong>{v:+g} pts</strong></div>' for k,v in rows)+'</div>'


def render_rules(snapshot):
    st.html(STYLE)
    query=st.text_input('Search league rules',placeholder='Try passing, reception, bench, waiver, playoff or a Sleeper field name',key='league_rules_search')
    counts=Counter(snapshot.roster_positions)
    starter_count=sum(n for slot,n in counts.items() if slot not in {'BN','IR','TAXI'})
    st.html('<div class="ff-rules-summary">'+''.join(f'<span class="ff-rule-pill"><b>{escape(str(v))}</b>{escape(k)}</span>' for k,v in [('starter slots',starter_count),('bench slots',counts.get('BN',0)),('scoring rules',len(snapshot.scoring)),('league format',snapshot.league_type.title())])+'</div>')
    st.subheader('Roster requirements')
    visible=[(slot,n) for slot,n in counts.items() if matches(query,slot,{'BN':'bench','IR':'injured reserve','TAXI':'taxi squad'}.get(slot,slot),'roster requirements')]
    if visible:
        st.html('<div class="ff-rules-summary">'+''.join(f'<span class="ff-rule-pill"><b>{n} ×</b>{escape(slot)}</span>' for slot,n in visible)+'</div>')
    else:st.caption('No roster slots match your search.')
    with st.expander('Slot eligibility & reserve details',expanded=bool(query) and bool(visible)):
        rows=[(slot,', '.join(sorted(FLEX_POSITIONS[slot])) if slot in FLEX_POSITIONS else {'BN':'Bench · not a starting slot','IR':'Injured reserve','TAXI':'Taxi squad'}.get(slot,slot)) for slot,_ in visible]
        # Reserve sizes are league settings, often absent from roster_positions.
        rows.extend((k,v) for k,v in snapshot.settings.items() if k.startswith(('reserve_','taxi_')) and matches(query,k,label(k),v))
        st.html(fields_html(rows))
    st.subheader('Scoring')
    groups=defaultdict(list)
    for k,v in sorted(snapshot.scoring.items()):
        group=category(k)
        if matches(query,k,label(k),group,v):groups[group].append((k,v))
    if not groups:st.caption('No scoring rules match your search.')
    for name,rows in groups.items():
        with st.expander(f'{name} · {len(rows)}',expanded=bool(query)):
            st.html(scoring_html(rows))
    st.caption('Values are league scoring weights. Raw Sleeper rule IDs are shown for precise reference; bonus conditions and stacking follow the league configuration.')
    with st.expander('Complete league settings',expanded=bool(query)):
        st.caption('All reported fields, including zero and disabled values. Numeric setting codes are preserved as reported by Sleeper.')
        for title,source in [('Settings',snapshot.settings),('League metadata',snapshot.metadata)]:
            rows=[(k,v) for k,v in leaves(source) if k and matches(query,k,label(k),display(v))]
            st.markdown('**'+title+f' · {len(rows)}**')
            if rows:st.html(fields_html(rows))
            else:st.caption('No matching fields.')
