"""Bookmaker odds -> expected goals per side, used to anchor the model's team-level expectations.

Pieces (all pure except the two small fetchers, which cache on disk):

- de-vig of 1X2 and over/under prices (proportional normalisation of the implied probabilities);
- conversion of (P(home win), P(away win), P(over L goals)) to Poisson expected goals (lambda_home, lambda_away):
  the total T = lambda_home + lambda_away is fixed by P(over L) alone (the sum of two Poissons is Poisson(T)), then
  the split is fixed by P(home) / (P(home) + P(away)); both are monotone, so each is solved by bisection;
- team-name mapping to FPL team ids (fails loudly on an unknown name);
- ``MatchOdds``: one fixture's odds-implied expected goals, keyed by (home team id, away team id).

Sources:

1. **Football-Data.co.uk** (historical, for the backtest): free CSVs of results and bookmaker odds per season,
   https://www.football-data.co.uk/ (Premier League file ``https://www.football-data.co.uk/mmz4281/{yyyy}/E0.csv``,
   column notes at https://www.football-data.co.uk/notes.txt). The site offers these files as free downloads; we
   fetch the one file once into the cache directory and re-read it from disk (``football-data_E0_{yyyy}.csv``),
   re-downloading only when it is older than the ttl. The backtest uses the pre-match average columns
   (``AvgH/AvgD/AvgA``, ``Avg>2.5/Avg<2.5``) as the realistic proxy for odds fetched days before kickoff; the
   closing columns (``AvgC...``) are only an upper bound. The same loader serves past seasons (``season_code`` of
   that season's fixtures, e.g. "2425"; ``fplxpts backtest --season``); 2019/20 onwards have the ``Avg*`` columns.
2. **The Odds API v4** (live, upcoming fixtures): https://the-odds-api.com/liveapi/guides/v4/ . Needs a key in the
   ``ODDS_API_KEY`` environment variable (or a ``.env`` file in the working directory; a non-empty environment
   variable wins). One call (``markets=h2h,totals``, ``regions=uk``) costs 2 credits of the plan's monthly quota, so
   the response is cached on disk for 12 hours (``odds-api_soccer_epl.json``, which never contains the key). The key
   is never printed, logged, cached or put in an exception message.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------------------------------------------
# probabilities and the Poisson solver


def devig(prices: list[float]) -> list[float]:
    """Decimal prices of one market's mutually exclusive outcomes -> probabilities summing to 1 (proportional)."""
    if not prices or any(p <= 1.0 for p in prices):
        raise ValueError(f"decimal prices must be > 1: {prices}")
    inv = [1.0 / p for p in prices]
    z = sum(inv)
    return [x / z for x in inv]


def devig_1x2(home: float, draw: float, away: float) -> tuple[float, float, float]:
    ph, pd, pa = devig([home, draw, away])
    return ph, pd, pa


def devig_two_way(over: float, under: float) -> tuple[float, float]:
    po, pu = devig([over, under])
    return po, pu


def _pmf(lam: float, kmax: int) -> list[float]:
    out, p = [], math.exp(-lam)
    for k in range(kmax + 1):
        out.append(p)
        p *= lam / (k + 1)
    return out


def _kmax(lam: float) -> int:
    return int(lam + 10 * math.sqrt(lam) + 12)


def p_over(total: float, line: float) -> float:
    """P(goals > line) for goals ~ Poisson(total); line must be a half-integer (2.5, 3.5, ...)."""
    if not is_half_line(line):
        raise ValueError(f"only half-goal lines are supported, got {line}")
    return 1.0 - sum(_pmf(total, int(line)))


def result_probs(lam_h: float, lam_a: float) -> tuple[float, float, float]:
    """(P(home win), P(draw), P(away win)) for independent Poisson goals."""
    ph_, pa_ = _pmf(lam_h, _kmax(lam_h)), _pmf(lam_a, _kmax(lam_a))
    cum_a, s = [], 0.0
    for x in pa_:
        s += x
        cum_a.append(s)
    home = sum(p * cum_a[min(i - 1, len(cum_a) - 1)] for i, p in enumerate(ph_) if i > 0)
    draw = sum(ph_[i] * pa_[i] for i in range(min(len(ph_), len(pa_))))
    return home, draw, max(0.0, 1.0 - home - draw)


def is_half_line(line: float) -> bool:
    return abs(line - math.floor(line) - 0.5) < 1e-9 and line > 0


def _bisect(f, lo: float, hi: float, target: float, iters: int = 100) -> float:
    """x in [lo, hi] with f(x) = target for increasing f (clamped to the ends)."""
    if f(lo) >= target:
        return lo
    if f(hi) <= target:
        return hi
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def total_from_over(p: float, line: float = 2.5) -> float:
    """Expected total goals T with P(Poisson(T) > line) = p (exact inverse of `p_over`)."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"P(over) must be in (0, 1), got {p}")
    return _bisect(lambda t: p_over(t, line), 1e-6, 15.0, p)


def split_total(total: float, p_home: float, p_away: float) -> tuple[float, float]:
    """(lambda_home, lambda_away) summing to `total` whose Poisson P(home)/(P(home)+P(away)) matches the odds."""
    if p_home <= 0 or p_away <= 0:
        raise ValueError("win probabilities must be positive")
    r = p_home / (p_home + p_away)

    def share(s: float) -> float:
        h, _, a = result_probs(s * total, (1 - s) * total)
        return h / (h + a)

    s = _bisect(share, 1e-4, 1 - 1e-4, r)
    return s * total, (1 - s) * total


def implied_lambdas(p_home: float, p_away: float, p_over_line: float, line: float = 2.5) -> tuple[float, float]:
    """Poisson expected goals (home, away) implied by de-vigged P(home), P(away) and P(over `line`)."""
    return split_total(total_from_over(p_over_line, line), p_home, p_away)


# ---------------------------------------------------------------------------------------------------------------
# records and team names


@dataclass(frozen=True)
class MatchOdds:
    """One fixture's odds-implied Poisson expected goals. Key: (home, away) FPL team ids (unique within a season);
    `kickoff` (ISO date) is kept to check the match against the FPL fixture's date."""
    home: int
    away: int
    kickoff: str | None
    lam_home: float
    lam_away: float
    p_home: float = 0.0
    p_draw: float = 0.0
    p_away: float = 0.0
    n_books: int = 0


def match_odds(home: int, away: int, kickoff: str | None, ph: float, pd: float, pa: float, total: float,
               n_books: int = 0) -> MatchOdds:
    lh, la = split_total(total, ph, pa)
    return MatchOdds(home, away, kickoff, lh, la, ph, pd, pa, n_books)


# Bookmaker / data-source names -> FPL short names. Football-Data.co.uk and The Odds API spellings.
TEAM_NAMES = {
    "arsenal": "ARS", "aston villa": "AVL", "bournemouth": "BOU", "afc bournemouth": "BOU",
    "brentford": "BRE", "brighton": "BHA", "brighton and hove albion": "BHA", "brighton & hove albion": "BHA",
    "burnley": "BUR", "chelsea": "CHE", "coventry": "COV", "coventry city": "COV",
    "crystal palace": "CRY", "everton": "EVE", "fulham": "FUL", "hull": "HUL", "hull city": "HUL",
    "ipswich": "IPS", "ipswich town": "IPS", "leeds": "LEE", "leeds united": "LEE",
    "leicester": "LEI", "leicester city": "LEI", "liverpool": "LIV", "luton": "LUT", "luton town": "LUT",
    "man city": "MCI", "manchester city": "MCI", "man united": "MUN", "manchester united": "MUN",
    "middlesbrough": "MID", "newcastle": "NEW", "newcastle united": "NEW",
    "nott'm forest": "NFO", "nottingham forest": "NFO", "sheffield united": "SHU", "sheffield utd": "SHU",
    "southampton": "SOU", "sunderland": "SUN", "tottenham": "TOT", "tottenham hotspur": "TOT",
    "west ham": "WHU", "west ham united": "WHU", "wolves": "WOL", "wolverhampton wanderers": "WOL",
}


def team_id(name: str, short_to_id: dict) -> int:
    """Source team name -> FPL team id. Raises KeyError naming the team if it is unknown or not in this season."""
    short = TEAM_NAMES.get(name.strip().lower())
    if short is None or short not in short_to_id:
        raise KeyError(f"unknown team name in odds data: {name!r}")
    return short_to_id[short]


def _days_apart(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def odds_by_round(odds: list[MatchOdds], fixtures: list, max_days: int = 3) -> dict:
    """{FPL event: {(home, away): MatchOdds}}; odds whose (home, away) pair has no FPL fixture with an event, or
    whose date is more than `max_days` from the FPL kickoff, are left out."""
    fx = {(f["team_h"], f["team_a"]): f for f in fixtures if f.get("event")}
    out: dict = {}
    for o in odds:
        f = fx.get((o.home, o.away))
        if f is None or _days_apart(o.kickoff, f.get("kickoff_time")) > max_days:
            continue
        out.setdefault(f["event"], {})[(o.home, o.away)] = o
    return out


def available_at(by_round: dict, cut: int) -> dict:
    """The odds a forecaster really has at cutoff `cut`: those for round cut + 1 only (fetched before it)."""
    return dict(by_round.get(cut + 1, {}))


# ---------------------------------------------------------------------------------------------------------------
# Football-Data.co.uk (historical)

FD_URL = "https://www.football-data.co.uk/mmz4281/{season}/E0.csv"
UA = {"User-Agent": "fplxpts research project"}


def football_data_csv(cache_dir: str | Path, season: str = "2627", ttl: int = 86400, fetch=None) -> str:
    """Text of the Football-Data.co.uk Premier League CSV for `season` (e.g. "2627"), downloaded at most once per
    `ttl` seconds into `cache_dir`. If the download fails and an (even stale) cached copy exists, that copy is used."""
    path = Path(cache_dir) / f"football-data_E0_{season}.csv"
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return path.read_text(encoding="utf-8-sig")
    try:
        raw = (fetch or _get)(FD_URL.format(season=season))
    except Exception:
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw.decode("utf-8-sig")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


def _fd_date(s: str) -> str:
    d, m, y = s.split("/")
    return f"{int(y) + (2000 if len(y) == 2 else 0):04d}-{int(m):02d}-{int(d):02d}"


FD_COLUMNS = {"open": ("AvgH", "AvgD", "AvgA", "Avg>2.5", "Avg<2.5"),
              "close": ("AvgCH", "AvgCD", "AvgCA", "AvgC>2.5", "AvgC<2.5")}


def parse_football_data(text: str, short_to_id: dict, kind: str = "open") -> list[MatchOdds]:
    """MatchOdds from a Football-Data CSV using the average pre-match (`kind="open"`) or closing (`"close"`) 1X2
    and over/under 2.5 prices. Rows with missing prices are skipped; an unknown team name raises."""
    h, d, a, o, u = FD_COLUMNS[kind]
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        if not r.get("HomeTeam"):
            continue
        home, away = team_id(r["HomeTeam"], short_to_id), team_id(r["AwayTeam"], short_to_id)
        try:
            prices = [float(r[c]) for c in (h, d, a, o, u)]
        except (KeyError, TypeError, ValueError):
            continue
        ph, pd, pa = devig_1x2(*prices[:3])
        po, _ = devig_two_way(*prices[3:])
        out.append(match_odds(home, away, _fd_date(r["Date"]), ph, pd, pa, total_from_over(po, 2.5)))
    return out


# ---------------------------------------------------------------------------------------------------------------
# The Odds API v4 (live)

ODDS_API_URL = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
ODDS_CACHE = "odds-api_soccer_epl.json"
SOURCE_NAME = "The Odds API"


class OddsError(RuntimeError):
    """A failed odds request. The message never contains the API key."""


def parse_dotenv(text: str) -> dict:
    """KEY=VALUE lines -> dict. Ignores blanks and # comments, an optional `export ` prefix, strips matching quotes
    around the value, and drops ` #` inline comments after unquoted values."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        elif " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        out[k] = v
    return out


def api_key(env: dict | None = None, dotenv: str | Path = ".env", name: str = "ODDS_API_KEY") -> str | None:
    """The key from the environment (non-empty wins), else from the `.env` file if present, else None."""
    env = os.environ if env is None else env
    if env.get(name):
        return env[name]
    p = Path(dotenv)
    if p.is_file():
        return parse_dotenv(p.read_text(encoding="utf-8")).get(name) or None
    return None


def fetch_odds_api(key: str, timeout: int = 30) -> tuple[list, dict]:
    """One live request. Returns (events, quota headers). Any failure is re-raised as OddsError without the key."""
    q = urllib.parse.urlencode({"apiKey": key, "regions": "uk", "markets": "h2h,totals", "oddsFormat": "decimal",
                                "dateFormat": "iso"})
    try:
        req = urllib.request.Request(f"{ODDS_API_URL}?{q}", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdr = {k: r.headers.get(k) for k in ("x-requests-remaining", "x-requests-used", "x-requests-last")}
            return json.loads(r.read()), hdr
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:  # noqa: BLE001 - re-raised sanitized below
        status = type(e).__name__
    raise OddsError(f"The Odds API request failed ({status})") from None


def cached_odds_api(cache_dir: str | Path, key: str | None, ttl: int = 12 * 3600, fetch=None) -> dict:
    """{"fetched_at", "source", "quota", "events"} from the disk cache if younger than `ttl`, else from one live
    request (then cached). Raises OddsError (without the key) if there is no fresh cache and no key, or the request
    fails; a stale cache is not used then (its odds may be for an earlier gameweek or long out of date)."""
    path = Path(cache_dir) / ODDS_CACHE
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text())
    if not key:
        raise OddsError("no ODDS_API_KEY set")
    events, quota = (fetch or fetch_odds_api)(key)
    payload = {"fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": SOURCE_NAME,
               "quota": quota, "events": events}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload


def event_odds(ev: dict, short_to_id: dict) -> MatchOdds | None:
    """One The Odds API event -> MatchOdds: de-vig each bookmaker's 1X2 and average; convert each bookmaker's
    half-goal totals line (any of 1.5, 2.5, 3.5, ...) to a Poisson total and average. None if a market is missing.
    Raises KeyError on an unknown team name."""
    home_name, away_name = ev["home_team"], ev["away_team"]
    home, away = team_id(home_name, short_to_id), team_id(away_name, short_to_id)
    probs, totals = [], []
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            oc = mk.get("outcomes", [])
            if mk.get("key") == "h2h":
                price = {o["name"]: o["price"] for o in oc}
                if {home_name, away_name, "Draw"} <= set(price):
                    try:
                        probs.append(devig_1x2(price[home_name], price["Draw"], price[away_name]))
                    except ValueError:
                        pass
            elif mk.get("key") == "totals":
                lines: dict = {}
                for o in oc:
                    if o.get("point") is not None:
                        lines.setdefault(float(o["point"]), {})[o["name"]] = o["price"]
                for line, pr in lines.items():
                    if is_half_line(line) and {"Over", "Under"} <= set(pr):
                        try:
                            totals.append(total_from_over(devig_two_way(pr["Over"], pr["Under"])[0], line))
                        except ValueError:
                            pass
    if not probs or not totals:
        return None
    ph, pd, pa = (sum(p[i] for p in probs) / len(probs) for i in range(3))
    return match_odds(home, away, ev.get("commence_time"), ph, pd, pa, sum(totals) / len(totals), len(probs))


def parse_odds_api(events: list, short_to_id: dict) -> tuple[list[MatchOdds], list[str]]:
    """(MatchOdds for events with both markets, unknown team names). Never raises on a bad event."""
    out, unknown = [], []
    for ev in events:
        try:
            m = event_odds(ev, short_to_id)
        except KeyError as e:
            unknown.append(str(e.args[0]) if e.args else "?")
            continue
        except (TypeError, ValueError):
            continue
        if m is not None:
            out.append(m)
    return out, unknown


@dataclass
class LiveOdds:
    """Live odds for the next gameweek, plus what to report about them."""
    by_fixture: dict          # {(home, away): MatchOdds} for fixtures in `gameweek`
    gameweek: int
    fixtures: int             # fixtures in that gameweek
    fetched_at: str | None
    unknown: list             # unmatched team-name messages
    note: str = ""            # why nothing was anchored, if so (no key, request failed, ...)

    @property
    def anchored(self) -> int:
        return len(self.by_fixture)

    def summary(self) -> dict | None:
        """The export JSON's "odds" field (None when nothing was anchored)."""
        if not self.by_fixture:
            return None
        return {"source": SOURCE_NAME, "fetched_at": self.fetched_at, "gameweek": self.gameweek,
                "fixtures_anchored": self.anchored, "fixtures_total": self.fixtures}

    def message(self) -> str:
        """One line for the CLI saying how many fixtures were anchored to odds and how many fell back."""
        why = f" ({self.note})" if self.note else ""
        extra = f"; unmatched team names: {', '.join(self.unknown)}" if self.unknown else ""
        return (f"Bookmaker odds: {self.anchored} of {self.fixtures} GW{self.gameweek} fixtures anchored to odds, "
                f"{self.fixtures - self.anchored} use the model's own numbers{why}{extra}")


def live_odds(season, gameweek: int, cache_dir: str | Path, key: str | None, ttl: int = 12 * 3600,
              fetch=None) -> LiveOdds:
    """Odds for the unfinished fixtures of `gameweek` (the next one), from the cache or one live request.
    Never raises: no key, a failed request or unmatched fixtures just mean fewer (or no) anchored fixtures, and the
    model's own numbers are used for the rest."""
    n = sum(1 for f in season.fixtures if f.get("event") == gameweek and not f.get("finished"))
    try:
        payload = cached_odds_api(cache_dir, key, ttl, fetch)
    except OddsError as e:
        return LiveOdds({}, gameweek, n, None, [], str(e))
    except Exception as e:  # noqa: BLE001 - odds must never break a run (e.g. a corrupt cache file)
        return LiveOdds({}, gameweek, n, None, [], f"odds cache unreadable: {type(e).__name__}")
    ms, unknown = parse_odds_api(payload.get("events", []), season.team_ids)
    rnd = odds_by_round(ms, [f for f in season.fixtures if not f.get("finished")]).get(gameweek, {})
    note = "" if rnd else "no odds for this gameweek yet"
    return LiveOdds(rnd, gameweek, n, payload.get("fetched_at"), unknown, note)


def season_code(fixtures: list) -> str:
    """Football-Data.co.uk season folder ("2627") from the earliest FPL kickoff date (seasons start in August)."""
    first = min(f["kickoff_time"] for f in fixtures if f.get("kickoff_time"))
    y = int(first[:4])
    return f"{y % 100:02d}{(y + 1) % 100:02d}"
