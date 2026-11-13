"""Scoring constants for Fantasy Premier League (2025/26 rules, incl. defensive contribution points)."""

POS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
POS_ID = {v: k for k, v in POS.items()}

# points per goal / per clean sheet by position id
GOAL_PTS = {1: 10, 2: 6, 3: 5, 4: 4}
CS_PTS = {1: 4, 2: 4, 3: 1, 4: 0}
# defensive-contribution thresholds that earn +2 (DEF: CBIT>=10, MID/FWD: CBIRT>=12)
DC_THRESHOLD = {2: 10, 3: 12, 4: 12}

# the additive pieces of a projection; calibration factors are fitted per (position, component)
COMPONENTS = ("app", "goal", "assist", "cs", "gc", "dc", "bonus", "sav", "yc")
