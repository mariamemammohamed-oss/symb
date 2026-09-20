import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# ---------- الإعدادات ----------
DATA_FILE = Path("candidates.csv")      # جدول المرشحين
SYMBOLS_DIR = Path("symbols")           # صور الرموز
GEOJSON_FILE = Path("suez.geojson")     # حدود الدائرة (اختياري)
SEATS = 2                               # عدد الفائزين لو مفيش عمود winner
COLS = 4                                # عدد الرموز في الصف
SUEZ_CENTER = [29.9668, 32.5498]
WINNER_VALUES = {"1", "yes", "true", "نعم", "فائز"}

st.set_page_config(page_title="مرشحو دائرة السويس", layout="centered")

# اتجاه عربي، وإبقاء الأعمدة جنب بعض على الموبايل
st.markdown(
    """
    <style>
    .stApp{direction:rtl;text-align:right}
    div[data-testid="stHorizontalBlock"]{flex-direction:row !important;flex-wrap:wrap !important;gap:0.5rem}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]{
        min-width:22% !important;flex:1 1 22% !important}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data(path: Path, mtime: float) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["votes"] = pd.to_numeric(df["votes"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("votes", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    if "winner" in df.columns:
        df["is_winner"] = df["winner"].astype(str).str.strip().str.lower().isin(WINNER_VALUES)
    else:
        df["is_winner"] = df["rank"] <= SEATS
    return df


def symbol_path(name) -> Path:
    return SYMBOLS_DIR / str(name)


if not DATA_FILE.exists():
    st.error("ضع ملف candidates.csv بجانب هذا الملف (الأعمدة: name, party, votes, symbol).")
    st.stop()

df = load_data(DATA_FILE, DATA_FILE.stat().st_mtime)
total_votes = int(df["votes"].sum())

if "selected" not in st.session_state or st.session_state.selected not in set(df["name"]):
    st.session_state.selected = df.loc[0, "name"]

cur = df[df["name"] == st.session_state.selected].iloc[0]

# ---------- العنوان والأرقام ----------
st.title("مرشحو دائرة السويس")

c1, c2, c3 = st.columns(3)
c1.metric("مرشح", f"{len(df):,}")
c2.metric("فائز", f"{int(df['is_winner'].sum()):,}")
c3.metric("الأصوات", f"{total_votes:,}")

# ---------- الخريطة ----------
color = "#185FA5" if cur["is_winner"] else "#888780"
opacity = 0.4 if cur["is_winner"] else 0.1

m = folium.Map(location=SUEZ_CENTER, zoom_start=10, tiles="cartodbpositron")
if GEOJSON_FILE.exists():
    data = json.loads(GEOJSON_FILE.read_text(encoding="utf-8"))
    layer = folium.GeoJson(
        data,
        tooltip="دائرة السويس",
        style_function=lambda _: {
            "fillColor": color,
            "color": color,
            "weight": 2,
            "fillOpacity": opacity,
        },
    )
    layer.add_to(m)
    m.fit_bounds(layer.get_bounds())
else:
    folium.Circle(
        SUEZ_CENTER,
        radius=15000,
        color=color,
        fill=True,
        fill_opacity=opacity,
        tooltip="دائرة السويس",
    ).add_to(m)

st_folium(m, height=260, use_container_width=True, returned_objects=[])

# ---------- الفلتر والبحث ----------
mode = st.radio(
    "العرض",
    ["الكل", "الفائزون فقط"],
    horizontal=True,
    label_visibility="collapsed",
)
query = st.text_input("ابحث باسم المرشح", "")

view = df
if mode == "الفائزون فقط":
    view = view[view["is_winner"]]
if query.strip():
    view = view[view["name"].str.contains(query.strip(), na=False)]

# ---------- شبكة الرموز ----------
if view.empty:
    st.warning("لا توجد نتائج مطابقة.")

for start in range(0, len(view), COLS):
    chunk = view.iloc[start:start + COLS]
    cols = st.columns(COLS)
    for col, (_, row) in zip(cols, chunk.iterrows()):
        with col:
            img = symbol_path(row["symbol"])
            if img.exists():
                st.image(str(img), width=64)
            label = ("✔ " if row["is_winner"] else "") + str(row["name"])
            if st.button(label, key=f"cand_{row['rank']}", use_container_width=True):
                st.session_state.selected = row["name"]
                st.rerun()

# ---------- كارت المرشح المختار ----------
share = cur["votes"] / total_votes if total_votes else 0

with st.container(border=True):
    img = symbol_path(cur["symbol"])
    if img.exists():
        st.image(str(img), width=80)
    st.subheader(str(cur["name"]))
    party = cur["party"] if "party" in cur and pd.notna(cur["party"]) else "مستقل"
    tag = "فائز" if cur["is_winner"] else f"الترتيب {int(cur['rank'])}"
    st.caption(f"{party} · {tag}")
    st.metric("عدد الأصوات", f"{int(cur['votes']):,}")
    st.progress(min(share, 1.0), text=f"{share * 100:.1f}% من إجمالي الأصوات")