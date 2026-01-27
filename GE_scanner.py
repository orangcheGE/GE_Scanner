import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import urllib.parse

# 1. 페이지 설정
st.set_page_config(page_title="독일 주식 20일선 스마트 스캐너", layout="wide")

# --- 독일 주요 지수 티커 리스트 ---
DAX_TICKERS = [
    'ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE', 'BMW.DE', 'CON.DE', 
    '1COV.DE', 'DTG.DE', 'DBK.DE', 'DB1.DE', 'LHA.DE', 'DPW.DE', 'DTE.DE', 'EOAN.DE', 
    'FRE.DE', 'FME.DE', 'HEI.DE', 'HEN3.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE', 
    'MUV2.DE', 'PUM.DE', 'RWE.DE', 'SAP.DE', 'SIE.DE', 'SY1.DE', 'VOW3.DE', 'VNA.DE'
] # 주요 종목 예시 (전체는 yfinance의 Ticker 클래스로 확장 가능)

# --- 데이터 분석 로직 ---
def analyze_german_stock(ticker_symbol):
    try:
        # 데이터 가져오기 (최근 60일치)
        stock = yf.Ticker(ticker_symbol)
        df = stock.history(period="60d")
        
        if len(df) < 30: return None
        
        # 보조지표 계산
        df['20MA'] = df['Close'].rolling(20).mean()
        df['5MA'] = df['Close'].rolling(5).mean()
        
        # MACD 계산 (에너지 분석용)
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = macd - signal

        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]

        price = last['Close']
        ma20 = last['20MA']
        ma5 = last['5MA']
        change = ((price - prev['Close']) / prev['Close']) * 100
        
        # 이격률
        disparity = ((price / ma20) - 1) * 100
        
        # 상태 로직 (기존 로직 유지)
        status, trend = "관망", "🌊 방향 탐색"
        macd_curr, macd_prev, macd_prev2 = last['MACD_hist'], prev['MACD_hist'], prev2['MACD_hist']
        is_energy_fading = macd_curr < macd_prev < macd_prev2

        if disparity >= 12:
            status, trend = "과열 주의", "🔥 이격 과다"
        elif price > ma20:
            if price < ma5:
                status, trend = "추세 이탈", "⚠️ 5일선 하회"
            elif 0 <= disparity <= 3:
                status, trend = "적극 매수", "🚀 이평선 근접"
            else:
                status, trend = "홀드", "📈 상승 유지"
        elif (prev['Close'] < prev['20MA']) and (price > ma20):
            status, trend = "매수 관심", "🔥 20일선 돌파"
        elif price < ma20:
            status, trend = "관망", "🌅 바닥 다지기"

        accel = "📈 가속" if macd_curr > macd_prev else "⚠️ 감속"
        chart_url = f"https://finance.yahoo.com/chart/{ticker_symbol}"
        
        return [ticker_symbol, round(change, 2), round(price, 2), round(ma20, 2), f"{round(disparity, 2)}%", status, f"{trend} | {accel}", chart_url]
    except Exception as e:
        return None

# --- UI 스타일링 ---
def show_styled_dataframe(df):
    if df.empty:
        st.info("분석된 종목이 없습니다.")
        return

    def color_status(val):
        if any(k in str(val) for k in ['매수', '적극']): return 'color: #ef5350; font-weight: bold'
        if any(k in str(val) for k in ['과열', '주의']): return 'color: #ffa726; font-weight: bold'
        if any(k in str(val) for k in ['매도', '이탈']): return 'color: #42a5f5; font-weight: bold'
        return ''

    st.dataframe(
        df.style.applymap(color_status, subset=['상태'])
        .applymap(lambda x: 'color: #ef5350' if float(str(x).replace('%','')) > 0 else 'color: #42a5f5', subset=['등락률']),
        use_container_width=True,
        column_config={"차트": st.column_config.LinkColumn("Yahoo Finance")},
        hide_index=True
    )

# --- 메인 UI ---
st.title("🇩🇪 독일 주식 20일선 스마트 스캐너")
st.caption("Yahoo Finance 실시간 데이터를 기반으로 분석합니다.")

st.sidebar.header("시장 설정")
market_type = st.sidebar.selectbox("지수 선택", ["DAX 40 (우량주)", "직접 입력"])
custom_ticker = ""
if market_type == "직접 입력":
    custom_ticker = st.sidebar.text_input("티커 입력 (예: SAP.DE, VOW3.DE)")

start_btn = st.sidebar.button("🚀 분석 시작")

# 상태 관리
BUY_STATUS = ["매수", "적극 매수", "매수 관심"]
SELL_STATUS = ["과열 주의", "추세 이탈"]

if start_btn:
    tickers = DAX_TICKERS if market_type == "DAX 40 (우량주)" else [custom_ticker]
    results = []
    
    progress_text = "독일 시장 데이터를 불러오는 중입니다..."
    my_bar = st.progress(0, text=progress_text)
    
    for i, ticker in enumerate(tickers):
        res = analyze_german_stock(ticker)
        if res:
            results.append(res)
        my_bar.progress((i + 1) / len(tickers))
    
    cols = ['티커', '등락률', '현재가(€)', '20MA', '이격률', '상태', '해석', '차트']
    st.session_state['df_ger'] = pd.DataFrame(results, columns=cols)
    st.success("분석 완료!")

if 'df_ger' in st.session_state:
    df = st.session_state['df_ger']
    
    # 상단 메트릭
    c1, c2, c3 = st.columns(3)
    c1.metric("총 종목", f"{len(df)}개")
    c2.metric("매수 신호", f"{len(df[df['상태'].str.contains('|'.join(BUY_STATUS))])}개")
    c3.metric("주의/이탈", f"{len(df[df['상태'].str.contains('|'.join(SELL_STATUS))])}개")
    
    show_styled_dataframe(df)
