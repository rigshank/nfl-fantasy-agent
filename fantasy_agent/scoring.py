"""League-specific offense scoring with explicit coverage, never stock PPR totals."""
import math


STAT_FIELDS = {
    "pass_yd": "passing_yards", "pass_td": "passing_tds", "pass_int": "passing_interceptions",
    "pass_cmp": "completions", "pass_att": "attempts", "pass_sack": "sacks_suffered",
    "pass_2pt": "passing_2pt_conversions", "pass_fd": "passing_first_downs",
    "rush_yd": "rushing_yards", "rush_td": "rushing_tds", "rush_att": "carries",
    "rush_2pt": "rushing_2pt_conversions", "rush_fd": "rushing_first_downs",
    "rec": "receptions", "rec_yd": "receiving_yards", "rec_td": "receiving_tds",
    "rec_2pt": "receiving_2pt_conversions", "rec_fd": "receiving_first_downs",
    "fum": "fumbles_total", "fum_lost": "fumbles_lost_total", "st_td": "special_teams_tds",
    "kr_yd": "kickoff_return_yards", "pr_yd": "punt_return_yards",
    "pass_cmp_40p": "passing_40", "rec_40p": "receiving_40", "rush_40p": "rushing_40",
    "pass_td_40p": "passing_tds_40_plus", "pass_td_50p": "passing_tds_50_plus",
    "rec_td_40p": "receiving_tds_40_plus", "rec_td_50p": "receiving_tds_50_plus",
    "rush_td_40p": "rushing_tds_40_plus", "rush_td_50p": "rushing_tds_50_plus",
    "pass_int_td": "passing_pick_sixes",
}
EVENT_FIELDS = {v for k, v in STAT_FIELDS.items() if k.endswith(("td_40p", "td_50p")) or k == "pass_int_td"}
# These fields affect slots held constant outside the offensive trade model.
NON_OFFENSE = {"sack", "sack_yd", "int", "fum_rec", "fum_rec_td", "safe", "ff", "tkl", "tkl_solo", "tkl_ast",
               "tkl_loss", "blk_kick", "pass_def", "qb_hit", "def_td", "def_2pt", "def_3_and_out",
               "def_4_and_stop", "def_pass_def", "def_st_td", "def_st_ff", "def_st_fum_rec", "st_ff", "st_fum_rec",
               "int_ret_yd", "fum_ret_yd", "blk_kick_ret_yd", "def_forced_punts"}
BONUSES = {"bonus_pass_yd_300": ("passing_yards", 300, 400),
           "bonus_pass_yd_400": ("passing_yards", 400, float("inf")),
           "bonus_rush_yd_100": ("rushing_yards", 100, 200),
           "bonus_rush_yd_200": ("rushing_yards", 200, float("inf")),
           "bonus_rec_yd_100": ("receiving_yards", 100, 200),
           "bonus_rec_yd_200": ("receiving_yards", 200, float("inf"))}
PREMIUMS = {"bonus_rec_te": "TE", "bonus_rec_rb": "RB", "bonus_rec_wr": "WR"}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def ignored_rule(key):
    return key in NON_OFFENSE or key.startswith(("pts_allow", "yds_allow", "fg", "xp", "idp_", "bonus_def_", "def_"))


def unsupported_rules(rules):
    return sorted(k for k, v in rules.items() if v and k not in STAT_FIELDS and k not in BONUSES
                  and k not in PREMIUMS and k != "pass_inc" and not ignored_rule(k))


def score_offense(row, rules, position):
    unsupported = unsupported_rules(rules)
    if unsupported:
        raise ValueError("Unsupported offensive scoring: " + ", ".join(unsupported))
    total = 0.0
    for key, weight in rules.items():
        if not weight or ignored_rule(key):
            continue
        if key in PREMIUMS:
            if position != PREMIUMS[key]:
                continue
            value = number(row.get("receptions"))
        elif key in BONUSES:
            field, lo, hi = BONUSES[key]
            observed = number(row.get(field))
            value = float(lo <= observed < hi) if observed is not None else None
        elif key == "pass_inc":
            a, c = number(row.get("attempts")), number(row.get("completions"))
            value = a - c if a is not None and c is not None else None
        else:
            value = number(row.get(STAT_FIELDS[key]))
        if value is None:
            raise ValueError(f"Missing scoring field for {key}")
        total += weight * value
    return total
