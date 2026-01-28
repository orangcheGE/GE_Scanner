import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="글로벌 20일선 스마트 스캐너", layout="wide")

# --- 2. 데이터 로딩 함수 (캐싱 적용) ---
@st.cache_data
def get_sp500_tickers():
    """Wikipedia에서 S&P 500 리스트 실시간 추출"""
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        table = pd.read_html(url)
        df = table[0]
        return df['Symbol'].tolist()
    except:
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'] # 실패 시 비상용 리스트

@st.cache_data
def get_dax_tickers():
    """독일 DAX 40 주요 종목 리스트"""
    return [
        'ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE', 'BMW.DE', 'CON.DE', 
        '1COV.DE', 'DTG.DE', 'DBK.DE', 'DB1.DE', 'LHA.DE', 'DPW.DE', 'DTE.DE', 'EOAN.DE', 
        'FRE.DE', 'FME.DE', 'HEI.DE', 'HEN3.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE', 
        'MUV2.DE', 'PUM.DE', 'RWE.DE', 'SAP.DE', 'SIE.DE', 'SY1.DE', 'VOW3.DE', 'VNA.DE'
    ]

# --- 3. 주식 분석 로직 ---
def analyze_stock(ticker_symbol):
    try:
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="60d")
        if len(df) < 30: return None
        
        # 지표 계산
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['5MA'] = df['Close'].rolling(window=5).mean()
        
        # MACD 계산
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = macd - signal

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price = last['Close']
        ma20 = last['20MA']
        change = ((price - prev['Close']) / prev['Close']) * 100
        disparity = ((price / ma20) - 1) * 100
        
        # 상태 판별
        status, trend = "관망", "🌊 방향 탐색"
        if disparity >= 12: status, trend = "과열 주의", "🔥 이격 과다"
        elif price > ma20:
            if price < last['5MA']: status, trend = "추세 이탈", "⚠️ 5일선 하회"
            else: status, trend = "홀드", "📈 상승 유지"
        elif (prev['Close'] < prev['20MA']) and (price > ma20):
            status, trend = "매수 관심", "🔥 20일선 돌파"

        chart_url = f"https://finance.yahoo.com/quote/{ticker_symbol}"
        return [ticker_symbol, round(change, 2), round(price, 2), round(ma20, 2), f"{round(disparity, 2)}%", status, trend, chart_url]
    except:
        return None

# --- 4. 메인 UI ---
st.sidebar.title("🌍 글로벌 마켓 설정")
market_choice = st.sidebar.selectbox("시장 선택", ["독일 (DAX 40)", "미국 (S&P 500)"])

if market_choice == "독일 (DAX 40)":
    tickers = get_dax_tickers()
    st.title("🇩🇪 독일 주식 스캐너")
else:
    all_sp500 = get_sp500_tickers()
    num_to_scan = st.sidebar.slider("스캔할 종목 수 (상위순)", 10, 500, 50)
    tickers = all_sp500[:num_to_scan]
    st.title("🇺🇸 S&P 500 스마트 스캐너")

start_btn = st.sidebar.button("🚀 분석 시작")

if start_btn:
    results = []
    progress_bar = st.progress(0)
    
    for i, t in enumerate(tickers):
        res = analyze_stock(t)
        if res: results.append(res)
        progress_bar.progress((i + 1) / len(tickers))
    
    df_res = pd.DataFrame(results, columns=['티커', '등락률', '현재가', '20MA', '이격률', '상태', '해석', '차트'])
    
    # 결과 출력
    st.dataframe(
        df_res.style.applymap(lambda x: 'color: #ef5350' if '매수' in str(x) else '', subset=['상태']),
        use_container_width=True,
        column_config={"차트": st.column_config.LinkColumn("차트")}
    )
    st.success(f"✅ {len(df_res)}개 종목 분석 완료!")
