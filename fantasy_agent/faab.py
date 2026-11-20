"""Transparent optional bidding heuristic, bounded by actual Sleeper budgets."""
import math
from .scoring import number


def waiver_budget(snapshot,roster_id):
    roster=next(r for r in snapshot.rosters if r.roster_id==roster_id)
    settings=snapshot.settings
    mode=settings.get("waiver_type")
    result={"waiver_type":mode,"initial_budget":None,"spent":None,"remaining":None,"minimum_bid":None,
            "basis":"League waiver settings and roster waiver_budget_used; verify commissioner adjustments in Sleeper."}
    if mode!=2:
        result["limitation"]="FAAB is not confirmed by waiver_type=2; no monetary bid is inferred from a default budget field."
        return result
    initial=number(settings.get("waiver_budget"));spent=number(roster.settings.get("waiver_budget_used"))
    adjustment=number(roster.settings.get("waiver_adjusted",0))
    minimum=number(settings.get("waiver_bid_min"))
    if minimum is None:minimum=number(settings.get("waiver_min_bid"))
    if minimum is None:
        minimum=0
        result["minimum_basis"]="Sleeper default $0 minimum; an unreported commissioner customization needs verification."
    result.update(initial_budget=initial,spent=spent,minimum_bid=minimum)
    if adjustment is None or adjustment!=0:
        result["reported_adjustment"]=adjustment
        result["limitation"]="The roster reports a waiver adjustment whose effect on available FAAB is not verified. Confirm the remaining balance in Sleeper; no numeric bid is inferred."
    elif initial is None or spent is None or initial<0 or minimum<0:
        result["limitation"]="Budget or spend is missing/invalid; no bid estimate is produced."
    else:
        result["remaining"]=max(0,math.floor(initial-spent))
    return result


def bid_guidance(snapshot,roster_id,pickup,weeks):
    budget=waiver_budget(snapshot,roster_id)
    remaining=budget["remaining"]
    if remaining is None:return {**budget,"range":None}
    if remaining<budget["minimum_bid"]:
        return {**budget,"range":None,"limitation":"Remaining FAAB is below the minimum bid; no legal bid is suggested."}
    # Stated personal spending heuristic, not a forecast of competing sealed bids.
    per_week=max(0,pickup.ros_gain)/max(1,weeks)
    fraction=min(.25,.02+.03*per_week) if per_week>0 else .01
    if pickup.confidence=="low":fraction*=.5
    low=max(math.ceil(budget["minimum_bid"]),math.floor(remaining*fraction*.5))
    high=min(remaining,max(low,math.ceil(remaining*fraction)))
    return {**budget,"range":[low,high],"basis":"Subjective spending range: 2% + 3% per estimated ROS lineup point/week, capped at 25% of remaining FAAB; depth-only 1%, low confidence halves it. Lower bound is half the upper rate. Not a winning-bid prediction.",
            "limitation":"Public data does not expose pending claims or sealed bids. Confirm current claim eligibility and commissioner budget adjustments before submitting."}
