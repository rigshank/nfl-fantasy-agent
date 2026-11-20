"""Compact activity browser sharing the league rules' searchable detail layout."""
from datetime import datetime,timezone
from html import escape
import streamlit as st
from .rules_ui import STYLE,fields_html,leaves,matches,display


def team_name(snapshot,rid):
    return next((r.manager for r in snapshot.rosters if str(r.roster_id)==str(rid)),f"Roster {rid}" if rid is not None else 'Not reported')


def player_name(snapshot,pid):
    player=snapshot.players.get(str(pid))
    return player.name if player else f"Unresolved player {pid}"


def activity_summary(snapshot,field,entry,index):
    if field=='transactions':
        kind=str(entry.get('type') or 'Transaction').replace('_',' ').title()
        status=str(entry.get('status') or 'Status not reported').replace('_',' ').title()
        teams=', '.join(team_name(snapshot,rid) for rid in entry.get('roster_ids') or []) or 'Teams not reported'
        title=f'{kind} · {status} · {teams}'
        lines=[]
        for action,key in [('Add','adds'),('Drop','drops')]:
            for pid,rid in (entry.get(key) or {}).items():lines.append((action,player_name(snapshot,pid)+(' to ' if key=='adds' else ' from ')+team_name(snapshot,rid)))
        if entry.get('draft_picks'):lines.append(('Draft picks included',len(entry['draft_picks'])))
        stamp=entry.get('status_updated') or entry.get('created')
        if isinstance(stamp,(int,float)):
            try:lines.insert(0,('Reported time (UTC)',datetime.fromtimestamp(stamp/1000,timezone.utc).strftime('%b %d, %Y · %H:%M UTC')))
            except (ValueError,OverflowError,OSError):pass
    elif field=='traded_picks':
        title=f"{entry.get('season','Season not reported')} · Round {entry.get('round','?')} · {team_name(snapshot,entry.get('roster_id'))} original pick"
        lines=[('Previous owner',team_name(snapshot,entry.get('previous_owner_id'))),('Current reported owner',team_name(snapshot,entry.get('owner_id')))]
    else:
        title=f"Draft {entry.get('season','')} · {str(entry.get('type') or 'Type not reported').replace('_',' ').title()} · {str(entry.get('status') or 'Status not reported').replace('_',' ').title()}"
        settings=entry.get('settings') or {}
        lines=[(key.replace('_',' ').title(),settings[key]) for key in ('rounds','teams','pick_timer') if key in settings]
        if entry.get('draft_id') is not None:lines.append(('Draft ID',entry['draft_id']))
    return title,lines


def activity_records(snapshot,field,query):
    result=[]
    for index,entry in enumerate(getattr(snapshot,field)):
        if not isinstance(entry,dict):
            entry={'reported_value':entry}
        title,summary=activity_summary(snapshot,field,entry,index)
        rows=list(leaves(entry))
        if matches(query,title,*[f'{k} {display(v)}' for k,v in summary+rows]):result.append((title,summary,rows))
    return result


def render_activity(snapshot):
    st.html(STYLE)
    query=st.text_input('Search league activity',placeholder='Player, manager, trade, waiver, season, draft ID or setting',key='league_activity_search')
    st.caption(f"Week {snapshot.week} activity and reported draft records. Expand a record for every source field; scores and ownership reflect the last league refresh.")
    sections=[('transactions','Weekly transactions'),('traded_picks','Traded draft picks'),('drafts','Draft metadata')]
    for field,title in sections:
        unavailable=any(w.startswith(field+' unavailable') for w in snapshot.warnings)
        records=activity_records(snapshot,field,query)
        with st.expander(f'{title} · {"Unavailable" if unavailable else str(len(records))+" records"}',expanded=bool(query)):
            if unavailable:
                st.warning('Unavailable on the last refresh. Refresh league to retry; this is not a confirmed empty history.')
                continue
            if not records:
                st.caption('No records match your search.' if query else 'No records were returned for this section.')
                continue
            pages=max(1,(len(records)+9)//10)
            page=st.number_input('Page · '+title,min_value=1,max_value=pages,value=1,key=f'activity_page_{snapshot.league_id}_{field}_{query}') if pages>1 else 1
            st.caption(f'{len(records)} records · showing {(page-1)*10+1}–{min(page*10,len(records))}')
            for i,(heading,summary,rows) in enumerate(records[(page-1)*10:page*10],start=(page-1)*10+1):
                with st.expander(f'{i:02d} · {heading}'):
                    if summary:
                        st.markdown('**Activity summary**')
                        st.html(fields_html(summary))
                    st.html('<details><summary style="cursor:pointer;color:#65dcd2;font-size:.8rem;padding:12px 0">All reported fields · '+str(len(rows))+'</summary>'+fields_html(rows)+'</details>')
    st.caption('Transactions cover the selected week. Traded-pick and draft metadata do not establish a complete historical log, draft selections or future-pick inventory. Reported pending or failed transactions are not treated as completed moves.')
