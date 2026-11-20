"""
단일 종목(기본: KT&G 033780) 전체 일별 종가 수집 + 계절성/주기성 분석 + 매수·매도 구간 탐색
실행:  streamlit run ktng_seasonality.py
"""
import time
from datetime import date

import altair as alt
import numpy as np
import pandas as pd
import requests
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # 사내망 환경

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://stock.naver.com/',
}
RENAME = {'localTradedAt': '날짜', 'closePrice': '종가', 'openPrice': '시가',
          'highPrice': '고가', 'lowPrice': '저가', 'accumulatedTradingVolume': '거래량'}


# ─────────────────────────────────────────────
# 1. 데이터 수집
# ─────────────────────────────────────────────
def normalize_prices(df):
    df = df.rename(columns=RENAME)
    df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
    for col in ['종가', '시가', '고가', '저가', '거래량']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    df = df.dropna(subset=['날짜', '종가'])
    return df.drop_duplicates('날짜', keep='last').sort_values('날짜').reset_index(drop=True)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_all_prices(code, max_pages=400, page_size=60):
    """네이버 일별 시세를 데이터가 끝날 때까지 페이지 단위로 수집."""
    frames, seen = [], set()
    for page in range(1, max_pages + 1):
        url = f"https://m.stock.naver.com/api/stock/{code}/price?pageSize={page_size}&page={page}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=10, verify=False)
            if res.status_code != 200:
                break
            data = res.json()
        except Exception:
            break
        if not data or not isinstance(data, list):
            break
        page_df = pd.DataFrame(data)
        if 'localTradedAt' not in page_df.columns:
            break
        dates = set(page_df['localTradedAt'])
        if dates <= seen:          # 같은 페이지 반복 -> 종료
            break
        seen |= dates
        frames.append(page_df)
        if len(data) < page_size:  # 마지막 페이지
            break
        time.sleep(0.05)
    if not frames:
        return pd.DataFrame()
    return normalize_prices(pd.concat(frames, ignore_index=True))


def load_uploaded_csv(file):
    """날짜/종가 컬럼이 있는 CSV(Date/Close 도 허용)."""
    df = pd.read_csv(file)
    df = df.rename(columns={'Date': '날짜', 'date': '날짜', 'Close': '종가', 'close': '종가'})
    return normalize_prices(df)


# ─────────────────────────────────────────────
# 2. 분석 함수 (UI와 분리)
# ─────────────────────────────────────────────
def to_series(df):
    return df.set_index('날짜')['종가'].astype(float)


def tstat(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 3 or np.std(x, ddof=1) == 0:
        return np.nan
    return x.mean() / (np.std(x, ddof=1) / np.sqrt(len(x)))


def yearly_curves(s):
    """연도별 '전년 마지막 종가=100' 기준 누적 곡선 (완결된 연도만) + 올해 진행분."""
    curves, current = {}, None
    last_year = s.index[-1].year
    for y in sorted(set(s.index.year)):
        sy = s[s.index.year == y]
        prev = s[s.index < pd.Timestamp(y, 1, 1)]
        base = prev.iloc[-1] if len(prev) else sy.iloc[0]
        cal = sy.reindex(pd.date_range(f'{y}-01-01', f'{y}-12-31'))
        if pd.isna(cal.iloc[0]):
            cal.iloc[0] = base
        cal = cal.ffill()
        complete = sy.index[0] <= pd.Timestamp(y, 1, 15) and sy.index[-1] >= pd.Timestamp(y, 12, 15)
        if complete:
            curves[y] = (cal / base * 100).values[:365]
        elif y == last_year and sy.index[0] <= pd.Timestamp(y, 1, 15):
            vals = (cal / base * 100).values[:365].copy()
            vals[(pd.date_range(f'{y}-01-01', f'{y}-12-31')[:365] > s.index[-1])] = np.nan
            current = vals
    idx = pd.date_range('2001-01-01', '2001-12-31')[:365]   # 표시용 더미 연도(평년)
    curve_df = pd.DataFrame(curves, index=idx)
    cur_s = pd.Series(current, index=idx) if current is not None else None
    return curve_df, cur_s


def monthly_returns(s):
    m = s.groupby(s.index.to_period('M')).last()
    r = m.pct_change().dropna()
    if len(r) and r.index[-1] == pd.Timestamp.today().to_period('M'):
        r = r.iloc[:-1]                      # 진행 중인 달 제외
    return r * 100


def month_stats(r):
    df = pd.DataFrame({'ret': r.values, 'month': r.index.month})
    g = df.groupby('month')['ret']
    return pd.DataFrame({
        '평균(%)': g.mean(), '중앙값(%)': g.median(),
        '승률(%)': g.apply(lambda x: (x > 0).mean() * 100),
        '표본(년)': g.count(), 't값': g.apply(tstat),
    }).round(2)


def weekly_series(s):
    w = s.groupby(s.index.to_period('W')).last()
    if len(w) and w.index[-1] == pd.Timestamp.today().to_period('W'):
        w = w.iloc[:-1]                      # 진행 중인 주 제외
    iso = w.index.start_time.isocalendar()
    year = iso['year'].values.astype(int)
    week = np.minimum(iso['week'].values.astype(int), 52)
    return w, year, week


def seasonal_consistency(w, year, week, n_perm=200, seed=0):
    """주별 수익률의 연도 간 일관성: 각 연도를 '나머지 연도 평균'과 상관 (leave-one-out).
    무작위 셔플 대비 얼마나 큰지(p값 유사)도 계산."""
    ret = w.pct_change().values
    df = pd.DataFrame({'y': year, 'w': week, 'r': ret}).dropna()
    df = df.groupby(['y', 'w'])['r'].mean().unstack('w')
    df = df.loc[df.notna().sum(axis=1) >= 45]
    if len(df) < 5:
        return None

    def mean_corr(frame):
        cors = []
        for y in frame.index:
            others = frame.drop(y).mean()
            row = frame.loc[y]
            m = row.notna() & others.notna()
            if m.sum() >= 40 and row[m].std() > 0 and others[m].std() > 0:
                cors.append(np.corrcoef(row[m], others[m])[0, 1])
        return np.array(cors)

    actual = mean_corr(df)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_perm):
        shuffled = df.copy()
        for y in shuffled.index:
            vals = shuffled.loc[y].values.copy()
            rng.shuffle(vals)
            shuffled.loc[y] = vals
        null.append(mean_corr(shuffled).mean())
    p = (np.sum(np.array(null) >= actual.mean()) + 1) / (n_perm + 1)
    return {'mean_corr': actual.mean(), 'pos_share': (actual > 0).mean() * 100,
            'n_years': len(df), 'p_value': p}


def find_cycles(s, min_days=20, max_frac=1 / 3, top=8):
    """로그가격에서 3차 추세를 제거한 뒤 FFT로 지배적 주기 탐색."""
    y = np.log(s.values.astype(float))
    n = len(y)
    t = np.arange(n)
    resid = y - np.polyval(np.polyfit(t, y, 3), t)
    resid = (resid - resid.mean()) * np.hanning(n)
    power = np.abs(np.fft.rfft(resid)) ** 2
    freqs = np.fft.rfftfreq(n)
    periods, power = 1 / freqs[1:], power[1:]
    mask = (periods >= min_days) & (periods <= n * max_frac)
    periods, power = periods[mask], power[mask]
    order = np.argsort(periods)
    periods, power = periods[order], power[order]
    share = power / power.sum() * 100
    peaks = [i for i in range(1, len(power) - 1)
             if power[i] > power[i - 1] and power[i] > power[i + 1]]
    peaks = sorted(peaks, key=lambda i: -power[i])[:top]
    peak_df = pd.DataFrame({
        '주기(거래일)': [round(periods[i]) for i in peaks],
        '≈개월': [round(periods[i] / 21, 1) for i in peaks],
        '비중(%)': [round(share[i], 1) for i in peaks],
    })
    spec_df = pd.DataFrame({'주기(거래일)': periods, '비중(%)': share}).set_index('주기(거래일)')
    return peak_df, spec_df


def week_to_label(week):
    """ISO 주차 -> 대략적인 날짜 라벨 (기준: 2023년)."""
    week = int(week)
    d = date.fromisocalendar(2023, week, 1)
    return f"W{week:02d}(~{d.month}/{d.day})"


def window_returns(vals, first, years, buy_week, hold):
    out = {}
    n = len(vals)
    for y in years:
        i = first.get((y, buy_week))
        if i is None or i + hold > n - 1:
            continue
        out[y] = vals[i + hold] / vals[i] - 1
    return pd.Series(out, dtype=float)


def scan_windows(w, year, week, years, holds=range(2, 27), min_n_ratio=0.8):
    """매수 주차(1~52) x 보유 주수 조합별 성과. baseline(무조건 보유 평균) 대비 초과수익 포함."""
    vals = w.values
    n = len(vals)
    first = {}
    for i, (y, wk) in enumerate(zip(year, week)):
        first.setdefault((int(y), int(wk)), i)
    in_years = np.isin(year, list(years))
    baseline = {}
    for L in holds:
        idx = np.where(in_years & (np.arange(n) + L <= n - 1))[0]
        baseline[L] = np.mean(vals[idx + L] / vals[idx] - 1) if len(idx) else np.nan
    rows = []
    for b in range(1, 53):
        for L in holds:
            r = window_returns(vals, first, years, b, L)
            if len(r) < max(5, min_n_ratio * len(years)):
                continue
            rows.append({
                '매수주차': b, '보유(주)': L, 'n': len(r),
                '평균(%)': r.mean() * 100, '승률(%)': (r > 0).mean() * 100,
                '초과(%)': (r.mean() - baseline[L]) * 100, 't값': tstat(r.values),
            })
    return pd.DataFrame(rows), first


def pick_top(table, ascending=False, k=10):
    """매수주차별 최적 보유기간 하나씩만 남기고 t값 기준 상위/하위 k개."""
    if table.empty:
        return table
    t = table.dropna(subset=['t값'])
    best = t.loc[t.groupby('매수주차')['t값'].idxmin() if ascending else t.groupby('매수주차')['t값'].idxmax()]
    return best.sort_values('t값', ascending=ascending).head(k).reset_index(drop=True)


def evaluate_on(vals, first, years, picks):
    rows = []
    for _, p in picks.iterrows():
        r = window_returns(vals, first, years, int(p['매수주차']), int(p['보유(주)']))
        rows.append({'검증 n': len(r),
                     '검증 평균(%)': r.mean() * 100 if len(r) else np.nan,
                     '검증 승률(%)': (r > 0).mean() * 100 if len(r) else np.nan})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# 3. UI
# ─────────────────────────────────────────────
def render(df, code):
    s = to_series(df)
    st.success(f"{code} · {s.index[0]:%Y-%m-%d} ~ {s.index[-1]:%Y-%m-%d} · {len(s):,}거래일 "
               f"({s.index[0].year}~{s.index[-1].year})")
    if s.index[0].year > date.today().year - 10:
        st.warning("수집된 기간이 10년 미만입니다. API가 과거 데이터를 제한했을 수 있으니, "
                   "전체 이력 CSV를 사이드바에서 업로드하는 방법도 고려하세요.")
    st.download_button("종가 CSV 다운로드", df.to_csv(index=False).encode('utf-8-sig'),
                       file_name=f"{code}_daily.csv", mime="text/csv")
    st.caption("※ 네이버 시세가 배당락·유상증자 등을 반영한 수정주가가 아니면 해당 시점이 패턴에 섞입니다. "
               "결산배당 기업은 연말 전후 구간을 특히 따로 확인하세요.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📈 가격", "🗓️ 연간 곡선", "📊 월별·주별", "🔁 주기(FFT)", "🎯 매수·매도 구간"])

    with tab1:
        st.line_chart(s, use_container_width=True)
        st.line_chart(np.log(s), use_container_width=True)
        st.caption("아래는 로그 가격입니다. 장기 추세와 변동 폭을 비교할 때 유용합니다.")

    curve_df, cur = yearly_curves(s)
    with tab2:
        if curve_df.empty:
            st.info("완결된 연도 데이터가 없습니다.")
        else:
            show = pd.DataFrame({'평균': curve_df.mean(axis=1), '중앙값': curve_df.median(axis=1)})
            if cur is not None:
                show[f'{s.index[-1].year}(진행)'] = cur
            st.markdown(f"**연초(전년 말 종가=100) 대비 연간 곡선 – 완결 {curve_df.shape[1]}개 연도 평균**")
            st.line_chart(show, use_container_width=True)
            with st.expander("연도별 곡선 전부 보기"):
                st.line_chart(curve_df, use_container_width=True)

    r_month = monthly_returns(s)
    w, w_year, w_week = weekly_series(s)
    with tab3:
        ms = month_stats(r_month)
        st.markdown("**월별 수익률 통계** (t값 절대값 2 이상이면 우연이라 보기 어려운 수준, 다만 12개월 중 고른 것이라 과대평가 주의)")
        st.bar_chart(ms['평균(%)'])
        st.dataframe(ms, use_container_width=True)
        heat = pd.DataFrame({'연도': r_month.index.year, '월': r_month.index.month, '수익률(%)': r_month.values})
        st.altair_chart(
            alt.Chart(heat).mark_rect().encode(
                x=alt.X('월:O'), y=alt.Y('연도:O'),
                color=alt.Color('수익률(%):Q', scale=alt.Scale(scheme='redblue', domainMid=0, reverse=True)),
                tooltip=['연도', '월', alt.Tooltip('수익률(%):Q', format='.1f')]),
            use_container_width=True)

        wk = pd.DataFrame({'wk': w_week, 'r': w.pct_change().values * 100}).dropna()
        wk_stat = wk.groupby('wk')['r'].agg(['mean', 'count']).rename(columns={'mean': '평균 주간수익률(%)', 'count': '표본'})
        st.markdown("**주차별 평균 수익률** (ISO 주차 1~52)")
        st.bar_chart(wk_stat['평균 주간수익률(%)'])

        cons = seasonal_consistency(w, w_year, w_week)
        if cons:
            st.markdown("**계절성이 실제로 있는지 점검** (주간 수익률의 연도 간 일관성)")
            c1, c2, c3 = st.columns(3)
            c1.metric("연도 간 평균 상관", f"{cons['mean_corr']:.2f}")
            c2.metric("상관 > 0 인 연도 비율", f"{cons['pos_share']:.0f}%")
            c3.metric("무작위 대비 p값", f"{cons['p_value']:.3f}", help="무작위로 섞은 데이터가 이 상관 이상을 만들 확률(작을수록 계절성 근거가 강함)")
            st.caption(f"{cons['n_years']}개 연도 기준. p값이 0.05보다 크면 '연중 규칙적 패턴'이라 부르기 어렵습니다.")

    with tab4:
        if len(s) < 500:
            st.info("주기 분석에는 최소 2년(약 500거래일) 이상이 필요합니다.")
        else:
            peaks, spec = find_cycles(s)
            st.markdown("**지배적 주기 후보** (로그가격에서 장기 추세 제거 후 스펙트럼)")
            st.dataframe(peaks, use_container_width=True, hide_index=True)
            st.line_chart(spec, use_container_width=True)
            st.caption("1년 ≈ 245거래일, 6개월 ≈ 122, 3개월(분기) ≈ 61. 이 부근에 뚜렷한 봉우리가 있으면 연간·반기·분기 주기를 의심할 수 있습니다. "
                       "주기가 길수록 관측 횟수가 적어 신뢰도가 낮습니다.")

    with tab5:
        years_all = sorted(set(int(y) for y in w_year))
        years_all = [y for y in years_all if (w_year == y).sum() >= 45]   # 거의 완결된 연도만
        if len(years_all) < 8:
            st.info("구간 탐색에는 최소 8개 연도가 필요합니다.")
            return
        split = max(5, int(len(years_all) * 0.7))
        train_years, test_years = years_all[:split], years_all[split:]
        st.markdown(f"**훈련 {train_years[0]}~{train_years[-1]} ({len(train_years)}년) → 검증 {test_years[0]}~{test_years[-1]} ({len(test_years)}년)**")
        st.caption("훈련 기간에서 고른 구간이 이후 기간에도 통하는지 확인합니다. 조합이 1,000개 이상이라 훈련 성과만 보면 우연히 좋아 보이는 구간이 반드시 나옵니다.")

        train_table, first = scan_windows(w, w_year, w_week, train_years)
        if train_table.empty:
            st.info("조건을 만족하는 구간이 없습니다.")
            return
        vals = w.values
        for title, asc in [("🟢 매수 후보 (훈련 t값 상위)", False), ("🔴 회피/매도 후보 (훈련 t값 하위)", True)]:
            picks = pick_top(train_table, ascending=asc)
            test_eval = evaluate_on(vals, first, test_years, picks)
            out = pd.concat([picks, test_eval], axis=1)
            out.insert(0, '매수시점', out['매수주차'].map(week_to_label))
            out.insert(1, '매도시점', (out['매수주차'] + out['보유(주)']).map(lambda x: week_to_label((x - 1) % 52 + 1)))
            st.markdown(f"**{title}**")
            st.dataframe(out.round(2).drop(columns=['매수주차']), use_container_width=True, hide_index=True)
            if not asc and not out.empty:
                ok = ((out['검증 평균(%)'] > 0) & (out['검증 승률(%)'] >= 50)).sum()
                st.caption(f"검증 기간에서도 평균 수익 > 0 이고 승률 50% 이상인 후보: {len(out)}개 중 {ok}개")

        st.markdown("**특정 구간의 연도별 결과 보기**")
        c1, c2 = st.columns(2)
        b = c1.number_input("매수 주차 (1~52)", 1, 52, int(pick_top(train_table).iloc[0]['매수주차']))
        L = c2.number_input("보유 주수", 2, 26, int(pick_top(train_table).iloc[0]['보유(주)']))
        full_table, full_first = scan_windows(w, w_year, w_week, years_all)
        r = window_returns(vals, full_first, years_all, int(b), int(L)) * 100
        if r.empty:
            st.info("해당 구간 데이터가 없습니다.")
        else:
            st.caption(f"{week_to_label(b)} 매수 → {L}주 보유 | 평균 {r.mean():+.1f}% · 승률 {(r > 0).mean() * 100:.0f}% · "
                       f"최악 {r.min():+.1f}% · 표본 {len(r)}년")
            st.bar_chart(r.rename('수익률(%)'))


def main():
    st.set_page_config(page_title="단일 종목 계절성 분석", layout="wide")
    st.title("🔍 단일 종목 계절성·주기 분석")
    code = st.sidebar.text_input("종목코드", value="033780", max_chars=6).strip().zfill(6)
    max_pages = st.sidebar.slider("최대 페이지(페이지당 60거래일)", 50, 600, 400, step=50)
    uploaded = st.sidebar.file_uploader("또는 CSV 업로드 (날짜, 종가 컬럼)", type="csv")
    if st.sidebar.button("🚀 데이터 가져오기 / 분석", use_container_width=True):
        if uploaded is not None:
            st.session_state['ss_df'] = load_uploaded_csv(uploaded)
            st.session_state['ss_code'] = code
        else:
            with st.spinner("전체 일별 시세를 수집하는 중입니다..."):
                data = fetch_all_prices(code, max_pages=max_pages)
            if data.empty:
                st.error("시세를 가져오지 못했습니다. 종목코드/네트워크를 확인하거나 CSV를 업로드하세요.")
            else:
                st.session_state['ss_df'] = data
                st.session_state['ss_code'] = code
    if 'ss_df' in st.session_state:
        render(st.session_state['ss_df'], st.session_state.get('ss_code', code))
    else:
        st.info("왼쪽에서 종목코드를 확인하고 '데이터 가져오기 / 분석'을 눌러주세요.")


if __name__ == "__main__":
    main()
