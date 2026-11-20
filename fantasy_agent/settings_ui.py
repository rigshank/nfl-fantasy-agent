"""Only useful operating controls; credentials never enter widgets or exports."""
import streamlit as st
from html import escape
from .integrations.gemini import Gemini,FREE_MODELS
from .integrations.research import Research,ProviderUnavailable
from .session import clear_analysis
from . import ui
from .waiver_cards import STYLE as METRIC_STYLE, stat
from .evidence_ui import STYLE as CARD_STYLE


def connection_card(name, configured, description):
    return CARD_STYLE + f'<div class="ff-source-card"><div class="ff-source-top"><div class="ff-source-title">{escape(name)}</div><span class="ff-source-state {"" if configured else "ff-source-stale"}">{"KEY CONFIGURED" if configured else "KEY MISSING"}</span></div><p>{escape(description)}</p><p>Key presence does not verify API access or remaining quota.</p></div>'


def usage_card(provider, row):
    # A missing row means no recorded attempts, not verified unused API quota.
    values = [stat('Recorded attempts', f'{row.get("requests",0):,}')]
    if provider == 'gemini':
        values.append(stat('Reported total tokens', f'{row.get("tokens",0):,}'))
    else:
        values.append(stat('Credit allowance', 'Check above', 'Provider quota is queried separately'))
    token_details = ''.join(stat(label, f'{row.get(key,0):,}') for label,key in [('Input tokens','input_tokens'),('Output tokens','output_tokens'),('Thinking tokens','thinking_tokens')]) if provider == 'gemini' else ''
    return METRIC_STYLE + CARD_STYLE + '<article class="ff-source-card"><div class="ff-source-title">' + provider.title() + '</div><div class="ff-evidence-grid" style="margin-top:12px">' + ''.join(values) + '</div>' + (f'<details style="margin-top:12px"><summary>Token breakdown</summary><div class="ff-evidence-grid" style="margin-top:10px">{token_details}</div></details>' if token_details else '') + '</article>'


def render_settings(snapshot,service,config,store):
    st.caption("Manage this session’s analysis preferences, check provider access, and refresh your league.")
    preferences,connections,data_tab=st.tabs(["Analysis preferences","Connections & usage","League data"])
    with preferences:
        st.subheader("Analysis preferences")
        st.caption("Choose how the AI handles your next analysis. Preferences apply to this browser session.")
        if st.session_state.pop('analysis_settings_saved',False):st.success('Analysis preferences saved for this session.')
        with st.form("analysis_settings"):
            models=["auto",*FREE_MODELS]
            if config.gemini_model not in models:models.append(config.gemini_model)
            left,right=st.columns([1.3,1])
            model=left.selectbox("Gemini model",models,index=models.index(config.gemini_model),format_func=lambda value:'Automatic · recommended' if value=='auto' else value,
                help='Automatic prefers a capable accessible free-tier model. An unavailable selection can fall back to another supported free-tier model.')
            levels=["high","medium","low"]
            level=right.selectbox("Reasoning level",levels,index=levels.index(config.gemini_thinking_level) if config.gemini_thinking_level in levels else 0,
                format_func=lambda value:value.title(),help='Applied where the selected model supports this reasoning setting.')
            submitted=st.form_submit_button("Save analysis preferences",type="primary",width='stretch')
        if submitted:
            st.session_state["analysis_options"]={"gemini_model":model,"gemini_thinking_level":level}
            st.session_state['analysis_settings_saved']=True
            st.rerun()
        with st.expander('Model selection and free-tier behavior'):
            st.caption(f'Automatic checks {len(FREE_MODELS)} supported free text models, preferring quality. Recently overloaded models cool down for two minutes. Actual API availability and quotas still apply; there is no paid fallback or custom token budget. Session preferences do not edit deployment secrets.')
    with connections:
        st.subheader('Provider connections')
        left,right=st.columns(2)
        with left:
            configured=bool(config.gemini_api_key.get_secret_value())
            st.html(connection_card('Gemini',configured,'AI reasoning and league-specific explanations.'))
            if st.button("Verify Gemini model access",width='stretch',disabled=not configured):
                try:
                    with st.spinner('Checking model metadata access…'):
                        selector=Gemini(config,store)
                        model=selector.check_model()
                    st.success("Model metadata access verified: "+model)
                    if selector.model_notice:st.info(selector.model_notice)
                    st.caption("This verifies model access, not current generation capacity or account billing status.")
                except ProviderUnavailable as exc:st.error(str(exc))
        with right:
            configured=bool(config.tavily_api_key.get_secret_value())
            st.html(connection_card('Tavily',configured,'Current news, injuries and web research with source links.'))
            if st.button("Check Tavily free allowance",width='stretch',disabled=not configured):
                try:
                    with st.spinner('Checking provider allowance…'):
                        account=Research(config,store).account_usage()["account"]
                    st.success(f"{account['current_plan']}: {account['plan_limit']-account['plan_usage']} free credits remaining.")
                except ProviderUnavailable as exc:st.error(str(exc))
        st.subheader('Recorded app usage')
        st.caption('Attempts and provider-reported tokens since this app cache was created. These are not billing totals or a monthly quota balance; model and allowance checks are excluded.')
        usage={row['provider']:row for row in store.usage() if row['provider'] in {'gemini','tavily'}}
        for col,provider in zip(st.columns(2),['gemini','tavily']):
            with col:st.html(usage_card(provider,usage.get(provider,{})))
    with data_tab:
        st.subheader("League data")
        st.html(CARD_STYLE + '<article class="ff-source-card"><div class="ff-source-title">' + escape(snapshot.name) + '</div><p>' + escape(f'{snapshot.season} season · Week {snapshot.week} · {len(snapshot.rosters)} teams · {snapshot.league_type.title()}') + '</p><p>League snapshot · ' + escape(ui.local_time(snapshot.refreshed_at)) + '</p><p>Player catalog · ' + escape(ui.local_time(snapshot.catalog_at)) + '</p></article>')
        left,right=st.columns(2)
        with left,st.container(border=True):
            st.markdown('**Refresh ownership and league settings**')
            st.caption('Fetch current league data and clear saved analyses so your next recommendations use the refreshed roster.')
            if st.button("Refresh league data",type='primary',width='stretch'):
                try:
                    with st.spinner('Refreshing league data…'):
                        fresh=service.load(snapshot.league_id,force=True)
                    clear_analysis(st.session_state)
                    st.session_state["snapshot"]=fresh
                    st.rerun()
                except (RuntimeError,ValueError) as exc:st.error(str(exc))
        with right,st.container(border=True):
            st.markdown('**Download this league snapshot**')
            st.caption('Save the currently displayed league data as JSON, including its timestamps. This export contains no API keys.')
            st.download_button("Export current league snapshot",snapshot.model_dump_json(indent=2),"league-snapshot.json","application/json",width='stretch')
        with st.expander('What gets refreshed?'):
            st.caption('League refresh updates roster ownership and league information. The daily player catalog and statistical caches are reused; analysis workspaces have separate statistical refresh controls. Provider credentials remain in environment variables or deployment secrets.')
