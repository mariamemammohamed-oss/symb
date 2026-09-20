import json
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# ---------- الإعدادات ----------
DATA_CSV = Path("candidates.csv")        # جدول المرشحين (CSV UTF-8)
DATA_XLSX = Path("candidates.xlsx")      # بديل: ملف إكسل مباشر
SYMBOLS_DIR = Path("symbols")            # مجلد صور الرموز
GEOJSON_NAMES = [                        # أسماء ملف الخريطة المحتملة
    "suze.geojson",
    "suez.geojson",
    "suze.geojson.json",
    "suez.geojson.json",
]
SEATS = 2                                # عدد الفائزين لو مفيش عمود winner
COLS = 5                                 # عدد الرموز في الصف
SUEZ_CENTER = [29.9668, 32.5498]
WINNER_VALUES = {"1", "yes", "true", "نعم", "فائز"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})


# ---------- دوال مساعدة ----------
def read_table():
    if DATA_CSV.exists():
        for enc in ("utf-8-sig", "cp1256"):
            for sep in (",", ";", "\t"):
                try:
                    t = pd.read_csv(DATA_CSV, sep=sep, encoding=enc)
                except (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
                    continue
                if "votes" in [str(c).strip().lower() for c in t.columns]:
                    return t
    if DATA_XLSX.exists():
        return pd.read_excel(DATA_XLSX)
    return None


def clean_table(df):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={"mame": "name"})  # تصحيح خطأ إملائي شائع في عنوان العمود
    missing = {"name", "votes", "symbol"} - set(df.columns)
    if missing:
        raise ValueError("الأعمدة الناقصة: " + ", ".join(sorted(missing)))
    df = df.dropna(subset=["name"]).copy()
    votes = df["votes"].astype(str).str.translate(DIGITS).str.replace(r"[,٬\s]", "", regex=True)
    df["votes"] = pd.to_numeric(votes, errors="coerce").fillna(0).astype(int)
    df = df.sort_values("votes", ascending=False, kind="stable").reset_index(drop=True)
    df["rank"] = df.index + 1
    if "winner" in df.columns:
        df["is_winner"] = df["winner"].astype(str).str.strip().str.lower().isin(WINNER_VALUES)
    else:
        df["is_winner"] = df["rank"] <= SEATS
    if "party" in df.columns:
        df["party"] = df["party"].fillna("مستقل").astype(str).str.strip()
    else:
        df["party"] = "مستقل"
    return df


def norm(text):
    """توحيد اسم الرمز: يتجاهل كلمة رمز و(ال) والامتداد وبعض الفروق في الحروف."""
    s = str(text).strip()
    if Path(s).suffix.lower() in IMG_EXT:
        s = Path(s).stem
    s = s.translate(AR_NORM).replace("_", " ").replace("-", " ")
    words = [w for w in s.split() if w != "رمز"]
    words = [w[2:] if w.startswith("ال") and len(w) > 3 else w for w in words]
    return "".join(words).lower()


def build_symbol_index():
    index = {}
    if SYMBOLS_DIR.exists():
        for f in sorted(SYMBOLS_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in IMG_EXT:
                index.setdefault(norm(f.name), f)
    return index


def find_symbol(value, index):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    try:
        exact = SYMBOLS_DIR / text
        if exact.is_file():
            return exact
    except OSError:
        pass
    return index.get(norm(text))


def short_label(value):
    words = [w for w in str(value).split() if w != "رمز"]
    return " ".join(words) if words else str(value)


def round_coords(obj, nd=4):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(v, nd) for v in obj]
        return [round_coords(o, nd) for o in obj]
    return obj


def first_xy(coords):
    while isinstance(coords, list) and coords and isinstance(coords[0], list):
        coords = coords[0]
    return coords


@st.cache_data
def load_geojson(path_str, mtime):
    """يقرأ ملف الخريطة ويخفّف حجمه (يحذف الخصائص ويقرّب الإحداثيات)."""
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    kind = data.get("type")
    if kind == "FeatureCollection":
        feats = data.get("features", [])
    elif kind == "Feature":
        feats = [data]
    else:
        feats = [{"type": "Feature", "properties": {}, "geometry": data}]
    out = []
    for f in feats:
        g = f.get("geometry")
        if not g:
            continue
        g = dict(g)
        if "coordinates" in g:
            g["coordinates"] = round_coords(g["coordinates"])
        out.append({"type": "Feature", "properties": {}, "geometry": g})
    return {"type": "FeatureCollection", "features": out}


# ---------- الصفحة ----------
st.set_page_config(page_title="مرشحو دائرة السويس", layout="centered")

st.markdown(
    """
    <style>
    .stApp{direction:rtl;text-align:right}
    div[data-testid="stHorizontalBlock"]{flex-direction:row !important;flex-wrap:wrap !important;gap:0.4rem}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]{
        min-width:15% !important;flex:1 1 15% !important}
    </style>
    """,
    unsafe_allow_html=True,
)

raw = read_table()
if raw is None:
    st.error("لم أجد ملف candidates.csv بجانب هذا الملف. احفظ الجدول بصيغة CSV UTF-8 في نفس المجلد.")
    st.stop()

try:
    df = clean_table(raw)
except ValueError as e:
    st.error(str(e))
    st.stop()

if df.empty:
    st.error("الجدول فاضي.")
    st.stop()

symbol_index = build_symbol_index()
total_votes = int(df["votes"].sum())

if "sel" not in st.session_state or st.session_state.sel not in set(df["rank"]):
    st.session_state.sel = 1

cur = df[df["rank"] == st.session_state.sel].iloc[0]

# ---------- العنوان والأرقام ----------
st.title("مرشحو دائرة السويس")
st.caption("المعروض: المرشحون الذين توفرت نتائجهم فقط.")

c1, c2, c3 = st.columns(3)
c1.metric("مرشحون", f"{len(df):,}")
c2.metric("فائزون", f"{int(df['is_winner'].sum()):,}")
c3.metric("مجموع الأصوات", f"{total_votes:,}")

# ---------- الخريطة ----------
color = "#185FA5" if cur["is_winner"] else "#888780"
opacity = 0.4 if cur["is_winner"] else 0.1

geo = None
geo_file = next((Path(n) for n in GEOJSON_NAMES if Path(n).exists()), None)
if geo_file:
    try:
        geo = load_geojson(str(geo_file), geo_file.stat().st_mtime)
        xy = first_xy(geo["features"][0]["geometry"]["coordinates"])
        if not (abs(xy[0]) <= 180 and abs(xy[1]) <= 90):
            st.warning("إحداثيات ملف الخريطة ليست WGS84. حوّلها في ArcGIS بأداة Project.")
            geo = None
    except Exception:
        st.warning("تعذّرت قراءة ملف الخريطة.")
        geo = None

m = folium.Map(location=SUEZ_CENTER, zoom_start=10, tiles="cartodbpositron")
if geo:
    layer = folium.GeoJson(
        geo,
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

# ---------- رموز المرشحين تحت الخريطة ----------
st.caption("اضغط على رمز المرشح")

for start in range(0, len(df), COLS):
    chunk = df.iloc[start:start + COLS]
    cols = st.columns(COLS)
    for col, (_, row) in zip(cols, chunk.iterrows()):
        with col:
            img = find_symbol(row["symbol"], symbol_index)
            if img:
                st.image(str(img), width=52)
            label = ("✔ " if row["is_winner"] else "") + short_label(row["symbol"])
            if st.button(label, key=f"cand_{row['rank']}", use_container_width=True):
                st.session_state.sel = int(row["rank"])
                st.rerun()

# ---------- كارت المرشح المختار ----------
share = cur["votes"] / total_votes if total_votes else 0

with st.container(border=True):
    img = find_symbol(cur["symbol"], symbol_index)
    if img:
        st.image(str(img), width=90)
    else:
        st.caption(f"صورة الرمز غير موجودة: {cur['symbol']}")
    st.subheader(str(cur["name"]))
    tag = "فائز" if cur["is_winner"] else f"الترتيب {int(cur['rank'])}"
    st.caption(f"{cur['party']} · {tag}")
    st.metric("عدد الأصوات", f"{int(cur['votes']):,}")
    st.progress(
        min(float(share), 1.0),
        text=f"{share * 100:.1f}% من مجموع أصوات المرشحين المعروضين",
    )