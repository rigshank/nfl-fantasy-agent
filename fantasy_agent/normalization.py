from .models import Player, Roster


def player_from_raw(pid: str, raw: dict) -> Player:
    name = raw.get("full_name") or " ".join(filter(None, [raw.get("first_name"), raw.get("last_name")]))
    return Player(player_id=str(pid), name=name or str(pid),
                  positions=raw.get("fantasy_positions") or ([raw["position"]] if raw.get("position") else []),
                  team=raw.get("team"), status=raw.get("status"),
                  injury_status=raw.get("injury_status"), active=raw.get("active") is not False)


def roster_from_raw(raw: dict, users: dict) -> Roster:
    owner = raw.get("owner_id")
    user = users.get(owner, {})
    metadata = user.get("metadata") or {}
    return Roster(roster_id=raw["roster_id"], owner_id=owner,
                  avatar=metadata.get("avatar") or user.get("avatar"),
                  co_owners=raw.get("co_owners") or [],
                  manager=metadata.get("team_name") or user.get("display_name") or f"Team {raw['roster_id']}",
                  **{k: raw.get(k) or [] for k in ("players", "starters", "reserve", "taxi")},
                  settings=raw.get("settings") or {}, metadata=raw.get("metadata") or {})


def league_type(settings: dict) -> str:
    return {0: "redraft", 1: "keeper", 2: "dynasty"}.get(settings.get("type"), "unknown")
