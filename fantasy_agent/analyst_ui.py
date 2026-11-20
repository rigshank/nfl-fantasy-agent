"""Conversational control center with actual tool progress and supporting results."""
from datetime import datetime
import streamlit as st
from .agent import Analyst
from .integrations.research import ProviderUnavailable
from .integrations.sleeper import DataUnavailable
from .lineup_service import LineupReport
from .lineup_ui import lineup_table
from .models import ResearchBundle
from .storage import BudgetExceeded
from . import ui


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
    st.caption("Ask for an action plan, trade, pickup, player comparison or lineup. The analyst selects Python and research tools as needed.")
    web=st.checkbox("Research current news when relevant",value=True)
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("research"):ui.sources_view(ResearchBundle.model_validate(message["research"]))
            if message.get("refreshed_at"):st.caption("Ownership refreshed "+ui.local_time(datetime.fromisoformat(message["refreshed_at"])))
            supporting_evidence(message.get("tools"))
    if st.button("New conversation"):
        st.session_state["messages"]=[];st.session_state.pop("queued_question",None);st.rerun()
    question=st.chat_input("Analyze my entire team and tell me what to do to improve my chances of winning") or st.session_state.pop("queued_question",None)
    if not question:return
    with st.chat_message("user"):st.write(question)
    analyst=Analyst(config,store,service)
    try:
        with st.status("Gathering league evidence…",expanded=True) as status:
            fresh,message=analyst.run(snapshot,roster_id,question,st.session_state["messages"],web,
                st.session_state.get("waiver_protected_players",[]),on_event=lambda name:st.write(name if name.startswith("Waiting") else "Using "+name.replace("_"," ")+"…"),
                excluded=st.session_state.get("lineup_excluded_players",[]))
            status.update(label="Analysis complete",state="complete",expanded=False)
        st.session_state["snapshot"]=fresh
        st.session_state["messages"].extend([{"role":"user","content":question},message])
        with st.chat_message("assistant"):
            st.markdown(message["content"])
            ui.sources_view(ResearchBundle.model_validate(message["research"]))
            st.caption("Ownership refreshed "+ui.local_time(fresh.refreshed_at))
            supporting_evidence(message["tools"])
    except (DataUnavailable,ProviderUnavailable,BudgetExceeded,ValueError) as exc:
        st.error(str(exc));st.caption("Retry after resolving the source/quota issue. Completed calculations below remain available.")
        tools=getattr(analyst,"last_tools",None)
        records=tools.records if tools else []
        st.session_state["messages"].extend([{"role":"user","content":question},
            {"role":"assistant","content":"Analysis could not finish: "+str(exc),"tools":records,
             "research":ResearchBundle(query=question,sources=list(tools.sources.values()) if tools else []).model_dump(mode="json")}])
        supporting_evidence(records)
