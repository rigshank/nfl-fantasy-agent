"""Clear only dependent UI state when league/team/rules change."""
ANALYSIS_KEYS=("waiver_run","waiver_snapshot","waiver_answers","waiver_identity",
    "trade_run","trade_snapshot","trade_explanations","trade_history","trade_identity",
    "lineup_report","lineup_identity","breakout_run","breakout_identity")


def clear_analysis(state,team_changed=False):
    for key in ANALYSIS_KEYS:state.pop(key,None)
    if team_changed:
        state.pop("waiver_protected_players",None)
        state.pop("lineup_excluded_players",None)
        state.pop("queued_question",None)
        state["messages"]=[]


def apply_overrides(config,state):
    return config.model_copy(update=state.get("analysis_options",{}))
