import json, ssl, sys, time, math, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np

ctx = ssl.create_default_context(cafile="/root/.ccr/ca-bundle.crt")
UA = {"User-Agent": "Mozilla/5.0"}
base = "https://fantasy.premierleague.com/api/"
K_TEAM, PRIOR_MIN, PRIOR_APPS, TEAM_HL = 3, 270, 3, 3.0
GP = {1: 10, 2: 6, 3: 5, 4: 4}
CSP = {1: 4, 2: 4, 3: 1, 4: 0}
TH = {2: 10, 3: 12, 4: 12}
posgrp = lambda p: p if p < 3 else 3
opp_of = lambda v: "a" if v == "h" else "h"
LAST_GW_DATA = 10


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), context=ctx, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


boot = get(base + "bootstrap-static/")
fixtures = get(base + "fixtures/")
teams = {t["id"]: t["short_name"] for t in boot["teams"]}
els = {e["id"]: e for e in boot["elements"]}
fxd = {f["id"]: f for f in fixtures}
done = lambda fid: bool((fxd.get(fid) or {}).get("finished") or (fxd.get(fid) or {}).get("finished_provisional"))


def summ(pid):
    d = get(base + f"element-summary/{pid}/")
    return pid, ([r for r in d["history"] if done(r["fixture"]) and r["round"] <= LAST_GW_DATA], d["history_past"])


gks = [e["id"] for e in els.values() if e["element_type"] == 1 and e["minutes"] > 0]
cand = [e["id"] for e in els.values() if e["minutes"] >= 90]
allids = sorted(set(gks) | set(cand))
with ThreadPoolExecutor(6) as ex:
    S = dict(ex.map(summ, allids))
p_hist = {p: S[p][0] for p in cand}
p_past = {p: S[p][1] for p in cand}
print("fetched", len(allids), "players")

# team xG per fixture (from keeper xGC)
xga = {}
for pid in gks:
    t = els[pid]["team"]
    for r in S[pid][0]:
        if r["minutes"] > 0:
            xga[(r["fixture"], t)] = xga.get((r["fixture"], t), 0.0) + float(r["expected_goals_conceded"])
fin = []
for f in sorted(fixtures, key=lambda f: (f.get("event") or 99, f["id"])):
    if f.get("finished") and f["event"] and f["event"] <= LAST_GW_DATA and (f["id"], f["team_h"]) in xga and (f["id"], f["team_a"]) in xga:
        fin.append({"ev": f["event"], "h": f["team_h"], "a": f["team_a"], "xg_h": xga[(f["id"], f["team_a"])], "xg_a": xga[(f["id"], f["team_h"])]})


def team_state(cut, hl=TEAM_HL):
    fc = [x for x in fin if x["ev"] <= cut]
    lg = {"h": sum(x["xg_h"] for x in fc) / len(fc), "a": sum(x["xg_a"] for x in fc) / len(fc)}
    tl = {}
    for x in fc:
        tl.setdefault(x["h"], []).append((x["ev"], x["a"], "h", x["xg_h"], x["xg_a"]))
        tl.setdefault(x["a"], []).append((x["ev"], x["h"], "a", x["xg_a"], x["xg_h"]))

    def ratings(h):
        att, dfn = {}, {}
        for t in teams:
            lt = tl.get(t, [])
            n = len(lt)
            if n == 0:
                att[t] = dfn[t] = 1.0
                continue
            ws = [1.0 if h is None else 0.5 ** ((n - 1 - i) / h) for i in range(n)]
            sw = sum(ws)
            f_ = sum(w * (r[3] / lg[r[2]]) for w, r in zip(ws, lt)) / sw
            a_ = sum(w * (r[4] / lg[opp_of(r[2])]) for w, r in zip(ws, lt)) / sw
            att[t] = (f_ * n + K_TEAM) / (n + K_TEAM)
            dfn[t] = (a_ * n + K_TEAM) / (n + K_TEAM)
        return att, dfn
    att0, dfn0 = ratings(None)
    pn_att = {t: sum(lg[r[2]] * dfn0[r[1]] for r in tl[t]) / len(tl[t]) for t in tl}
    pn_opp = {t: sum(lg[opp_of(r[2])] * att0[r[1]] for r in tl[t]) / len(tl[t]) for t in tl}
    att, dfn = ratings(hl)
    return dict(lg=lg, att=att, dfn=dfn, pn_att=pn_att, pn_opp=pn_opp)


def last_season_prior(pid):
    """(xg per min, xa per min, weight in minutes) from the last two seasons, last season counted fully, the one before at half weight."""
    wsum = xg = xa = 0.0
    for r in p_past[pid]:
        w = {"2025/26": 1.0, "2024/25": 0.5}.get(r["season_name"])
        if not w or r["minutes"] < 450:
            continue
        wsum += w * r["minutes"]
        xg += w * float(r["expected_goals"])
        xa += w * float(r["expected_assists"])
    if wsum == 0:
        return 0.0, 0.0, 0.0
    return xg / wsum, xa / wsum, wsum


PRIOR = {p: last_season_prior(p) for p in cand}


def weigh(rows, form):
    if form is None:
        return rows
    n = form
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


def build(cut, form, lam, cap=2500.0, pm=270, minlive=90):
    H = {p: [r for r in p_hist[p] if r["round"] <= cut] for p in cand}
    live = [p for p in cand if sum(r["minutes"] for r in H[p]) >= minlive]
    pool, hit_rows = {}, {1: [], 2: [], 3: []}
    for pos in (1, 2, 3, 4):
        es = [p for p in live if els[p]["element_type"] == pos]
        m = sum(r["minutes"] for p in es for r in H[p])
        pool[pos] = {k: sum(float(r[col]) for p in es for r in H[p]) / m for k, col in (("xg", "expected_goals"), ("xa", "expected_assists"), ("bon", "bonus"), ("sav", "saves"))}
    for p in live:
        pos = els[p]["element_type"]
        for r in H[p]:
            if r["minutes"] >= 60:
                hit_rows[posgrp(pos)].append(1 if r["defensive_contribution"] >= TH.get(pos, 99) else 0)
    pool_hit = {g: (sum(v) / len(v) if v else 0) for g, v in hit_rows.items()}
    P = {}
    for pid in live:
        pos, t = els[pid]["element_type"], els[pid]["team"]
        hr = H[pid]
        hrw = weigh(hr, form)
        mins = sum(r["minutes"] for r in hrw)
        lxg, lxa, lw = PRIOR[pid]
        wl = lam * min(lw, cap)

        def sh(stat, prior_pm, last_pm):
            return (stat + prior_pm * pm + last_pm * wl) / (mins + pm + wl) * 90
        hrs = [1 if r["defensive_contribution"] >= TH.get(pos, 99) else 0 for r in hr if r["minutes"] >= 60]
        hit = 0.0 if pos == 1 else (sum(hrs) + pool_hit[posgrp(pos)] * PRIOR_APPS) / (len(hrs) + PRIOR_APPS)
        last = hr[-5:]
        P[pid] = {
            "pos": pos, "team": t,
            "xg90": 0.0 if pos == 1 else sh(sum(float(r["expected_goals"]) for r in hrw), pool[pos]["xg"], lxg),
            "xa90": 0.0 if pos == 1 else sh(sum(float(r["expected_assists"]) for r in hrw), pool[pos]["xa"], lxa),
            "bon90": (sum(r["bonus"] for r in hrw) + pool[pos]["bon"] * pm) / (mins + pm) * 90,
            "sav90": (sum(r["saves"] for r in hrw) + pool[pos]["sav"] * pm) / (mins + pm) * 90 if pos == 1 else 0.0,
            "yc90": sum(r["yellow_cards"] for r in hrw) / max(mins, 1) * 90, "hit": hit,
            "mf": sum(r["minutes"] for r in last) / len(last) / 90,
            "app": sum((2 if r["minutes"] >= 60 else 1 if r["minutes"] > 0 else 0) for r in last) / len(last),
            "p60": sum(1 for r in last if r["minutes"] >= 60) / len(last),
        }
    return P


def pf(lam):
    s, p = 0.0, math.exp(-lam)
    for k in range(15):
        s += (k // 2) * p
        p *= lam / (k + 1)
    return s


def comps(p, v, O, st):
    lg, att, dfn = st["lg"], st["att"], st["dfn"]
    T, pos, mf = p["team"], p["pos"], p["mf"]
    att_m = lg[v] * dfn[O] / st["pn_att"][T]
    opp_xg = lg[opp_of(v)] * att[O] * dfn[T]
    opp_m = lg[opp_of(v)] * att[O] / st["pn_opp"][T]
    return {
        "app": p["app"], "goal": p["xg90"] * mf * att_m * GP[pos], "assist": p["xa90"] * mf * att_m * 3,
        "cs": math.exp(-opp_xg) * CSP[pos] * p["p60"], "gc": -(pf(opp_xg * mf) if pos in (1, 2) else 0),
        "dc": 2 * p["hit"] * p["p60"], "bonus": p["bon90"] * mf,
        "sav": (p["sav90"] * mf * opp_m / 3 if pos == 1 else 0), "yc": -p["yc90"] * mf,
    }


def actual_comps(r, pos):
    m = r["minutes"]
    return {
        "app": 2 if m >= 60 else 1 if m > 0 else 0, "goal": r["goals_scored"] * GP[pos], "assist": r["assists"] * 3,
        "cs": (r["clean_sheets"] * CSP[pos] if m >= 60 else 0), "gc": -(r["goals_conceded"] // 2) if pos in (1, 2) else 0,
        "dc": 2 if pos != 1 and r["defensive_contribution"] >= TH[pos] else 0, "bonus": r["bonus"],
        "sav": (r["saves"] // 3 if pos == 1 else 0), "yc": -r["yellow_cards"],
    }




import copy, unicodedata, os
norm = lambda x: "".join(c for c in unicodedata.normalize("NFKD", x.lower()) if not unicodedata.combining(c))
CAL = {tuple([int(k.split("|")[0]), k.split("|")[1]]): v for k, v in json.load(open("calib.json"))["cal"].items()}
COMPS = ["app", "goal", "assist", "cs", "gc", "dc", "bonus", "sav", "yc"]
FIRST_GW, LAST_GW = 11, 18
print("LIVE6_START")

# ---- real penalty counts (penalty goals from the PL ranking + FPL penalties_missed); strip them from history ----
PEN_XG, PEN_RATE_XG = 0.76, 0.10
PENGOALS = [("Le Fée","SUN",3),("Groß","BHA",2),("Fernandes","MUN",2),("Szoboszlai","LIV",1),("McGinn","AVL",1),("Nketiah","CRY",1),
            ("McBurnie","HUL",1),("Gibbs-White","NFO",1),("Saka","ARS",1),("Clarke","IPS",1),("Rudoni","COV",1),("Palmer","CHE",1),("Flemming","IPS",1)]
pg = {}
for key, tm_, n in PENGOALS:
    m = [e for e in els.values() if teams[e["team"]] == tm_ and norm(key) in norm(e["web_name"])]
    assert len(m) == 1, (key, [e["web_name"] for e in m]); pg[m[0]["id"]] = n
taken = {e["id"]: pg.get(e["id"], 0) + e["penalties_missed"] for e in els.values() if pg.get(e["id"], 0) + e["penalties_missed"] > 0}
adj = copy.deepcopy(p_hist)
for pid, n in taken.items():
    if pid not in adj: continue
    sc, ms = pg.get(pid, 0), els[pid]["penalties_missed"]; used = set()
    for r in sorted([r for r in adj[pid] if r["goals_scored"] >= 1], key=lambda r: -float(r["expected_goals"]))[:sc]:
        r["expected_goals"] = str(max(0.0, float(r["expected_goals"]) - PEN_XG)); r["goals_scored"] -= 1; used.add(r["round"])
    for r in sorted([r for r in adj[pid] if r["round"] not in used and r["goals_scored"] == 0], key=lambda r: -float(r["expected_goals"]))[:ms]:
        r["expected_goals"] = str(max(0.0, float(r["expected_goals"]) - PEN_XG))
primary = {}
for tm_ in set(e["team"] for e in els.values()):
    c = [e for e in els.values() if e["team"] == tm_ and e["element_type"] != 1 and taken.get(e["id"], 0) > 0]
    if c: primary[tm_] = max(c, key=lambda e: (taken[e["id"]], -(e["penalties_order"] or 9)))["id"]
    else:
        o1 = [e for e in els.values() if e["team"] == tm_ and e["penalties_order"] == 1 and e["element_type"] != 1]
        if o1: primary[tm_] = o1[0]["id"]

# ---- players: hl4 form, last-season prior 0.15 (prior_min 450), pens stripped; then pen share; overrides ----
p_hist = adj
P = build(10, 4, 0.15, pm=450, minlive=90)
for pid in primary.values():
    if pid in P: P[pid]["xg90"] += PEN_RATE_XG
ids = {}
SQN = [("Raya","ARS",1),("Palmer","IPS",1),("Van Hecke","TOT",2),("Calafiori","ARS",2),("De Cuyper","BHA",2),("Muharemovic","LEE",2),("Thomas","COV",2),
       ("Tavernier","BOU",3),("Rogers","CHE",3),("Schade","BRE",3),("Mbeumo","MUN",3),("Barnes","NEW",3),("Jackson","AVL",4),("Haaland","MCI",4),("Isak","LIV",4),("Rudoni","COV",3)]
for key, tm_, pos_ in SQN:
    m = [e for e in els.values() if teams[e["team"]] == tm_ and e["element_type"] == pos_ and (norm(key) in norm(e["web_name"]) or norm(key) in norm(e["second_name"]))]
    assert len(m) == 1, (key, [e["web_name"] for e in m]); ids[key] = m[0]["id"]
OVR = {"Calafiori": dict(mf=0.95, app=1.9, p60=0.9), "Thomas": dict(mf=0.94, app=1.9, p60=0.88), "Isak": dict(mf=0.88, app=1.85, p60=0.85)}
for n, d in OVR.items(): P[ids[n]].update(d)
FIT = {ids["Calafiori"], ids["Thomas"]}   # assumed fully fit

st = team_state(10)
sched = {}
for f in fixtures:
    ev = f.get("event")
    if ev and FIRST_GW <= ev <= LAST_GW and not f.get("finished"):
        sched.setdefault(f["team_h"], []).append((ev, "h", f["team_a"])); sched.setdefault(f["team_a"], []).append((ev, "a", f["team_h"]))
S = {}
for pid, p in P.items():
    e = els[pid]
    if e["status"] in ("u", "s", "n") or e["chance_of_playing_next_round"] == 0: continue
    ch = 1.0 if pid in FIT else (e["chance_of_playing_next_round"] if e["chance_of_playing_next_round"] is not None else 100) / 100
    d = {}
    for ev, v, O in sorted(sched.get(p["team"], [])):
        cm = comps(p, v, O, st)
        x = sum(cm[k] * CAL.get((p["pos"], k), 1.0) for k in COMPS)
        d[ev] = x * (ch if ev == FIRST_GW else (1.0 if ch >= 0.5 else 0.5))
    S[pid] = d
f5 = lambda pid: sum(v for ev, v in S[pid].items() if ev <= 15)
f8 = lambda pid: sum(S[pid].values())
print("calibration factors in use:", {f"{k[0]}|{k[1]}": round(v, 2) for k, v in CAL.items() if k[1] in ("goal", "cs", "gc", "app")})

for posn, pos in (("MIDS", 3), ("FWDS", 4), ("DEFS", 2), ("GKS", 1)):
    pool_ = [pid for pid in S if els[pid]["element_type"] == pos and els[pid]["minutes"] >= 270 and P[pid]["mf"] >= 0.7 and els[pid]["chance_of_playing_next_round"] in (None, 75, 100)]
    top_ = sorted(pool_, key=lambda i: -f5(i))[: (4 if pos == 1 else 10)]
    print(f"\nTOP {posn} GW11-15 (recalibrated model; GW11-18 in brackets), price")
    for i in top_: print(f"   {els[i]['web_name']:<14}{teams[els[i]['team']]} £{els[i]['now_cost']/10:.1f}m  {f5(i):5.1f}  [{f8(i):5.1f}]")
print("\nYOUR SQUAD (current, with Schade) GW11-15 [GW11-18], per GW:")
for n in ["Raya","Palmer","Van Hecke","Calafiori","De Cuyper","Muharemovic","Thomas","Tavernier","Rogers","Schade","Mbeumo","Barnes","Rudoni","Jackson","Haaland","Isak"]:
    i = ids[n]
    if i in S: print(f"   {els[i]['web_name']:<12}{teams[els[i]['team']]} £{els[i]['now_cost']/10:.1f}m {f5(i):5.1f} [{f8(i):5.1f}]  {[round(S[i].get(ev, 0), 1) for ev in range(11, 16)]}")

def best_xi(vals):
    D = sorted([v for p, v in vals if els[p]["element_type"] == 2], reverse=True); M = sorted([v for p, v in vals if els[p]["element_type"] == 3], reverse=True)
    F = sorted([v for p, v in vals if els[p]["element_type"] == 4], reverse=True); G = max(v for p, v in vals if els[p]["element_type"] == 1)
    top_ = 0
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if 1 <= f <= 3 and d <= len(D) and m <= len(M) and f <= len(F): top_ = max(top_, sum(D[:d]) + sum(M[:m]) + sum(F[:f]))
    return G + top_
sq0 = [ids[n] for n in ["Raya","Palmer","Van Hecke","Calafiori","De Cuyper","Muharemovic","Thomas","Tavernier","Rogers","Schade","Mbeumo","Barnes","Jackson","Haaland","Isak"]]
tot = lambda sq_, lo, hi: sum(best_xi([(p, S.get(p, {}).get(ev, 0.0)) for p in sq_]) for ev in range(lo, hi + 1))
b5, b8 = tot(sq0, 11, 15), tot(sq0, 11, 18)
price = lambda i: els[i]["now_cost"] / 10
cnt = {}
for p in sq0: cnt[els[p]["team"]] = cnt.get(els[p]["team"], 0) + 1
pool = [pid for pid in S if els[pid]["minutes"] >= 270 and P[pid]["mf"] >= 0.7 and els[pid]["chance_of_playing_next_round"] in (None, 75, 100) and pid not in sq0]
sing = []
for o in sq0:
    for i_ in pool:
        if els[i_]["element_type"] != els[o]["element_type"]: continue
        if els[i_]["team"] != els[o]["team"] and cnt.get(els[i_]["team"], 0) >= 3: continue
        c = price(i_) - price(o)
        if c > 1.5: continue
        sq2 = [i_ if p == o else p for p in sq0]
        sing.append((tot(sq2, 11, 15) - b5, tot(sq2, 11, 18) - b8, o, i_, c))
sing.sort(key=lambda r: -(r[0] + r[1]))
print("\nBEST SINGLE MOVES FROM YOUR CURRENT SQUAD, cost <= +£0.5m  (5GW | 8GW | cost)")
for r in [r for r in sing if r[4] <= 0.5][:14]: print(f"   {els[r[2]]['web_name']:<12}-> {els[r[3]]['web_name']:<12} {r[0]:+5.1f} | {r[1]:+5.1f} | £{r[4]:+.1f}m")
print("\nBEST SINGLE MOVES costing +£0.5m to +£1.5m")
for r in [r for r in sing if r[4] > 0.5][:8]: print(f"   {els[r[2]]['web_name']:<12}-> {els[r[3]]['web_name']:<12} {r[0]:+5.1f} | {r[1]:+5.1f} | £{r[4]:+.1f}m")

# lineups after Schade -> Rudoni
sq15 = [ids["Rudoni"] if p == ids["Schade"] else p for p in sq0]
val = lambda p, ev: S.get(p, {}).get(ev, 0.0)
print("\nXI WITH RUDONI IN FOR SCHADE:")
for ev in range(11, 16):
    G = max([p for p in sq15 if els[p]["element_type"] == 1], key=lambda p: val(p, ev))
    byp = {pos: sorted([p for p in sq15 if els[p]["element_type"] == pos], key=lambda p: -val(p, ev)) for pos in (2, 3, 4)}
    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if not (1 <= f <= 3): continue
            xi = byp[2][:d] + byp[3][:m] + byp[4][:f]; sc = sum(val(p, ev) for p in xi) + val(G, ev)
            if best is None or sc > best[0]: best = (sc, d, m, f, xi)
    sc, d, m, f, xi = best; cap = max(xi, key=lambda p: val(p, ev))
    bench = sorted([p for p in sq15 if p not in xi and els[p]["element_type"] != 1], key=lambda p: -val(p, ev))
    print(f"GW{ev} {d}-{m}-{f} total {sc:.1f} (C {els[cap]['web_name']} {val(cap, ev):.1f}): " + ", ".join(f"{els[p]['web_name']} {val(p, ev):.1f}" for p in sorted(xi, key=lambda p: (els[p]['element_type'], -val(p, ev)))) + " | bench: " + ", ".join(f"{els[p]['web_name']} {val(p, ev):.1f}" for p in bench))
print("LIVE6_DONE")
