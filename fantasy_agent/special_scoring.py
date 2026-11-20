"""Covered Sleeper kicker, team-defense and IDP rules on nflverse evidence.

Unknown categories and absent fields fail explicitly. No default scoring values.
"""
import re
from .scoring import number, NON_OFFENSE

KICKING = {"fgm": "fg_made", "fgmiss": "fg_missed", "xpm": "pat_made", "xpmiss": "pat_missed",
           "fgm_yds": "fg_made_distance", "fgmiss_yds": "fg_missed_distance"}
DEFENSE = {"sack": "def_sacks", "int": "def_interceptions", "fum_rec": "fumble_recovery_opp",
    "safe": "def_safeties", "ff": "def_fumbles_forced", "tkl_solo": "def_tackles_solo",
    "tkl_ast": "def_tackle_assists", "tkl_loss": "def_tackles_for_loss", "qb_hit": "def_qb_hits",
    "pass_def": "def_pass_defended", "def_pass_def": "def_pass_defended", "def_td": "def_tds",
    "sack_yd": "def_sack_yards",
    "def_st_td": "special_teams_tds", "def_2pt": "def_2pt_made", "int_ret_yd": "def_interception_yards",
    "fum_ret_yd": "fumble_recovery_yards_opp", "fum_rec_td": "fumble_recovery_tds"}


def field(row, key):
    value = number(row.get(key))
    if value is None:
        raise ValueError("Missing scoring field: " + key)
    return value


def score_special(row, rules, kind, opponent=None):
    if kind == "IDP":
        # Sleeper keeps individual weights separate from team-defense weights.
        rules = {k.removeprefix("idp_"):v for k,v in rules.items() if k.startswith("idp_")}
    elif kind == "DEF":
        rules = {k:v for k,v in rules.items() if not k.startswith("idp_")}
    total, relevant = 0., 0
    for rule, weight in rules.items():
        if not weight:
            continue
        if kind == "K":
            if not rule.startswith(("fg", "xp")):
                continue
            if rule == "fgmiss":
                value = field(row,"fg_att") - field(row,"fg_made")
            elif rule == "xpmiss":
                value = field(row,"pat_att") - field(row,"pat_made")
            elif rule == "fgmiss_yds":
                value = field(row,"fg_missed_distance") + field(row,"fg_blocked_distance")
            elif rule in KICKING:
                value = field(row, KICKING[rule])
            elif rule == "fgm_50p":
                value = field(row, "fg_made_50_59") + field(row, "fg_made_60_")
            elif rule == "fgm_60p":
                value = field(row, "fg_made_60_")
            elif re.fullmatch(r"fgm_(0_19|20_29|30_39|40_49)", rule):
                value = field(row, "fg_made_" + rule[4:])
            elif re.fullmatch(r"fgmiss_(0_19|20_29|30_39|40_49|50_59)", rule):
                value = field(row, "fg_missed_" + rule[7:])
                lo,hi=map(int,rule[7:].split("_"))
                value += sum(lo<=d<=hi for d in blocked_distances(row))
            elif rule == "fgmiss_50p":
                value = field(row, "fg_missed_50_59") + field(row, "fg_missed_60_")
                value += sum(d>=50 for d in blocked_distances(row))
            else:
                raise ValueError("Unsupported kicker scoring: " + rule)
        else:
            is_defense = kind == "IDP" or rule in NON_OFFENSE or rule in DEFENSE or rule.startswith(("pts_allow", "yds_allow", "def_", "idp_", "bonus_def_"))
            if not is_defense:
                continue
            if kind != "DEF" and rule.startswith(("pts_allow", "yds_allow", "def_st_")):
                continue
            if rule in DEFENSE:
                value = field(row, DEFENSE[rule])
            elif rule == "tkl":
                value = field(row, "def_tackles_solo") + field(row, "def_tackle_assists")
            elif rule == "blk_kick":
                value = sum(field(row, k) for k in ("def_punt_blocks", "def_pat_blocks", "def_fg_blocks"))
            elif rule.startswith(("pts_allow", "yds_allow")) and opponent is not None:
                prefix = "pts_allow" if rule.startswith("pts_allow") else "yds_allow"
                if prefix == "pts_allow":
                    # Sleeper charges all opponent PATs/2PTs, including after a
                    # defensive TD, plus offensive and special-teams TDs/FGs.
                    # Scoreboard includes offensive fumble-recovery TDs and all
                    # conversion points. Exclude opposing defense TDs/safeties,
                    # not the PATs that followed those touchdowns.
                    actual = field(opponent,"points_scored") - 6*field(opponent,"def_tds") - 2*field(opponent,"def_safeties")
                    if actual < 0:
                        raise ValueError("Inconsistent defense points-allowed evidence")
                else:
                    actual = field(opponent, "passing_yards") - field(opponent, "sack_yards_lost") + field(opponent, "rushing_yards")
                suffix = rule[len(prefix):].lstrip("_")
                if not suffix:
                    value = actual
                elif suffix == "0":
                    value = float(actual == 0)
                elif re.fullmatch(r"\d+_\d+", suffix):
                    lo, hi = map(int, suffix.split("_"))
                    value = float(lo <= actual <= hi)
                elif re.fullmatch(r"\d+p", suffix):
                    value = float(actual >= int(suffix[:-1]))
                else:
                    raise ValueError("Unsupported defensive range: " + rule)
            else:
                raise ValueError("Unsupported defensive scoring: " + rule)
        total += weight * value
        relevant += 1
    if not relevant:
        raise ValueError("No covered scoring configured for " + kind)
    return total


def blocked_distances(row):
    count=field(row,"fg_blocked")
    if not count:return []
    try:
        distances=[float(v) for v in str(row.get("fg_blocked_list") or "").split(";") if v]
    except ValueError:
        raise ValueError("Invalid blocked field-goal distance list") from None
    if len(distances)!=count:
        raise ValueError("Missing blocked field-goal distances")
    return distances
