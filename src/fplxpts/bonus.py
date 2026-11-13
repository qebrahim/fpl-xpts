"""Bonus points modelled by how they are earned.

Bonus goes to the top three BPS in a match, and BPS is driven by goals, assists, clean sheets and saves plus
many small actions (passes, tackles, key passes...). We estimate, per position, how much bonus an extra event is
worth on average:

    bonus ~ base * (minutes/90) + b_goal * goals + b_assist * assists + b_cs * clean_sheet + b_sav * saves

fitted by ridge least squares on match rows up to the cutoff. A player's projected bonus is then

    base90_player * minutes_fraction + sum_k b_k * E[event_k in this fixture]

so a striker facing a leaky defence, or a defender with a likely clean sheet, gets more bonus than the same
player in a tough fixture, and bonus no longer ignores the expected goals/assists/clean sheet of the match.
`base90_player` is the position base plus the player's own shrunk residual (bonus not explained by events),
which captures players who earn BPS through non-scoring actions.
"""
from __future__ import annotations

# events that carry BPS for each position (FWD/MID get no clean-sheet BPS; only keepers get save BPS)
EVENTS = {1: ("goal", "assist", "cs", "sav"), 2: ("goal", "assist", "cs"), 3: ("goal", "assist"), 4: ("goal", "assist")}
RIDGE = 1.0   # pseudo-observations pulling event coefficients towards 0 (the base term is not penalised)


def event_counts(row: dict, pos: int) -> dict:
    """Bonus-relevant events in one match row."""
    return {
        "goal": row["goals_scored"],
        "assist": row["assists"],
        "cs": row["clean_sheets"] if row["minutes"] >= 60 else 0,
        "sav": row["saves"] if pos == 1 else 0,
    }


def _solve(a: list, b: list) -> list:
    """Solve a x = b by Gauss-Jordan elimination with partial pivoting (tiny systems, no numpy needed)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        d = m[c][c]
        m[c] = [v / d for v in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [v - f * w for v, w in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def fit_bonus_coefs(rows: list, pos: int, ridge: float = RIDGE) -> dict:
    """{'base': bonus per 90 from nothing but playing, 'goal': .., 'assist': .., ...}: all >= 0.

    `rows` are (match row) dicts for players of position `pos`. Returns zeros when there is no data.
    """
    evs = EVENTS[pos]
    rows = [r for r in rows if r["minutes"] > 0]
    k = len(evs) + 1
    if not rows:
        return {"base": 0.0, **{e: 0.0 for e in evs}}
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for r in rows:
        ev = event_counts(r, pos)
        x = [r["minutes"] / 90] + [float(ev[e]) for e in evs]
        for i in range(k):
            xty[i] += x[i] * r["bonus"]
            for j in range(k):
                xtx[i][j] += x[i] * x[j]
    for i in range(1, k):
        xtx[i][i] += ridge
    xtx[0][0] += 1e-9
    beta = _solve(xtx, xty)
    return {"base": max(beta[0], 0.0), **{e: max(b, 0.0) for e, b in zip(evs, beta[1:])}}


def residual(row: dict, pos: int, coefs: dict) -> float:
    """Bonus in this match not explained by its events or minutes."""
    ev = event_counts(row, pos)
    fitted = coefs["base"] * row["minutes"] / 90 + sum(coefs.get(e, 0.0) * ev[e] for e in EVENTS[pos])
    return row["bonus"] - fitted


def expected_bonus(base90: float, coefs: dict, mf: float, events: dict) -> float:
    """Expected bonus for a fixture: baseline per 90 x expected minutes + marginal bonus x expected events."""
    return base90 * mf + sum(coefs.get(e, 0.0) * v for e, v in events.items())
