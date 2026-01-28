import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="글로벌 스마트 스캐너", layout="wide")

# --- 2. 데이터 로딩 함수 (403 에러 방지 적용) ---
@st.cache_data
def get_sp500_tickers():
    """Wikipedia에서 S&P 500 리스트 추출 (Header 추가로 403 방지)"""
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(response.text)
        df = tables[0]
        # 일부 티커에 포함된 '.'을 '-'로 변경 (yfinance 호환성: 예: BRK.B -> BRK-B)
        tickers = df['Symbol'].str.replace('.', '-', regex=False).tolist()
        return tickers
    except Exception as e:
        st.error(f"S&P 500 리스트 호출 실패. 기본 리스트로 전환합니다. (에러: {e})")
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'UNH', 'JNJ', 'V']

@st.cache_data
def get_dax_tickers():
    return [
        'ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE', 'BMW.DE', 'CON.DE', 
        '1COV.DE', 'DTG.DE', 'DBK.DE', 'DB1.DE', 'LHA.DE', 'DPW.DE', 'DTE.DE', 'EOAN.DE', 
        'FRE.DE', 'FME.DE', 'HEI.DE', 'HEN3.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE', 
        'MUV2.DE', 'PUM.DE', 'RWE.DE', 'SAP.DE', 'SIE.DE', 'SY1.DE', 'VOW3.DE', 'VNA.DE'
    ]

# --- 3. 분석 로직 (yfinance 최적화) ---
def analyze_stock(ticker):
    try:
        # 단일 종목 데이터를 빠르게 가져오기
        data = yf.download(ticker, period="60d", interval="1d", progress=False, show_errors=False)
        if data.empty or len(data) < 30: return None
        
        close = data['Close']
        ma20 = close.rolling(window=20).mean()
        ma5 = close.rolling(window=5).mean()
        
        last_price = float(close.iloc[-1])
        last_ma20 = float(ma20.iloc[-1])
        last_ma5 = float(ma5.iloc[-1])
        prev_price = float(close.iloc[-2])
        prev_ma20 = float(ma20.iloc[-2])
        
        change = ((last_price - prev_price) / prev_price) * 100
        disparity = ((last_price / last_ma20) - 1) * 100
        
        status, trend = "관망", "🌊 방향 탐색"
        if disparity >= 12: 
            status, trend = "과열 주의", "🔥 이격 과다"
        elif last_price > last_ma20:
            if last_price < last_ma5: 
                status, trend = "추세 이탈", "⚠️ 5일선 하회"
            else: 
                status, trend = "홀드", "📈 상승 유지"
        elif (prev_price < prev_ma20) and (last_price > last_ma20):
            status, trend = "매수 관심", "🔥 20일선 돌파"

        return [ticker, round(change, 2), round(last_price, 2), round(last_ma20, 2), f"{round(disparity, 2)}%", status, trend]
    except:
        return None

# --- 4. 사이드바 및 페이지 로직 ---
st.sidebar.title("🌍 글로벌 마켓 스캐너")
market = st.sidebar.radio("시장 선택", ["독일 (DAX)", "미국 (S&P 500)"])

if market == "독일 (DAX)":
    full_list = get_dax_tickers()
else:
    full_list = get_sp500_tickers()

items_per_page = 40
total_pages = (len(full_list) // items_per_page) + (1 if len(full_list) % items_per_page > 0 else 0)

page_num = st.sidebar.number_input(f"페이지 선택 (1-{total_pages})", min_value=1, max_value=total_pages, value=1)

start_idx = (page_num - 1) * items_per_page
end_idx = start_idx + items_per_page
target_tickers = full_list[start_idx:end_idx]

st.sidebar.info(f"선택된 종목: {len(target_tickers)}개 (전체 {len(full_list)}개 중)")
start_btn = st.sidebar.button("🚀 분석 시작")

# --- 5. 결과 테이블 ---
if start_btn:
    st.subheader(f"📊 {market} - {page_num}페이지 분석")
    results = []
    prog = st.progress(0)
    
    for i, t in enumerate(target_tickers):
        res = analyze_stock(t)
        if res: results.append(res)
        prog.progress((i + 1) / len(target_tickers))
    
    if results:
        df = pd.DataFrame(results, columns=['티커', '등락률', '현재가', '20MA', '이격률', '상태', '해석'])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.success("✅ 분석 완료!")
    else:
        st.error("데이터를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.")
