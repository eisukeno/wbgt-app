# -*- coding: utf-8 -*-
"""
WBGT Dashboard  – Tokyo / Kanagawa
  • Latest 1-hour observation
  • 3-hourly forecast for today & tomorrow
run:  streamlit run wbgt_dashboard.py
"""
import streamlit as st
import pandas as pd
import requests, io, datetime as dt, pytz

JST = pytz.timezone('Asia/Tokyo')
PREFS = {'Tokyo': 'tokyo', 'Kanagawa': 'kanagawa'}

# ------------------------------------------------------------
# 共通関数
# ------------------------------------------------------------
def parse_header_time(tok: str) -> dt.datetime:
    base = dt.datetime.strptime(tok[:8], '%Y%m%d')
    h    = int(tok[8:10])
    if h == 24:                           # 24:00 -> 翌日 0:00
        base += dt.timedelta(days=1)
        h = 0
    return base.replace(hour=h)           # tz なし (Excel friendly)

@st.cache_data(ttl=1800)                 # 30 分キャッシュ
def fetch_forecast(pref_key):
    """今日・明日の 3 時間毎予測を返す DataFrame"""
    url = f'https://www.wbgt.env.go.jp/prev15WG/dl/yohou_{pref_key}.csv'
    txt = requests.get(url, timeout=10).text
    lines = txt.splitlines()

    hdr_tok = [x for x in lines[0].split(',')[2:] if x]
    times   = [parse_header_time(t) for t in hdr_tok]

    vals_raw = lines[1].split(',')[2:]
    vals = [int(v.strip())/10 if v.strip() else None for v in vals_raw]

    df = pd.DataFrame({'Datetime': times, 'WBGT': vals})
    today = dt.datetime.now().date()
    tomorrow = today + dt.timedelta(days=1)
    today_df    = df[df['Datetime'].dt.date == today]
    tomorrow_df = df[df['Datetime'].dt.date == tomorrow]
    return today_df, tomorrow_df

@st.cache_data(ttl=900)                  # 15 分キャッシュ
def fetch_current(pref_key):
    """最新 1 本の実況値と時刻"""
    now = dt.datetime.now()
    url = f'https://www.wbgt.env.go.jp/est15WG/dl/wbgt_{pref_key}_{now:%Y%m}.csv'
    df  = pd.read_csv(io.StringIO(requests.get(url, timeout=10).text))
    # 24:00 補正
    df['Date_dt'] = pd.to_datetime(df['Date'], format='%Y/%m/%d')
    mask24 = df['Time'].str.strip().str.startswith('24')
    if mask24.any():
        df.loc[mask24, 'Date_dt'] += pd.Timedelta(days=1)
        df.loc[mask24, 'Time'] = df.loc[mask24, 'Time'].str.replace(r'^24:', '00:', regex=True)

    dtcol = pd.to_datetime(df['Date_dt'].dt.strftime('%Y/%m/%d') + ' ' + df['Time'].str.strip(),
                           format='%Y/%m/%d %H:%M')
    df['Datetime'] = dtcol
    latest = df[df.iloc[:,2].notna()].iloc[-1]
    return latest['Datetime'], latest.iloc[2]

def risk_level(val: float|int|None):
    if val is None:
        return 'N/A', '#CCCCCC'
    if val < 21:
        return '安全（ほぼ問題なし）', '#8fd175'
    if val < 25:
        return '注意（21〜25℃）', '#69c6ff'   # Blue
    if val < 28:
        return '警戒（25〜28℃）', '#fff15c'   # Yellow
    if val < 31:
        return '厳重警戒（28〜31℃）', '#ffa54c' # Orange
    return '危険（31℃以上）', '#ff4c4c'        # Red

# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
st.set_page_config(page_title='WBGT Monitor', layout='wide')
st.title('WBGT Monitor – 東京 / 神奈川')

pref_display = st.selectbox('都道府県を選択', list(PREFS.keys()), index=0)
pref_key = PREFS[pref_display]

# --- データ取得 ---
cur_time, cur_val = fetch_current(pref_key)
today_df, tomorrow_df = fetch_forecast(pref_key)

# --- 現在値表示 ---
lv_text, lv_color = risk_level(cur_val)
st.subheader(f'最新実況値（{pref_display}）')
col1, col2 = st.columns([1,3])
with col1:
    st.metric('WBGT', f'{cur_val:.1f}' if cur_val is not None else 'N/A')
with col2:
    st.markdown(f"""
        <div style="padding:10px; border-radius:8px; background:{lv_color};">
        <b>リスクレベル：</b>{lv_text}<br>
        <small>観測時刻：{cur_time:%Y-%m-%d %H:%M}</small>
        </div>
    """, unsafe_allow_html=True)

st.divider()

# --- 予測グラフ ---
tab1, tab2 = st.tabs(['今日の予測', '明日の予測'])
with tab1:
    st.line_chart(today_df.set_index('Datetime')['WBGT'],
                  height=300, use_container_width=True)
with tab2:
    st.line_chart(tomorrow_df.set_index('Datetime')['WBGT'],
                  height=300, use_container_width=True)
    
# 2) 今日の WBGT が 28℃ 以上になる見込みなら注意喚起
max_today = today_df['WBGT'].max()

if pd.isna(max_today):
    # 予測が取れなかった場合
    st.info("本日の予測データが取得できませんでした。")
elif max_today >= 28:
    # 28℃ 以上になる見込みがある
    st.warning(
        "本日、実写等の「連続して１時間以上又は１日４時間を超えて実施」が"
        "見込まれる作業を行う場合は体調チェック表に記入をしてください。"
    )
else:
    # 28℃ 未満で収まりそう
    st.success("本日は WBGT が 28℃ 以上にはならなさそうです。※チェックシートは不要です。")

st.caption('データ出典：環境省 WBGT 注意喚起サービス（3 時間毎予測 / 1 時間毎実況）')    
