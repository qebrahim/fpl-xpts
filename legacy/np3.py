import json, ssl, sys, time, math, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

out_dir = Path(sys.argv[1])
out_dir.mkdir(parents=True, exist_ok=True)
FIRST_GW, LAST_GW = 11, 18
K_TEAM, PRIOR_MIN, PRIOR_APPS = 3, 270, 3
HALF_LIFE = 3.0
TARGET = "Mbeumo"

ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
UA = {"User-Agent": "Mozilla/5.0"}
base = "https://fantasy.premierleague.com/api/"


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), context=ctx, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def hist(pid):
    h = get(base + f"element-summary/{pid}/")["history"]
    ok = lambda r: bool((fxd.get(r["fixture"]) or {}).get("finished") or (fxd.get(r["fixture"]) or {}).get("finished_provisional"))
    return pid, [r for r in h if ok(r)]


boot = get(base + "bootstrap-static/")
fixtures = get(base + "fixtures/")
teams = {t["id"]: t["short_name"] for t in boot["teams"]}
tid = {v: k for k, v in teams.items()}
els = {e["id"]: e for e in boot["elements"]}
fxd = {f["id"]: f for f in fixtures}

# ---- team xG per fixture from goalkeeper xGC ----
gks = [e["id"] for e in els.values() if e["element_type"] == 1 and e["minutes"] > 0]
with ThreadPoolExecutor(6) as ex:
    gk_hist = dict(ex.map(hist, gks))
xga = {}
for pid, rows in gk_hist.items():
    t = els[pid]["team"]
    for r in rows:
        if r["minutes"] > 0:
            xga[(r["fixture"], t)] = xga.get((r["fixture"], t), 0.0) + float(r["expected_goals_conceded"])
fin = []
for f in sorted(fixtures, key=lambda f: (f.get("event") or 99, f["id"])):
    if f.get("finished") and (f["id"], f["team_h"]) in xga and (f["id"], f["team_a"]) in xga:
        fin.append({"fid": f["id"], "ev": f["event"], "h": f["team_h"], "a": f["team_a"],
                    "xg_h": xga[(f["id"], f["team_a"])], "xg_a": xga[(f["id"], f["team_h"])],
                    "sh": f["team_h_score"], "sa": f["team_a_score"]})
lg = {"h": sum(x["xg_h"] for x in fin) / len(fin), "a": sum(x["xg_a"] for x in fin) / len(fin)}
opp_of = lambda v: "a" if v == "h" else "h"

team_log = {}  # chronological per team: (ev, opp, v, xg_for, xg_against, gf, ga)
for x in fin:
    team_log.setdefault(x["h"], []).append((x["ev"], x["a"], "h", x["xg_h"], x["xg_a"], x["sh"], x["sa"]))
    team_log.setdefault(x["a"], []).append((x["ev"], x["h"], "a", x["xg_a"], x["xg_h"], x["sa"], x["sh"]))


def ratings(hl):
    att, dfn = {}, {}
    for t in teams:
        lt = team_log.get(t, [])
        n = len(lt)
        if n == 0:
            att[t] = dfn[t] = 1.0
            continue
        ws = [1.0 if hl is None else 0.5 ** ((n - 1 - i) / hl) for i in range(n)]
        sw = sum(ws)
        f_ = sum(w * (r[3] / lg[r[2]]) for w, r in zip(ws, lt)) / sw
        a_ = sum(w * (r[4] / lg[opp_of(r[2])]) for w, r in zip(ws, lt)) / sw
        att[t] = (f_ * n + K_TEAM) / (n + K_TEAM)
        dfn[t] = (a_ * n + K_TEAM) / (n + K_TEAM)
    # past-opponent norms always use the season-average (unweighted) ratings, matching how player rates were earned
    return att, dfn


att0, dfn0 = ratings(None)
pn_att = {t: sum(lg[r[2]] * dfn0[r[1]] for r in team_log[t]) / len(team_log[t]) for t in team_log}
pn_opp = {t: sum(lg[opp_of(r[2])] * att0[r[1]] for r in team_log[t]) / len(team_log[t]) for t in team_log}

# ---- match logs for the user's three claims ----
tm = {t: [k for k, v in els.items() if False] for t in []}
print("TEAM MATCH LOGS (round, opp, venue, xG for, xG against, score)  | league avg xG: home %.2f away %.2f" % (lg["h"], lg["a"]))
for name in ("CHE", "LIV", "MUN"):
    t = tid[name]
    print(f" {name}:")
    for ev, o, v, xf, xg_, gf, ga in team_log[t]:
        print(f"   GW{ev} {teams[o]}({v.upper()})  xG {xf:.2f} - {xg_:.2f}  score {gf}-{ga}")
    last3 = team_log[t][-3:]
    print(f"   season xGC/gm {sum(r[4] for r in team_log[t]) / len(team_log[t]):.2f} | last 3 xGC/gm {sum(r[4] for r in last3) / 3:.2f} | last 3 xG for/gm {sum(r[3] for r in last3) / 3:.2f}")
for label, (a_, d_) in (("season-avg", (att0, dfn0)), ("recency(hl=3)", ratings(HALF_LIFE))):
    print(f" ratings [{label}]  CHE att {a_[tid['CHE']]:.2f} def {d_[tid['CHE']]:.2f} | LIV att {a_[tid['LIV']]:.2f} def {d_[tid['LIV']]:.2f} | BOU def {d_[tid['BOU']]:.2f} | AVL def {d_[tid['AVL']]:.2f} | BRE def {d_[tid['BRE']]:.2f}")

# ---- player rates ----
import unicodedata
norm = lambda x: "".join(c for c in unicodedata.normalize("NFKD", x.lower()) if not unicodedata.combining(c))
SQ = [("Raya", "ARS", 1), ("Palmer", "IPS", 1), ("Hall", "NEW", 2), ("Calafiori", "ARS", 2), ("Muharemovic", "LEE", 2),
      ("De Cuyper", "BHA", 2), ("Thomas", "COV", 2), ("Tavernier", "BOU", 3), ("Schade", "BRE", 3), ("Rogers", "CHE", 3),
      ("Barnes", "NEW", 3), ("Mbeumo", "MUN", 3), ("Haaland", "MCI", 4), ("Gonzalo", "FUL", 4), ("Jackson", "AVL", 4),
      ("Barry", "EVE", 4), ("Isak", "LIV", 4), ("Evanilson", "BOU", 4), ("Rudoni", "COV", 3), ("Le Fee", "SUN", 3), ("Iwobi", "FUL", 3),
      ("Manzambi", "AVL", 3), ("McGinn", "AVL", 3), ("Rice", "ARS", 3), ("Van Hecke", "TOT", 2), ("Konsa", "ARS", 2), ("Silva", "BOU", 2),
      ("Hill", "BOU", 2), ("Gabriel", "ARS", 2), ("Trafford", "LEE", 1), ("Alysson", "AVL", 3)]
sq = {}
for key, tm_, pos_ in SQ:
    m = [e for e in els.values() if teams[e["team"]] == tm_ and e["element_type"] == pos_ and (norm(key) in norm(e["web_name"]) or norm(key) in norm(e["second_name"]))]
    assert len(m) == 1, (key, [(e["web_name"], e["second_name"]) for e in m])
    sq[m[0]["id"]] = key
cand = [e for e in els.values() if e["minutes"] >= PRIOR_MIN or e["id"] in sq]
with ThreadPoolExecutor(6) as ex:
    p_hist = dict(ex.map(hist, [e["id"] for e in cand]))
GP = {1: 10, 2: 6, 3: 5, 4: 4}
CSP = {1: 4, 2: 4, 3: 1, 4: 0}
TH = {2: 10, 3: 12, 4: 12}
posgrp = lambda p: p if p < 3 else 3
mb = [e for e in cand if e["web_name"] == "Mbeumo"][0]["id"]

print(f"\n{TARGET.upper()} MATCH LOG (round, opp, venue, min, xG, xA, xGI, pts, defcon)")
for r in p_hist[mb]:
    print(f"   GW{r['round']} {teams[r['opponent_team']]}({'H' if r['was_home'] else 'A'})  {r['minutes']}'  xG {float(r['expected_goals']):.2f} xA {float(r['expected_assists']):.2f} xGI {float(r['expected_goal_involvements']):.2f}  {r['total_points']} pts  dc {r['defensive_contribution']}")
tot = lambda rows, k: sum(float(r[k]) for r in rows)
allr = p_hist[mb]
exr = [r for r in allr if teams[r["opponent_team"]] != "IPS"]
print(f"   xGI/90 all: {tot(allr, 'expected_goal_involvements') / sum(r['minutes'] for r in allr) * 90:.2f} | excl. Ipswich: {tot(exr, 'expected_goal_involvements') / sum(r['minutes'] for r in exr) * 90:.2f}")


FORM = None
BONUS_PRIOR = None
def weigh(rows):
    if FORM is None:
        return rows
    kind, n = FORM
    if kind == "last":
        return rows[-n:]
    N = len(rows)
    out = []
    for i, r in enumerate(rows):
        w = 0.5 ** ((N - 1 - i) / n)
        q = dict(r)
        q["minutes"] = r["minutes"] * w
        for k in ("expected_goals", "expected_assists"):
            q[k] = float(r[k]) * w
        for k in ("bonus", "saves", "yellow_cards"):
            q[k] = r[k] * w
        out.append(q)
    return out

def build_players(excl_opp=None, only_pid=None):
    pool, hit_rows = {}, {1: [], 2: [], 3: []}
    for pos in (1, 2, 3, 4):
        es = [e for e in cand if e["element_type"] == pos]
        m = sum(e["minutes"] for e in es)
        pool[pos] = {k: sum(float(r[col]) for e in es for r in p_hist[e["id"]]) / m for k, col in (("xg", "expected_goals"), ("xa", "expected_assists"), ("bon", "bonus"), ("sav", "saves"))}
    for e in cand:
        pos = e["element_type"]
        for r in p_hist[e["id"]]:
            if r["minutes"] >= 60:
                hit_rows[posgrp(pos)].append(1 if r["defensive_contribution"] >= TH.get(pos, 99) else 0)
    pool_hit = {g: (sum(v) / len(v) if v else 0) for g, v in hit_rows.items()}
    players = {}
    for e in cand:
        pid, pos, t = e["id"], e["element_type"], e["team"]
        hfull = p_hist[pid]
        hr = hfull
        if excl_opp and (only_pid is None or pid == only_pid):
            hr = [r for r in hfull if teams[r["opponent_team"]] != excl_opp]
        hrw = weigh(hr)
        mins = sum(r["minutes"] for r in hrw)
        sh = lambda stat, pr: (stat + pr * PRIOR_MIN) / (mins + PRIOR_MIN) * 90
        hrs = [1 if r["defensive_contribution"] >= TH.get(pos, 99) else 0 for r in hr if r["minutes"] >= 60]
        hit = 0.0 if pos == 1 else (sum(hrs) + pool_hit[posgrp(pos)] * PRIOR_APPS) / (len(hrs) + PRIOR_APPS)
        last = hfull[-5:]
        players[pid] = {
            "pos": pos, "team": t, "name": e["web_name"], "price": e["now_cost"] / 10, "own": float(e["selected_by_percent"]),
            "xg90": 0.0 if pos == 1 else sh(tot(hrw, "expected_goals"), pool[pos]["xg"]),
            "xa90": 0.0 if pos == 1 else sh(tot(hrw, "expected_assists"), pool[pos]["xa"]),
            "bon90": (sum(r["bonus"] for r in hrw) + pool[pos]["bon"] * (BONUS_PRIOR or PRIOR_MIN)) / (mins + (BONUS_PRIOR or PRIOR_MIN)) * 90,
            "sav90": sh(sum(r["saves"] for r in hrw), pool[pos]["sav"]) if pos == 1 else 0.0,
            "yc90": sum(r["yellow_cards"] for r in hrw) / max(mins, 1) * 90, "hit": hit,
            "mf": sum(r["minutes"] for r in last) / len(last) / 90,
            "app": sum((2 if r["minutes"] >= 60 else 1 if r["minutes"] > 0 else 0) for r in last) / len(last),
            "p60": sum(1 for r in last if r["minutes"] >= 60) / len(last),
            "status": e["status"], "chance": e["chance_of_playing_next_round"],
        }
    return players


def pf(lam):
    s, p = 0.0, math.exp(-lam)
    for k in range(15):
        s += (k // 2) * p
        p *= lam / (k + 1)
    return s


def project(p, v, O, att, dfn):
    T, pos, mf, app, p60 = p["team"], p["pos"], p["mf"], p["app"], p["p60"]
    att_m = lg[v] * dfn[O] / pn_att[T]
    opp_xg = lg[opp_of(v)] * att[O] * dfn[T]
    opp_m = lg[opp_of(v)] * att[O] / pn_opp[T]
    return (app + p["xg90"] * mf * att_m * GP[pos] + p["xa90"] * mf * att_m * 3 + math.exp(-opp_xg) * CSP[pos] * p60
            - (pf(opp_xg * mf) if pos in (1, 2) else 0) + 2 * p["hit"] * p60 + p["bon90"] * mf
            + (p["sav90"] * mf * opp_m / 3 if pos == 1 else 0) - p["yc90"] * mf)


sched = {}
for f in fixtures:
    ev = f.get("event")
    if ev and FIRST_GW <= ev <= LAST_GW and not f.get("finished"):
        sched.setdefault(f["team_h"], []).append((ev, "h", f["team_a"]))
        sched.setdefault(f["team_a"], []).append((ev, "a", f["team_h"]))


def run(players, att, dfn):
    rows = []
    for pid, p in players.items():
        if p["status"] in ("u", "s", "n") or p["chance"] == 0:
            continue
        ch = (p["chance"] if p["chance"] is not None else 100) / 100
        tot_, det = 0.0, []
        for ev, v, O in sorted(sched.get(p["team"], [])):
            x = project(p, v, O, att, dfn) * (ch if ev == FIRST_GW else (1.0 if ch >= 0.5 else 0.5))
            tot_ += x
            det.append((ev, f"{teams[O]}({v.upper()})", round(x, 1)))
        rows.append({"id": pid, "name": p["name"], "team": teams[p["team"]], "price": p["price"], "own": p["own"], "xpts": round(tot_, 1), "det": det})
    rows.sort(key=lambda r: -r["xpts"])
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows




att_r, dfn_r = ratings(HALF_LIFE)
print("\nNP3_START")
import copy
ids = {k: i for i, k in sq.items()}
PEN_XG, PEN_RATE_XG = 0.76, 0.10
# Actual penalty GOALS this season (one-versus-one.com PL penalty-goals ranking, full list of players with >=1; all others 0)
PENGOALS = [("Le Fée","SUN",3),("Groß","BHA",2),("Fernandes","MUN",2),("Szoboszlai","LIV",1),("McGinn","AVL",1),("Nketiah","CRY",1),
            ("McBurnie","HUL",1),("Gibbs-White","NFO",1),("Saka","ARS",1),("Clarke","IPS",1),("Rudoni","COV",1),("Palmer","CHE",1),("Flemming","IPS",1)]
pg = {}
for key, tm_, n in PENGOALS:
    m = [e for e in els.values() if teams[e["team"]] == tm_ and norm(key) in norm(e["web_name"])]
    assert len(m) == 1, (key, [e["web_name"] for e in m])
    pg[m[0]["id"]] = n
taken = {}
for e in els.values():
    n = pg.get(e["id"], 0) + e["penalties_missed"]
    if n: taken[e["id"]] = n
orig_hist = p_hist
adj_hist = copy.deepcopy(p_hist)
print("PENALTIES TAKEN THIS SEASON = penalty goals (source) + FPL penalties_missed")
for pid, n in sorted(taken.items(), key=lambda kv: -kv[1]):
    e = els[pid]
    print(f"   {e['web_name']:<14}{teams[e['team']]}  taken {n}  (scored {pg.get(pid,0)}, missed {e['penalties_missed']})  FPL ord {e['penalties_order']}  min {e['minutes']}")
for pid, n in taken.items():
    if pid not in adj_hist: continue
    sc, ms = pg.get(pid, 0), els[pid]["penalties_missed"]
    rows_ = adj_hist[pid]
    used = set()
    for r in sorted([r for r in rows_ if r["goals_scored"] >= 1], key=lambda r: -float(r["expected_goals"]))[:sc]:
        r["expected_goals"] = str(max(0.0, float(r["expected_goals"]) - PEN_XG)); r["goals_scored"] -= 1; used.add(r["round"])
    for r in sorted([r for r in rows_ if r["round"] not in used and r["goals_scored"] == 0], key=lambda r: -float(r["expected_goals"]))[:ms]:
        r["expected_goals"] = str(max(0.0, float(r["expected_goals"]) - PEN_XG))
# primary taker per club: most pens taken; none -> FPL order-1 player (Arsenal split Saka/Ødegaard as Saka is injured)
primary = {}
for tm_ in set(e["team"] for e in els.values()):
    c = [e for e in els.values() if e["team"] == tm_ and e["element_type"] != 1 and taken.get(e["id"], 0) > 0]
    if c:
        primary[tm_] = max(c, key=lambda e: (taken[e["id"]], -e["penalties_order"] if e["penalties_order"] else -9))["id"]
    else:
        o1 = [e for e in els.values() if e["team"] == tm_ and e["penalties_order"] == 1 and e["element_type"] != 1]
        if o1: primary[tm_] = o1[0]["id"]
print("\nPRIMARY PEN TAKER PER CLUB used for future pens (0.10 xG/game):")
for tm_, pid in sorted(primary.items(), key=lambda kv: teams[kv[0]]):
    e = els[pid]
    print(f"   {teams[tm_]:<4} {e['web_name']:<14} taken {taken.get(pid,0)}  ord{e['penalties_order']}  £{e['now_cost']/10:.1f}m")


att_r, dfn_r = ratings(HALF_LIFE)
def fin_cut(pid, H):
    h = H[pid]; r = sum(x["goals_scored"] for x in h) - sum(float(x["expected_goals"]) for x in h)
    return -0.147 if r <= -1.5 else (-0.065 if r >= 1.5 else 0.0)
def series(form, H, add_pen):
    global FORM, p_hist
    FORM = form; p_hist = H
    pl = build_players()
    pl[ids["Calafiori"]].update(mf=0.95, app=1.9, p60=0.9)
    pl[ids["Isak"]].update(mf=0.88, app=1.85, p60=0.85)
    for pid in add_pen:
        if pid in pl: pl[pid]["xg90"] += PEN_RATE_XG
    rows = {r["id"]: r for r in run(pl, att_r, dfn_r)}
    out = {}
    for pid, r in rows.items():
        p = pl[pid]; cut = fin_cut(pid, H)
        fx = {ev: (v, O) for ev, v, O in sched.get(p["team"], [])}
        d = {}
        for ev, _, x in r["det"]:
            v, O = fx[ev]
            d[ev] = x + 4 * cut * p["xg90"] * p["mf"] * (lg[v] * dfn_r[O] / pn_att[p["team"]])
        out[pid] = d
    return out, pl
S = {}
for label, form in (("hl4", ("hl", 4)), ("season", None)):
    old, _ = series(form, orig_hist, [])
    new, pl = series(form, adj_hist, list(primary.values()))
    S[label] = (old, new, pl)
pl = S["hl4"][2]
f5 = lambda D, pid: sum(v for ev, v in D[pid].items() if ev <= 15)
print("\nGW11-15 projection: as-is -> all-pens-regressed (hl4 / season) for pen takers + your squad")
chk = list(primary.values()) + [ids[n] for n in ["Raya","Palmer","Van Hecke","Calafiori","De Cuyper","Muharemovic","Thomas","Tavernier","Rogers","Schade","Mbeumo","Barnes","Jackson","Haaland","Isak"]]
seen = set()
for pid in chk:
    if pid in seen or pid not in S["hl4"][0]: continue
    seen.add(pid)
    if els[pid]["element_type"] == 1: continue
    o4, n4, os_, ns = f5(S["hl4"][0], pid), f5(S["hl4"][1], pid), f5(S["season"][0], pid), f5(S["season"][1], pid)
    if pid in primary.values() or abs(n4 - o4) > 0.05:
        print(f"   {els[pid]['web_name']:<14}{teams[els[pid]['team']]} £{els[pid]['now_cost']/10:.1f}m {o4:5.1f}/{os_:5.1f} -> {n4:5.1f}/{ns:5.1f}")
b, bs = S["hl4"][1], S["season"][1]
for posn, pos in (("MIDS", 3), ("FWDS", 4), ("DEFS", 2)):
    pool_ = [pid for pid in b if els[pid]["element_type"] == pos and els[pid]["minutes"] >= 270 and pl[pid]["mf"] >= 0.7 and els[pid]["chance_of_playing_next_round"] in (None, 75, 100)]
    top_ = sorted(pool_, key=lambda i: -(f5(b, i) + f5(bs, i)))[:10]
    print(f"\nTOP 10 {posn} GW11-15, all pens regressed (hl4/season)")
    for i in top_:
        print(f"   {els[i]['web_name']:<14}{teams[els[i]['team']]} £{els[i]['now_cost']/10:.1f}m  {f5(b, i):5.1f}/{f5(bs, i):5.1f}")
def best_xi(vals):
    D = sorted([v for p, v in vals if els[p]["element_type"] == 2], reverse=True)
    M = sorted([v for p, v in vals if els[p]["element_type"] == 3], reverse=True)
    F = sorted([v for p, v in vals if els[p]["element_type"] == 4], reverse=True)
    G = max(v for p, v in vals if els[p]["element_type"] == 1)
    top_ = 0
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3 and d <= len(D) and m <= len(M) and f <= len(F):
                top_ = max(top_, sum(D[:d]) + sum(M[:m]) + sum(F[:f]))
    return G + top_
squad0 = [ids[n] for n in ["Raya","Palmer","Van Hecke","Calafiori","De Cuyper","Muharemovic","Thomas","Tavernier","Rogers","Schade","Mbeumo","Barnes","Jackson","Haaland","Isak"]]
price = {pid: els[pid]["now_cost"] / 10 for pid in els}
pool = [pid for pid in b if els[pid]["minutes"] >= 270 and pl[pid]["mf"] >= 0.7 and els[pid]["chance_of_playing_next_round"] in (None, 75, 100) and pid not in squad0]
def tot(sq_, Sd, lo, hi): return sum(best_xi([(p, Sd.get(p, {}).get(ev, 0.0)) for p in sq_]) for ev in range(lo, hi + 1))
base = (tot(squad0, b, 11, 15), tot(squad0, bs, 11, 15), tot(squad0, b, 11, 18), tot(squad0, bs, 11, 18))
counts = {}
for p in squad0: counts[els[p]["team"]] = counts.get(els[p]["team"], 0) + 1
sing = []
for o in squad0:
    for i_ in pool:
        if els[i_]["element_type"] != els[o]["element_type"]: continue
        if els[i_]["team"] != els[o]["team"] and counts.get(els[i_]["team"], 0) >= 3: continue
        c = price[i_] - price[o]
        if c > 1.5: continue
        sq2 = [i_ if p == o else p for p in squad0]
        sing.append((tot(sq2, b, 11, 15) - base[0], tot(sq2, bs, 11, 15) - base[1], tot(sq2, b, 11, 18) - base[2], tot(sq2, bs, 11, 18) - base[3], o, i_, c))
sing.sort(key=lambda r: -(r[0] + r[1] + r[2] + r[3]))
print("\nBEST SINGLE MOVES COSTING <= +£0.5m: 5GW hl4/season | 8GW hl4/season | cost")
for r in [r for r in sing if r[6] <= 0.5][:14]:
    print(f"   {els[r[4]]['web_name']:<12}-> {els[r[5]]['web_name']:<12} 5GW {r[0]:+5.1f}/{r[1]:+5.1f} | 8GW {r[2]:+5.1f}/{r[3]:+5.1f} | £{r[6]:+.1f}m")
print("\nBEST SINGLE MOVES COSTING +£0.5m to +£1.5m")
for r in [r for r in sing if r[6] > 0.5][:8]:
    print(f"   {els[r[4]]['web_name']:<12}-> {els[r[5]]['web_name']:<12} 5GW {r[0]:+5.1f}/{r[1]:+5.1f} | 8GW {r[2]:+5.1f}/{r[3]:+5.1f} | £{r[6]:+.1f}m")
