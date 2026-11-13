"""Streamlit UI stub.  Run:  pip install -e ".[app]" && streamlit run app/streamlit_app.py

Deliberately minimal: shows the model's top players by position and, if config/squad.toml exists, your
squad's lineup and captain per gameweek. See docs/ROADMAP.md (P3) for the planned UI.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from fplxpts.api import FPLClient
from fplxpts.config import SquadCfg, load_config, load_squad
from fplxpts.constants import POS
from fplxpts.data import load_season
from fplxpts.model import Projector
from fplxpts.optimize import pick_lineup

st.set_page_config(page_title="fplxpts", layout="wide")
st.title("fplxpts: expected points for FPL")


@st.cache_resource(ttl=3600)
def season():
    return load_season(FPLClient(".cache"))


@st.cache_resource(ttl=3600)
def projector(squad_path: str | None):
    squad = load_squad(squad_path) if squad_path else SquadCfg()
    return Projector(season(), load_config(), squad)


squad_file = Path("config/squad.toml")
pr = projector(str(squad_file) if squad_file.exists() else None)
proj = pr.project()
weeks = st.sidebar.slider("Window (gameweeks)", 1, 8, 5)
lo, hi = proj.first_gw, proj.first_gw + weeks - 1
els = pr.season.elements

st.subheader(f"Top players, GW{lo}-{hi}")
cols = st.columns(4)
for col, (pid_pos, name) in zip(cols, POS.items()):
    pool = [p for p in proj.series if els[p]["element_type"] == pid_pos and els[p]["minutes"] >= 270 and proj.available(p)]
    top = sorted(pool, key=lambda p: -proj.pts(p, lo, hi))[:10]
    col.markdown(f"**{name}**")
    col.dataframe(pd.DataFrame({"player": [els[p]["web_name"] for p in top], "price": [els[p]["now_cost"] / 10 for p in top],
                                "xPts": [round(proj.pts(p, lo, hi), 1) for p in top]}), hide_index=True)

if pr.ids:
    st.subheader("Your squad")
    ids = list(pr.ids.values())
    st.dataframe(pd.DataFrame({"player": [els[p]["web_name"] for p in ids],
                               **{f"GW{g}": [round(proj.series.get(p, {}).get(g, 0), 1) for p in ids] for g in range(lo, hi + 1)}}),
                 hide_index=True)
    for gw in range(lo, hi + 1):
        lu = pick_lineup(ids, proj, gw)
        st.write(f"**GW{gw}** {lu.formation}  XI {lu.total:.1f}  Captain: {els[lu.captain]['web_name']}")
else:
    st.info("Copy config/squad.example.toml to config/squad.toml to see your squad here.")
