"""Small, read-only tool dispatcher sharing the dashboard's real-data services."""
import statistics
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from .analysis import owned, free_players
from .evaluation import evaluate_players
from .integrations.gemini import Gemini
from .integrations.nflverse import NFLVerse, SCHEDULE_URL
from .integrations.research import Research, safe_error,validate_answer_sources
from .lineup_service import LineupService
from .models import ResearchBundle, utcnow
from .service import compact_context,analysis_fingerprint
from .trade_models import TradeOptions
from .trade_service import TradeService
from .trades import TradeEngine
from .waiver_service import WaiverService
from .waivers import breakout_signals


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Empty(Args):
    pass


class PlayerQuery(Args):
    query: str = ""
    position: str | None = None


class EvidenceArgs(Args):
    player_ids: list[str] = Field(default_factory=list, description="Exact Sleeper IDs from league/player tools; empty selects scope.")
    scope: Literal["my", "free", "all"] = "my"
    position: str | None = None
    include_history: bool = Field(False,description="Include full weekly histories and future week estimates; use for detailed player comparisons when needed.")


class TradeArgs(Args):
    position: str | None = None
    opponent_id: int | None = None
    structures: list[list[int]] = Field(default_factory=lambda:[[1,1],[2,1]], description="Player counts [send,receive] per structure, 1–3 each; all eligible players are searched.")
    must_send: list[str] = Field(default_factory=list)
    results: int = Field(10,ge=1,le=50,description="Returned ranked rows; does not limit analyzed players.")


class CompareTradeArgs(Args):
    opponent_id: int
    send: list[str]
    receive: list[str]


class WaiverArgs(Args):
    position: str | None = None
    strategy: Literal["balanced","win_now"] = "balanced"
    protected: list[str] = Field(default_factory=list)
    breakout_scope: Literal["available","my","all"] = Field("available",description="Which breakout signals to RETURN. All players are evaluated; default is available pickups. Choose my for roster development or all for league-wide scouting.")


class LineupArgs(Args):
    week: int | None = Field(None,ge=1,le=18)
    strategy: Literal["expected","upside","floor"] = "expected"
    exclude_players: list[str] = Field(default_factory=list,description="Owned player IDs to exclude from unlocked slots based on current reports.")
    exclusion_sources: dict[str,str] = Field(default_factory=dict,description="Exact already-retrieved source URL for each additional player exclusion. Do not infer inactivity from missing news.")


class SearchArgs(Args):
    query: str = Field(min_length=1,description="Relevant NFL/player news, injuries, rankings, usage or matchup query. Include season/player names.")
    time_range: Literal["day","week","month","year"] = "week"


TOOLS = {
    "team_strategy": (Empty,"For broad improve-my-team, league strategy or playoff-planning requests: collect league, all-team needs, waivers/breakouts, legal current lineup and realistic trades in ONE tool call using shared evidence. Then research the leading relevant decisions. Focused requests should use individual tools."),
    "get_league": (Empty,"Retrieve latest refreshed scoring, roster slots, your team, every opponent, records, current matchups, transactions and ownership."),
    "find_players": (PlayerQuery,"Resolve player names to exact Sleeper IDs with current team, injury metadata and owner. Empty query returns all matching catalog entries."),
    "get_free_agents": (PlayerQuery,"Return every eligible truly unowned free player matching optional position/name. For ranked pickups use waivers_and_breakouts, which already analyzes the entire eligible pool; do not redundantly fetch catalog directories."),
    "player_evidence": (EvidenceArgs,"Observed statistics, targets/carries/snaps, trends, weekly statistical estimates, historical variability, dated dynasty values and missing evidence. Use to compare named players or analyze ALL players in scope; never invent projections."),
    "team_needs": (Empty,"Analyze every team's measured positional strength and needs relative to this league, including coverage and replacement scarcity."),
    "find_trades": (TradeArgs,"Search actual opponent rosters using dashboard trade service; rank real packages by both-team lineup gains, dynasty fairness and opponent needs. No trade is also a valid result."),
    "evaluate_trade": (CompareTradeArgs,"Calculate an exact proposed trade for both teams, including unfavorable trades; validate ownership, roster drops, dynasty cost and gains. No acceptance probability."),
    "waivers_and_breakouts": (WaiverArgs,"Dashboard waiver service: evaluate all eligible free players, legal pickup/drop alternatives and opportunity-based breakout signals on actual rosters."),
    "breakout_candidates": (EvidenceArgs,"Independent breakout/opportunity scouting across my, free or all players, optionally by position. Works even when own missing starter evidence prevents waiver comparisons."),
    "optimize_lineup": (LineupArgs,"Dashboard lineup service: exact legal current/future starters, kickoff locks, byes, injury metadata, substitutions and clearly labeled statistical estimates. Defaults to CURRENT week."),
    "search_news": (SearchArgs,"Tavily current NFL research with publication/retrieval dates and URL citations. Use when current reporting materially changes a decision; cache duplicate queries and obey actual free allowance."),
}


class AgentTools:
    def __init__(self,config,store,league_service,snapshot,roster_id,web=True,protected=None,data_client=None,excluded=None):
        self.config,self.store,self.service=config,store,league_service
        self.snapshot,self.roster_id,self.web=snapshot,roster_id,web
        self.protected=protected or []
        self.data_client=data_client or NFLVerse(config,store)
        self.data=None
        self.values=None
        self.warnings=[]
        self.memo={}
        self.records=[]
        self.sources={}
        self.on_event=None
        self.research_error=None
        self.excluded=set(excluded or [])

    def declarations(self):
        from google.genai import types
        return [types.FunctionDeclaration(name=name,description=description,parameters_json_schema=model.model_json_schema())
                for name,(model,description) in TOOLS.items() if self.web or name!="search_news"]

    def load_data(self):
        if self.data is None:
            self.data=self.data_client.load(int(self.snapshot.season),dynasty=self.snapshot.league_type=="dynasty",scoring_rules=self.snapshot.scoring)
            self.data.schedule,source=self.data_client.csv("nflverse current schedule",SCHEDULE_URL,{"season","week","home_team","away_team","gameday"},ttl=300)
            self.data.sources.append(source)
        return self.data

    def evidence(self):
        if self.values is None:
            self.values,self.warnings=evaluate_players(self.snapshot,self.load_data(),self.snapshot.week,18,self.config.dynasty_max_age_days)
        return self.values

    def _players(self,ids):
        ownership={p:r.roster_id for r in self.snapshot.rosters for p in owned(r)}
        result={}
        for pid in sorted(ids):
            if pid not in self.snapshot.players:continue
            p=self.snapshot.players[pid]
            result[pid]={"name":p.name,"positions":p.positions,"team":p.team,"owner_roster_id":ownership.get(pid),
                **({"injury_status":p.injury_status} if p.injury_status else {}),
                **({"status":p.status} if p.status else {}),**({"active":False} if not p.active else {}),
                **({"known":False} if not p.known else {})}
        return result

    def _execute(self,name,a):
        if name!="search_news" and (utcnow()-self.snapshot.refreshed_at).total_seconds()>self.config.league_cache_seconds:
            fresh=self.service.load(self.snapshot.league_id,force=True)
            self._check_refresh(fresh)
            self.snapshot=fresh
        s=self.snapshot
        if name=="team_strategy":
            return {tool:self.call(tool,{},self.on_event) for tool in
                    ("get_league","team_needs","waivers_and_breakouts","optimize_lineup","find_trades")}
        if name=="get_league":
            return compact_context(s,self.roster_id)
        if name in {"find_players","get_free_agents"}:
            pool=free_players(s) if name=="get_free_agents" else s.players.values()
            ids=[p.player_id for p in pool if (not a.position or a.position.upper() in p.positions) and
                 (not a.query or a.query.casefold() in p.name.casefold() or a.query==p.player_id)]
            return {"count":len(ids),"players":self._players(ids),"ownership_at":s.refreshed_at.isoformat(),"catalog_at":s.catalog_at.isoformat()}
        if name=="player_evidence":
            values=self.evidence()
            roster=next(r for r in s.rosters if r.roster_id==self.roster_id)
            ids=set(a.player_ids) if a.player_ids else owned(roster) if a.scope=="my" else {p.player_id for p in free_players(s)} if a.scope=="free" else set(s.players)
            if a.position:ids={p for p in ids if p in s.players and a.position.upper() in s.players[p].positions}
            unknown=ids-s.players.keys()
            if unknown:raise ValueError("Unknown IDs; resolve through find_players: "+str(sorted(unknown)))
            exclude=set() if a.include_history else {"weekly_observed","weekly","opponents","schedule_factors"}
            return {"players":self._players(ids),"evidence":{p:values[p].model_dump(mode="json",exclude=exclude) for p in sorted(ids) if p in values},
                    "history_included":a.include_history,
                    "missing_evaluation_ids":sorted(ids-values.keys()),"warnings":self.warnings,
                    "sources":[x.model_dump(mode="json") for x in self.data.sources]}
        if name=="team_needs":
            values=self.evidence();reports=[]
            strengths={}
            free_ids={p.player_id for p in free_players(s)}
            replacement={}
            for pos in ("QB","RB","WR","TE"):
                points=sorted([v.projected_ppg for p,v in values.items() if p in free_ids and v.position==pos and v.available],reverse=True)
                replacement[pos]=statistics.median(points[:5]) if points else None
            for roster in s.rosters:
                ids=owned(roster)-set(roster.reserve+roster.taxi)
                strengths[roster.roster_id]={pos:sum(sorted([values[p].projected_ppg for p in ids if p in values and values[p].available and values[p].position==pos],reverse=True)[:max(1,s.roster_positions.count(pos))]) for pos in ("QB","RB","WR","TE")}
            medians={pos:statistics.median([v[pos] for v in strengths.values()]) for pos in ("QB","RB","WR","TE")}
            for roster in s.rosters:
                relative={p:round(v-medians[p],2) for p,v in strengths[roster.roster_id].items()}
                reports.append({"roster_id":roster.roster_id,"manager":roster.manager,"relative_positional_estimate":relative,
                    "needs":[p for p in sorted(relative,key=relative.get) if relative[p]<0],
                    "strengths":[p for p in sorted(relative,key=relative.get,reverse=True) if relative[p]>0],
                    "evaluated_players":len(owned(roster)&values.keys()),
                    "missing_ids":sorted(owned(roster)-values.keys())})
            return {"teams":reports,"replacement_ppg":replacement,"basis":"Best positional starters versus league median; free replacement is median of best five measured free players. Flex opportunity cost is recomputed by trade/waiver tools.","warnings":self.warnings,
                    "sources":[x.model_dump(mode="json") for x in self.data.sources]}
        if name=="find_trades":
            options=TradeOptions(structures=[tuple(x) for x in a.structures],receive_position=a.position.upper() if a.position else None,
                                 opponent_id=a.opponent_id,must_send=a.must_send,max_results=a.results)
            run=TradeService(self.config,self.store,self.service,self.data_client).analyze(s,self.roster_id,options,
                    data=self.load_data(),evaluations=(self.evidence(),self.warnings))
            result=run.model_dump(mode="json");result.pop("evaluations")
            result["players"]=self._players({p for t in run.trades for p in t.send+t.receive+t.my_drops+t.opponent_drops})
            return result
        if name=="evaluate_trade":
            engine=TradeEngine(s,self.load_data(),self.config)
            proposal=engine.compare(self.roster_id,a.opponent_id,a.send,a.receive,TradeOptions(),enforce_preferences=False)
            return {"trade":proposal.model_dump(mode="json") if proposal else None,"players":self._players(a.send+a.receive),
                    "limitations":engine.warnings+["A null trade means missing valuation/availability or unfillable/capacity constraints; do not assert it is fair or beneficial."],
                    "sources":[x.model_dump(mode="json") for x in self.data.sources]}
        if name=="waivers_and_breakouts":
            run=WaiverService(self.config,self.store,self.service,self.data_client).analyze(s,self.roster_id,sorted(set(self.protected+a.protected)),a.strategy.replace("_"," "),
                    data=self.load_data(),evaluations=(self.evidence(),self.warnings))
            result=run.model_dump(mode="json");result.pop("evaluations")
            if a.position:
                result["pickups"]=[p for p in result["pickups"] if a.position.upper() in s.players[p["player_id"]].positions]
                result["breakouts"]=[p for p in result["breakouts"] if a.position.upper() in s.players[p["player_id"]].positions]
            if a.breakout_scope!="all":
                ids={p.player_id for p in free_players(s)} if a.breakout_scope=="available" else owned(next(r for r in s.rosters if r.roster_id==self.roster_id))
                result["breakouts"]=[b for b in result["breakouts"] if b["player_id"] in ids]
            result["breakout_scope"]=a.breakout_scope
            result["players"]=self._players({p["player_id"] for k in ("pickups","breakouts") for p in result[k]}|{p["drop_id"] for p in result["pickups"] if p["drop_id"]})
            return result
        if name=="breakout_candidates":
            values=self.evidence()
            selected=set(a.player_ids) if a.player_ids else owned(next(r for r in s.rosters if r.roster_id==self.roster_id)) if a.scope=="my" else {p.player_id for p in free_players(s)} if a.scope=="free" else set(values)
            signals=[b for b in breakout_signals(values) if b.player_id in selected and (not a.position or values[b.player_id].position==a.position.upper())]
            return {"breakouts":[b.model_dump(mode="json") for b in signals],"pickups":[],"players":self._players([b.player_id for b in signals]),
                "sources":[x.model_dump(mode="json") for x in self.data.sources],"warnings":self.warnings,"snapshot_at":s.refreshed_at.isoformat()}
        if name=="optimize_lineup":
            for pid in set(a.exclude_players)-self.excluded:
                if a.exclusion_sources.get(pid) not in self.sources:
                    raise ValueError("Retrieve and cite a current report before adding an AI lineup exclusion; no inactivity was inferred.")
            report=LineupService(self.config,self.store,self.service,self.data_client).analyze(s,self.load_data(),self.roster_id,a.week,a.strategy,
                    evaluations=(self.evidence(),self.warnings),excluded=self.excluded|set(a.exclude_players))
            result=report.model_dump(mode="json");result["players"]=self._players(report.evidence)
            return result
        if name=="search_news":
            if not self.web:raise ValueError("Web research is disabled for this question.")
            if self.research_error:raise ValueError("Research unavailable for this turn: "+self.research_error)
            try:bundle=Research(self.config,self.store).search(a.query,a.time_range)
            except RuntimeError as exc:
                self.research_error=str(exc);raise
            self.sources.update({x.url:x for x in bundle.sources})
            return bundle.model_dump(mode="json")
        raise ValueError("Unknown analysis tool.")

    def _check_refresh(self,fresh):
        if analysis_fingerprint(fresh)!=analysis_fingerprint(self.snapshot):
            raise ValueError("League changed during analysis. Start a new question so every calculation uses the refreshed ownership and settings.")

    def call(self,name,args,on_event=None):
        if name not in TOOLS or (name=="search_news" and not self.web):
            return {"error":"Unknown or disabled tool: "+str(name)}
        if on_event:on_event(name)
        if on_event:self.on_event=on_event
        try:
            parsed=TOOLS[name][0].model_validate(args or {})
            key=name+":"+parsed.model_dump_json()
            cached=key in self.memo
            if cached:result=self.memo[key]
            else:
                result=self._execute(name,parsed)
                self.memo[key]=result
            self.records.append({"tool":name,"arguments":parsed.model_dump(mode="json"),"cached":cached,
                "result":{"analyses":list(result),"note":"Individual calculations are recorded above."} if name=="team_strategy" else result})
            return {"result":self.for_model(name,result),"cached_this_turn":cached,
                    "player_directory_url":"https://sleeper.com/nfl/players"}
        except Exception as exc:
            error=safe_error(exc,self.config.gemini_api_key.get_secret_value(),self.config.tavily_api_key.get_secret_value())
            self.records.append({"tool":name,"arguments":args,"error":error})
            return {"error":error,"recovery":"Do not invent the unavailable result. Explain the source/validation failure; use other available evidence or ask the user to retry."}

    def validate_sources(self,answer):
        """A fluent citation is not evidence that its URL was ever retrieved."""
        allowed={"https://sleeper.com/nfl/players"}
        allowed.update(s.url for s in self.sources.values())
        if self.data:allowed.update(s.url for s in self.data.sources)
        for record in self.records:
            for source in record.get("result",{}).get("sources",[]):
                if isinstance(source,dict) and source.get("url"):allowed.add(source["url"])
        validate_answer_sources(answer,allowed)

    @staticmethod
    def for_model(name,result):
        """Keep every candidate, without resending repetitive per-player prose or
        histories. Full calculations remain in the UI; evidence tool supplies
        requested detailed histories. This is data shaping, not a player cap.
        """
        result=dict(result)
        if name=="get_league":
            result["player_columns"]=["player_id","name","positions","team","catalog_injury"]
            result["players"]=[[pid,p["name"],p["pos"],p["team"],p["catalog_injury"]] for pid,p in result["players"].items()]
            result["matchups"]=[{k:v for k,v in m.items() if k in {"roster_id","matchup_id","points","starters","starters_points","custom_points"}} for m in result["matchups"]]
            result["recent_transactions"]=[{k:v for k,v in t.items() if k in {"type","status","roster_ids","adds","drops","settings","created","status_updated","waiver_budget"}} for t in result["recent_transactions"]]
        if name!="get_league" and isinstance(result.get("players"),dict):
            columns=["player_id","name","positions","team","owner_roster_id","injury_status","status","active","known"]
            result["player_columns"]=columns
            result["players"]=[[pid,*[p.get(k,True if k in {"active","known"} else None) for k in columns[1:]]] for pid,p in result["players"].items()]
        if name=="find_trades":
            rows=[]
            for trade in result["trades"]:
                row={k:v for k,v in trade.items() if k not in {"my_after","opponent_after","reasons"}}
                row["opponent_incentive"]=trade["reasons"][3] if len(trade["reasons"])>3 else "Inspect both-team gains and needs."
                rows.append(row)
            result["trades"]=rows
            result["detail_note"]="Every ranked proposal is retained. Exact after-trade lineups and full reasons are recorded in Supporting evidence; evaluate_trade can retrieve a selected package in detail."
        if name in {"waivers_and_breakouts","breakout_candidates"}:
            metrics=["opportunities","targets","carries","snap_share","target_share","red_zone_opportunities"]
            columns=["player_id","score","label","confidence","recent_games","prior_games"]+[f"{m}_{t}" for m in metrics for t in ("prior","recent","change")]
            rows=[]
            for b in result["breakouts"]:
                changes={c["metric"]:c for c in b["changes"]}
                rows.append([b[k] for k in columns[:6]]+[changes.get(m,{}).get(t) for m in metrics for t in ("prior","recent","change")])
            return {**result,"breakout_columns":columns,"breakouts":rows,
                "detail_note":"All signals in the requested scope retained as tabular rows. Full history, limitations and metrics are available through player_evidence(include_history=true)."}
        if name=="optimize_lineup":
            fields={"position","games","last_week","season_ppg","recent_ppg","projected_ppg","floor","upside","targets","carries","recent_opportunities","opportunity_trend","snap_pct","available","limitations","method","estimate"}
            return {**result,"evidence":{p:{k:v for k,v in e.items() if k in fields} for p,e in result["evidence"].items()},
                    "detail_note":"All evaluated roster players retained. Retrieve full weekly histories with player_evidence(include_history=true)."}
        if name=="player_evidence" and not result.get("history_included") and result.get("evidence"):
            columns=list(next(iter(result["evidence"].values())))
            return {**result,"evidence_columns":columns,"evidence":[[e.get(k) for k in columns] for e in result["evidence"].values()]}
        return result


class Analyst:
    def __init__(self,config,store,service,gemini=None):
        self.config,self.store,self.service=config,store,service
        self.gemini=gemini or Gemini(config,store)

    def run(self,snapshot,roster_id,question,history,web=True,protected=None,on_event=None,excluded=None):
        fresh=self.service.load(snapshot.league_id,force=True)
        if not any(r.roster_id==roster_id for r in fresh.rosters):
            raise ValueError("The selected team no longer exists in this league. Choose your team again.")
        tools=AgentTools(self.config,self.store,self.service,fresh,roster_id,web,protected,excluded=excluded)
        self.last_tools=tools
        for message in history:
            if message.get("role")=="assistant" and message.get("research"):
                bundle=ResearchBundle.model_validate(message["research"])
                for source in bundle.sources:
                    if 0<=(utcnow()-source.retrieved_at).total_seconds()<=14400:
                        tools.sources[source.url]=source
        text=self.gemini.run_agent({"league_id":fresh.league_id,"season":fresh.season,"week":fresh.week,
            "my_roster_id":roster_id,"refreshed_at":fresh.refreshed_at.isoformat(),"web_enabled":web,
            "recent_research":[{"url":s.url,"published_at":s.published_at,"retrieved_at":s.retrieved_at.isoformat()} for s in tools.sources.values()]},question,history,tools,on_event)
        tools.validate_sources(text)
        # A long research/model turn may overlap a claim, trade or starter change.
        # Verify the same ownership/settings immediately before showing advice.
        verified=self.service.load(fresh.league_id,force=True)
        tools._check_refresh(verified)
        bundle=ResearchBundle(query=question,sources=list(tools.sources.values()))
        return verified,{"content":text,"role":"assistant","research":bundle.model_dump(mode="json"),
                      "tools":tools.records,"refreshed_at":verified.refreshed_at.isoformat()}
