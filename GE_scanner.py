import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="글로벌 퀀트 스캐너", layout="wide")

# --- 2. 데이터 로딩 함수 ---
@st.cache_data
def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(response.text)
        df = tables[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META']

@st.cache_data
def get_dax_tickers():
    return ['ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE', 'BMW.DE', 'CON.DE', '1COV.DE', 'DTG.DE', 'DBK.DE', 'DB1.DE', 'LHA.DE', 'DPW.DE', 'DTE.DE', 'EOAN.DE', 'FRE.DE', 'FME.DE', 'HEI.DE', 'HEN3.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE', 'MUV2.DE', 'PUM.DE', 'RWE.DE', 'SAP.DE', 'SIE.DE', 'SY1.DE', 'VOW3.DE', 'VNA.DE']

# --- 3. 강화된 상세 분석 로직 ---
def analyze_stock(ticker):
    try:
        # 지표 계산을 위해 100일치 데이터를 가져옵니다.
        data = yf.download(ticker, period="100d", interval="1d", progress=False)
        
        if data.empty or len(data) < 40:
            return None, f"{ticker}: 데이터 부족"
        
        # MultiIndex 대응
        if isinstance(data.columns, pd.MultiIndex):
            close = data['Close'][ticker]
            volume = data['Volume'][ticker]
        else:
            close = data['Close']
            volume = data['Volume']
            
        # [지표 1] 이동평균선
        ma20 = close.rolling(window=20).mean()
        ma5 = close.rolling(window=5).mean()
        
        # [지표 2] MACD 계산
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        macd_line = exp12 - exp26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        # 최근 데이터 추출
        curr_price = float(close.iloc[-1])
        prev_price = float(close.iloc[-2])
        curr_ma20 = float(ma20.iloc[-1])
        prev_ma20 = float(ma20.iloc[-2])
        curr_ma5 = float(ma5.iloc[-1])
        
        # [지표 3] 거래량 필터 (최근 5일 평균 거래량 대비 오늘 거래량)
        avg_vol_5d = volume.iloc[-6:-1].mean()
        curr_vol = volume.iloc[-1]
        vol_ratio = curr_vol / avg_vol_5d if avg_vol_5d > 0 else 0
        
        # 계산 결과 정리
        change = ((curr_price - prev_price) / prev_price) * 100
        disparity = ((curr_price / curr_ma20) - 1) * 100
        
        # --- 매수/매도 로직 강화 ---
        status, trend = "관망", "🌊 방향 탐색"
        
        # 1. 강력 매수 조건: 20일선 돌파 + 거래량 1.5배 폭발 + MACD 히스토그램 증가
        if (prev_price < prev_ma20) and (curr_price > curr_ma20):
            if vol_ratio >= 1.5 and macd_hist.iloc[-1] > macd_hist.iloc[-2]:
                status, trend = "🔥 강력 매수", "20일선 돌파 + 거래량 폭발 + MACD 상승"
            else:
                status, trend = "매수 관심", "20일선 돌파 (에너지 보충 필요)"
        
        # 2. 보유 및 매도 조건
        elif curr_price > curr_ma20:
            if disparity >= 15:
                status, trend = "과열 주의", "📢 이격률 과다 (조정 대비)"
            elif curr_price < curr_ma5:
                status, trend = "익절 고려", "⚠️ 5일선 이탈 (단기 힘 약화)"
            else:
                status, trend = "홀딩", "📈 상승 추세 유지"
        
        elif (prev_price > prev_ma20) and (curr_price < curr_ma20):
            status, trend = "매도/관망", "📉 20일선 하향 이탈"

        chart_url = f"https://finance.yahoo.com/chart/{ticker}"
        
        return [ticker, round(change, 2), round(curr_price, 2), f"{round(vol_ratio, 1)}배", f"{round(disparity, 2)}%", status, trend, chart_url], None
    except Exception as e:
        return None, f"{ticker}: 에러 ({str(e)})"

# --- 4. 메인 UI ---
st.sidebar.title("🌍 글로벌 퀀트 스캐너")
market = st.sidebar.radio("시장 선택", ["독일 (DAX)", "미국 (S&P 500)"])
full_list = get_dax_tickers() if market == "독일 (DAX)" else get_sp500_tickers()

items_per_page = 40
total_pages = (len(full_list) // items_per_page) + 1
page_num = st.sidebar.number_input(f"페이지 선택 (1-{total_pages})", min_value=1, max_value=total_pages, value=1)

start_idx = (page_num - 1) * items_per_page
target_tickers = full_list[start_idx : start_idx + items_per_page]

if st.sidebar.button("🚀 퀀트 분석 시작"):
    results = []
    error_logs = []
    prog = st.progress(0)
    
    for i, t in enumerate(target_tickers):
        res, err = analyze_stock(t)
        if res: results.append(res)
        if err: error_logs.append(err)
        prog.progress((i + 1) / len(target_tickers))
    
    if results:
        df = pd.DataFrame(results, columns=['티커', '등락률', '현재가', '거래량비', '이격률', '상태', '해석', '차트'])
        
        # 강조 스타일 적용
        def color_status(val):
            if '강력 매수' in val: return 'background-color: #ff4b4b; color: white'
            if '매수 관심' in val: return 'color: #ff4b4b'
            if '이탈' in val or '매도' in val: return 'color: #31333f; background-color: #f0f2f6'
            return ''

        st.dataframe(
            df.style.applymap(color_status, subset=['상태']),
            use_container_width=True, 
            hide_index=True,
            column_config={"차트": st.column_config.LinkColumn("차트 보기", display_text="Open 🔗")}
        )
    
    if error_logs:
        with st.expander("⚠️ 분석 실패 로그"):
            for log in error_logs: st.write(log)
            
    st.success(f"✅ 분석 완료! {len(results)}개 종목")
