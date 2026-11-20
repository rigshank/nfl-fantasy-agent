"""Only useful operating controls; credentials never enter widgets or exports."""
import streamlit as st
from .integrations.gemini import Gemini,FREE_MODELS
from .integrations.research import Research,ProviderUnavailable
from .session import clear_analysis
from . import ui


def render_settings(snapshot,service,config,store):
    st.subheader("Analysis and connections")
    preferences,connections,data_tab=st.tabs(["Analysis preferences","Connections & usage","League data"])
    with preferences:
        with st.form("analysis_settings"):
            models=["auto",*FREE_MODELS]
            if config.gemini_model not in models:models.append(config.gemini_model)
            model=st.selectbox("Gemini model",models,index=models.index(config.gemini_model))
            levels=["high","medium","low"]
            level=st.selectbox("Reasoning level",levels,index=levels.index(config.gemini_thinking_level) if config.gemini_thinking_level in levels else 0)
            submitted=st.form_submit_button("Apply analysis settings",type="primary")
        if submitted:
            st.session_state["analysis_options"]={"gemini_model":model,"gemini_thinking_level":level}
            st.rerun()
        st.caption("These session preferences do not edit your secrets. Auto checks seven documented free text models, preferring quality; recently overloaded models cool down for two minutes; no paid fallback, output-token cap or custom token budget is enabled.")
    with connections:
        st.write("Gemini key:","Configured" if config.gemini_api_key.get_secret_value() else "Missing")
        st.write("Tavily key:","Configured" if config.tavily_api_key.get_secret_value() else "Missing")
        if st.button("Verify Gemini model access"):
            try:
                selector=Gemini(config,store)
                model=selector.check_model()
                st.success("Model metadata access verified: "+model)
                if selector.model_notice:st.info(selector.model_notice)
                st.caption("This verifies model access, not current generation capacity or account billing status.")
            except ProviderUnavailable as exc:st.error(str(exc))
        if st.button("Check Tavily free allowance"):
            try:
                account=Research(config,store).account_usage()["account"]
                st.success(f"{account['current_plan']}: {account['plan_limit']-account['plan_usage']} free credits remaining.")
            except ProviderUnavailable as exc:st.error(str(exc))
        usage=[row for row in store.usage() if row["provider"] in {"gemini","tavily"}]
        if usage:st.dataframe(usage,hide_index=True,width="stretch")
        st.caption("Generation/search attempts and reported tokens since this cache was created. Model lookups and quota checks are excluded; these are not provider billing or durable monthly totals.")
    with data_tab:
        st.subheader("League data")
        st.caption("Last refresh: "+ui.local_time(snapshot.refreshed_at))
        if st.button("Refresh league data"):
            try:
                fresh=service.load(snapshot.league_id,force=True)
                clear_analysis(st.session_state)
                st.session_state["snapshot"]=fresh
                st.rerun()
            except (RuntimeError,ValueError) as exc:st.error(str(exc))
        st.download_button("Export current league snapshot",snapshot.model_dump_json(indent=2),"league-snapshot.json","application/json")
        st.caption("The daily player catalog and statistical caches are reused. Keys remain in environment variables or Streamlit secrets; no key is included in this export.")
