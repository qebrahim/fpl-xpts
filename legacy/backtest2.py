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



CUTS = list(range(1, 10)); HORIZON = 5
STATES = {c: team_state(c) for c in CUTS}
COMPS = ["app", "goal", "assist", "cs", "gc", "dc", "bonus", "sav", "yc"]


def evaluate(form, lam, pm):
    rows = []
    for c in CUTS:
        P = build(c, form, lam, pm=pm)
        st = STATES[c]
        for pid, p in P.items():
            H = [r for r in p_hist[pid] if r["round"] <= c]
            gx = sum(r["goals_scored"] for r in H) - sum(float(r["expected_goals"]) for r in H)
            for r in p_hist[pid]:
                if c < r["round"] <= min(c + HORIZON, LAST_GW_DATA):
                    v = "h" if r["was_home"] else "a"
                    cm = comps(p, v, r["opponent_team"], st)
                    rows.append((pid, c, r["round"], p["pos"], sum(cm.values()), r["total_points"], cm, actual_comps(r, p["pos"]), gx))
    return rows


def rmse(rows, cal=None):
    pr = np.array([sum(x[6][k] * (cal.get((x[3], k), 1.0) if cal else 1.0) for k in COMPS) for x in rows]); ac = np.array([x[5] for x in rows])
    return math.sqrt(np.mean((pr - ac) ** 2)), np.mean(pr - ac), pr, ac


print("BACKTEST2_START")
print(f"cutoffs {CUTS[0]}-{CUTS[-1]}, predicting the next {HORIZON} rounds (up to GW{LAST_GW_DATA}), players with >=90 min at cutoff")
grid = [(f, lam, pmv) for f in (None, 4, 6) for lam in (0.0, 0.15, 0.3) for pmv in (180, 270, 450)]
res = {}
for f, lam, pmv in grid:
    rows = evaluate(f, lam, pmv)
    res[(f, lam, pmv)] = rows
    r, b_, _, _ = rmse(rows)
    print(f"   form={str(f):<5} prior_lambda={lam:<5} prior_min={pmv:<4} n={len(rows)} RMSE {r:.4f} bias {b_:+.3f}", flush=True)
ranked = sorted(res, key=lambda k: rmse(res[k])[0])
print("\nTOP 5 SETTINGS:")
for k in ranked[:5]:
    print("  ", k, round(rmse(res[k])[0], 4))
base_key = (None, 0.0, 270)
print("CURRENT (season-long, no prior, prior_min 270):", round(rmse(res[base_key])[0], 4), "| live default was hl4:", round(rmse(res[(4, 0.0, 270)])[0], 4))
best = ranked[0]
print("BEST:", best)

# RMSE by cutoff bucket for current vs best
for lab, cs in (("early cuts 1-3", (1, 2, 3)), ("mid cuts 4-6", (4, 5, 6)), ("late cuts 7-9", (7, 8, 9))):
    out = []
    for k in (base_key, (4, 0.0, 270), best):
        sub = [x for x in res[k] if x[1] in cs]
        out.append(f"{k}: {rmse(sub)[0]:.3f}")
    print(f"   {lab:<16}", " | ".join(out))

# paired bootstrap best vs current
def boot(a, b, B=400):
    da = {(x[0], x[1], x[2]): (x[4] - x[5]) ** 2 for x in res[a]}; db = {(x[0], x[1], x[2]): (x[4] - x[5]) ** 2 for x in res[b]}
    byp = {}
    for k in da:
        if k in db: byp.setdefault(k[0], []).append(da[k] - db[k])
    pl = sorted(byp); arr = {p: np.array(v) for p, v in byp.items()}
    rng = np.random.default_rng(3)
    base_ = np.mean(np.concatenate(list(arr.values())))
    return base_, np.std([np.mean(np.concatenate([arr[p] for p in rng.choice(pl, len(pl))])) for _ in range(B)])
d, se = boot(best, base_key)
print(f"paired sq-error diff best vs season-long/no-prior: {d:+.3f} +/- {se:.3f}")
d, se = boot(best, (4, 0.0, 270))
print(f"paired sq-error diff best vs hl4/no-prior:        {d:+.3f} +/- {se:.3f}")

# ---------- calibration (time split: fit on target rounds <=6, test on rounds >=7), best settings ----------
rows = res[best]
def fit_cal(rs, K=20.0):
    cal = {}
    for pos in (1, 2, 3, 4):
        sub = [x for x in rs if x[3] == pos]
        for k in COMPS:
            sp = sum(x[6][k] for x in sub); sa = sum(x[7][k] for x in sub)
            if abs(sp) < 1e-9: continue
            cal[(pos, k)] = (sa + K * (1 if sp > 0 else -1)) / (sp + K * (1 if sp > 0 else -1))
    return cal
train = [x for x in rows if x[2] <= 6]; test = [x for x in rows if x[2] >= 7]
cal_tr = fit_cal(train)
r0, b0_, p0, a0 = rmse(test); r1, b1_, p1, a1 = rmse(test, cal_tr)
print(f"\nTIME-SPLIT CHECK (fit on rounds<=6: n={len(train)}, test on rounds>=7: n={len(test)})")
print(f"   uncalibrated RMSE {r0:.4f} bias {b0_:+.3f}  ->  calibrated RMSE {r1:.4f} bias {b1_:+.3f}")
# also check the extra top-end shrink slope fitted on train
ptr = np.array([sum(x[6][k] * cal_tr.get((x[3], k), 1.0) for k in COMPS) for x in train]); atr = np.array([x[5] for x in train])
slope = np.polyfit(ptr, atr, 1)
print(f"   after component calibration, train fit actual = {slope[0]:.2f}*pred + {slope[1]:+.2f}")
pt2 = slope[0] * p1 + slope[1]
print(f"   + slope shrink on test: RMSE {math.sqrt(np.mean((pt2 - a1) ** 2)):.4f}")
def topk(pr_, ac_, rs, k=12):
    by = {}
    for p_, a_, x in zip(pr_, ac_, rs): by.setdefault((x[1], x[2]), []).append((p_, a_))
    return np.mean([np.mean([a for _, a in sorted(l, reverse=True)[:k]]) for l in by.values()])
print(f"   top-12 picks avg actual (test): uncal {topk(p0, a0, test):.2f}  cal {topk(p1, a1, test):.2f}")

cal_all = fit_cal(rows)
print("\nFINAL CALIBRATION FACTORS (all data; actual/predicted by position and component; 1.00 = fine)")
for pos, lab in ((1, "GK"), (2, "DEF"), (3, "MID"), (4, "FWD")):
    print(f"   {lab}: " + "  ".join(f"{k} {cal_all[(pos, k)]:.2f}" for k in COMPS if (pos, k) in cal_all))
r2, b2_, p2, a2 = rmse(rows, cal_all)
print(f"   full-sample RMSE uncal {rmse(rows)[0]:.4f} -> cal {r2:.4f}")
ptot = np.array([sum(x[6][k] * cal_all.get((x[3], k), 1.0) for k in COMPS) for x in rows]); atot = np.array([x[5] for x in rows])
sl = np.polyfit(ptot, atot, 1)
print(f"   residual calibration slope after components: actual = {sl[0]:.2f}*pred + {sl[1]:+.2f}")
json.dump({"best": [best[0], best[1], best[2]], "cal": {f"{p}|{k}": v for (p, k), v in cal_all.items()}, "slope": [float(sl[0]), float(sl[1])]}, open("calib.json", "w"))

# ---------- finishing persistence ----------
print("\nFINISHING PERSISTENCE (outfield attackers, MID+FWD): actual goal pts / predicted goal pts in later rounds, by earlier (goals - xG)")
for lab, lo, hi in (("<= -1.5", -99, -1.5), ("-1.5..-0.75", -1.5, -0.75), ("-0.75..+0.75", -0.75, 0.75), ("+0.75..+1.5", 0.75, 1.5), (">= +1.5", 1.5, 99)):
    sub = [x for x in rows if x[3] in (3, 4) and lo <= x[8] < hi]
    if len(sub) < 30: continue
    sp = sum(x[6]["goal"] for x in sub); sa = sum(x[7]["goal"] for x in sub)
    print(f"   {lab:<13} n={len(sub):4d}  predicted {sp:6.1f}  actual {sa:6.1f}  ratio {sa / sp:.2f}")
print("BACKTEST2_DONE")
