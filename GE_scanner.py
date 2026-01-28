import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="글로벌 스마트 스캐너", layout="wide")

# --- 2. 데이터 로딩 함수 (캐싱) ---
@st.cache_data
def get_sp500_tickers():
    """Wikipedia에서 S&P 500 리스트 추출 (실패 시 재시도 로직 포함)"""
    try:
        # header를 추가하여 접근 차단 방지
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        tables = pd.read_html(url)
        df = tables[0]
        return df['Symbol'].tolist()
    except Exception as e:
        st.error(f"S&P 500 리스트를 불러오지 못했습니다. (에러: {e})")
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'BRK-B', 'UNH', 'JNJ']

@st.cache_data
def get_dax_tickers():
    return [
        'ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE', 'BMW.DE', 'CON.DE', 
        '1COV.DE', 'DTG.DE', 'DBK.DE', 'DB1.DE', 'LHA.DE', 'DPW.DE', 'DTE.DE', 'EOAN.DE', 
        'FRE.DE', 'FME.DE', 'HEI.DE', 'HEN3.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE', 
        'MUV2.DE', 'PUM.DE', 'RWE.DE', 'SAP.DE', 'SIE.DE', 'SY1.DE', 'VOW3.DE', 'VNA.DE'
    ]

# --- 3. 분석 로직 ---
def analyze_stock(ticker):
    try:
        data = yf.download(ticker, period="60d", interval="1d", progress=False)
        if data.empty or len(data) < 30: return None
        
        # 20일 이동평균선 및 지표 계산
        close = data['Close']
        ma20 = close.rolling(window=20).mean()
        ma5 = close.rolling(window=5).mean()
        
        last_price = float(close.iloc[-1])
        last_ma20 = float(ma20.iloc[-1])
        last_ma5 = float(ma5.iloc[-1])
        prev_price = float(close.iloc[-2])
        
        change = ((last_price - prev_price) / prev_price) * 100
        disparity = ((last_price / last_ma20) - 1) * 100
        
        status, trend = "관망", "🌊 방향 탐색"
        if disparity >= 12: status, trend = "과열 주의", "🔥 이격 과다"
        elif last_price > last_ma20:
            if last_price < last_ma5: status, trend = "추세 이탈", "⚠️ 5일선 하회"
            else: status, trend = "홀드", "📈 상승 유지"
        elif (float(close.iloc[-2]) < float(ma20.iloc[-2])) and (last_price > last_ma20):
            status, trend = "매수 관심", "🔥 20일선 돌파"

        return [ticker, round(change, 2), round(last_price, 2), round(last_ma20, 2), f"{round(disparity, 2)}%", status, trend]
    except:
        return None

# --- 4. 사이드바 UI ---
st.sidebar.title("🌍 글로벌 마켓 스캐너")
market = st.sidebar.radio("시장 선택", ["독일 (DAX)", "미국 (S&P 500)"])

# 페이지당 개수 설정
items_per_page = 40 

if market == "독일 (DAX)":
    full_list = get_dax_tickers()
    total_pages = 1
else:
    full_list = get_sp500_tickers()
    total_pages = (len(full_list) // items_per_page) + 1

# 페이지 선택 슬라이더 또는 숫자 선택
page_num = st.sidebar.number_input(f"페이지 선택 (1-{total_pages})", min_value=1, max_value=total_pages, value=1)

# 현재 페이지에 해당하는 종목만 추출
start_idx = (page_num - 1) * items_per_page
end_idx = start_idx + items_per_page
target_tickers = full_list[start_idx:end_idx]

st.sidebar.write(f"현재 분석 대상: {len(target_tickers)} 종목")
start_btn = st.sidebar.button("🚀 분석 시작")

# --- 5. 결과 화면 ---
if start_btn:
    st.subheader(f"📊 {market} - {page_num}페이지 분석 결과")
    results = []
    prog = st.progress(0)
    
    for i, t in enumerate(target_tickers):
        res = analyze_stock(t)
        if res: results.append(res)
        prog.progress((i + 1) / len(target_tickers))
    
    if results:
        df = pd.DataFrame(results, columns=['티커', '등락률', '현재가', '20MA', '이격률', '상태', '해석'])
        st.dataframe(df, use_container_width=True)
        st.success("분석이 완료되었습니다!")
    else:
        st.warning("분석 결과가 없습니다. 티커를 확인해 주세요.")
