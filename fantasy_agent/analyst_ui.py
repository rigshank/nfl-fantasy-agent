"""Conversational control center with actual tool progress and supporting results."""
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import streamlit as st
import streamlit.components.v1 as components
from .conversations import Conversations
from .agent import Analyst
from .integrations.research import ProviderUnavailable
from .integrations.sleeper import DataUnavailable
from .lineup_service import LineupReport
from .lineup_ui import lineup_table
from .models import ResearchBundle
from .storage import BudgetExceeded
from . import ui

_browser_identity=components.declare_component("analyst_browser_identity",path=str(Path(__file__).parent/"components"/"browser_identity"))


def conversation_history(snapshot,roster_id,store):
    fallback=st.session_state.setdefault("analyst_browser_fallback",uuid4().hex)
    browser_id=_browser_identity(fallback=fallback,key="analyst_browser_identity",default=None)
    if browser_id is None:
        st.caption("Loading your conversations…")
        st.stop()
    chats=Conversations(store,str(browser_id),snapshot.league_id,roster_id)
    history=chats.list()
    entering=not st.session_state.get("analyst_page_open") or st.session_state.get("analyst_scope")!=chats.scope
    if entering:
        # Preserve a pre-upgrade chat without importing another team's history.
        legacy=st.session_state.get("messages",[]) if "analyst_scope" not in st.session_state else []
        if legacy:
            chats.create(legacy);history=chats.list()
        selected=history[0]["id"] if history else None
        st.session_state.update(analyst_scope=chats.scope,analyst_conversation=selected,
            messages=chats.messages(selected) if selected else [],analyst_page_open=True)
    def select(cid):
        st.session_state["analyst_conversation"]=cid
        st.session_state["messages"]=chats.messages(cid) or []
        st.session_state.pop("queued_question",None)
    def new_chat():select(None)
    left,right=st.columns([1,3],gap="large")
    with left,st.container(border=True,key="analyst_history"):
        st.subheader("Conversations")
        st.button("New conversation",icon=":material/add:",on_click=new_chat,width="stretch",key="analyst_new")
        if not history:st.caption("Your chats will appear here after your first question.")
        with st.container(height=430,border=False):
            group=None
            for chat in history:
                stamp=datetime.fromtimestamp(chat["updated"],timezone.utc).astimezone(ZoneInfo("America/Chicago"))
                label=stamp.strftime("%b %d, %Y")
                if group!=label:st.caption(label.upper());group=label
                st.button(chat["title"],on_click=select,args=(chat["id"],),width="stretch",
                    type="primary" if chat["id"]==st.session_state.get("analyst_conversation") else "secondary",
                    key="analyst_chat_"+chat["id"],help="Last message · "+ui.local_time(stamp))
        st.caption("Saved for this browser and team.")
    return chats,right


def save_conversation(chats):
    cid=st.session_state.get("analyst_conversation")
    if cid is None:
        cid=chats.create(st.session_state["messages"])
        st.session_state["analyst_conversation"]=cid
    else:chats.save(cid,st.session_state["messages"])


def supporting_evidence(records):
    if not records:return
    with st.expander("Supporting evidence and calculations"):
        for record in records:
            st.markdown("**"+record["tool"].replace("_"," ").title()+"**")
            if record.get("error"):
                st.warning(record["error"]);continue
            result=record.get("result",{})
            players=result.get("players",{})
            def names(ids):return ", ".join(players.get(p,{}).get("name",p) for p in ids)
            if record["tool"]=="optimize_lineup":
                st.dataframe(lineup_table(LineupReport.model_validate(result),players),hide_index=True,width="stretch")
            elif record["tool"] in {"find_trades","evaluate_trade"}:
                trades=result.get("trades",[result["trade"]] if result.get("trade") else [])
                st.dataframe([{"Opponent":t["opponent_id"],"Send":names(t["send"]),"Receive":names(t["receive"]),
                    "Your ROS gain":t["my_ros_gain"],"Opponent ROS gain":t["opponent_ros_gain"],"Balance":t["balance_score"],"Confidence":t["confidence"]} for t in trades],hide_index=True,width="stretch")
            elif record["tool"]=="waivers_and_breakouts":
                st.dataframe([{"Pickup":names([p["player_id"]]),"Drop":names([p["drop_id"]]) if p["drop_id"] else "Open spot",
                    "Next full week gain":p["next_week_gain"],"ROS gain":p["ros_gain"],"Confidence":p["confidence"]} for p in result["pickups"]],hide_index=True,width="stretch")
            st.json({"arguments":record.get("arguments"),"evidence":result},expanded=False)


def render_analyst(snapshot,roster_id,service,config,store):
    chats,conversation=conversation_history(snapshot,roster_id,store)
    with conversation,st.container(key="analyst_conversation_panel"):
        render_conversation(snapshot,roster_id,service,config,store,chats)


def render_conversation(snapshot,roster_id,service,config,store,chats):
    st.subheader("Your league analyst")
    st.caption("Trades, pickups and lineup decisions, grounded in your league.")
    def prompt(text):st.session_state["queued_question"]=text
    if not st.session_state["messages"]:
        with st.container(border=True):
            st.subheader("What should we work on?")
            for col,label,question in zip(st.columns(3),["⇄ Find a trade","◇ Improve my bench","◎ Set my lineup"],
                ["Find realistic trades that improve my starting lineup and explain the other manager's incentive.","Find the best available pickups and explain who I should drop.","Who should I start this week? Research relevant injuries and explain close decisions."]):
                col.button(label,on_click=prompt,args=(question,),width="stretch")
            st.caption("Uses your league, deterministic analysis and current reporting. Every important decision should have evidence.")
    web=st.checkbox("Research current news when relevant",value=True)
    with st.container(height=340 if st.session_state["messages"] else "content",border=False,key="analyst_transcript",autoscroll=True):
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                if message.get("error"):st.error(message["content"])
                else:st.markdown(message["content"])
                if message.get("research"):ui.sources_view(ResearchBundle.model_validate(message["research"]),expanded=False)
                if message.get("refreshed_at"):st.caption("Ownership refreshed "+ui.local_time(datetime.fromisoformat(message["refreshed_at"])))
                supporting_evidence(message.get("tools"))
    with st.container(border=True,key="analyst_composer"):
        st.html('<div class="ff-composer-label">✧ ASK YOUR ANALYST</div>')
        question=st.chat_input("Ask about a trade, a player, or your next move…",key="analyst_question") or st.session_state.pop("queued_question",None)
        st.caption("Enter to send · Shift + Enter for a new line")
    if not question:return
    prior=list(st.session_state["messages"])
    st.session_state["messages"].append({"role":"user","content":question})
    save_conversation(chats)
    with st.chat_message("user"):st.write(question)
    analyst=Analyst(config,store,service)
    try:
        with st.status("Gathering league evidence…",expanded=True) as status:
            fresh,message=analyst.run(snapshot,roster_id,question,prior,web,
                st.session_state.get("waiver_protected_players",[]),on_event=lambda name:st.write(name if name.startswith("Waiting") else "Using "+name.replace("_"," ")+"…"),
                excluded=st.session_state.get("lineup_excluded_players",[]))
            status.update(label="Analysis complete",state="complete",expanded=False)
        st.session_state["snapshot"]=fresh
        st.session_state["messages"].append(message)
        save_conversation(chats)
        st.rerun()
    except (DataUnavailable,ProviderUnavailable,BudgetExceeded,ValueError) as exc:
        st.error(str(exc));st.caption("Retry after resolving the source/quota issue. Completed calculations below remain available.")
        tools=getattr(analyst,"last_tools",None)
        records=tools.records if tools else []
        st.session_state["messages"].append(
            {"role":"assistant","content":"Analysis could not finish: "+str(exc),"tools":records,"error":True,
             "research":ResearchBundle(query=question,sources=list(tools.sources.values()) if tools else []).model_dump(mode="json")})
        save_conversation(chats)
        st.rerun()
