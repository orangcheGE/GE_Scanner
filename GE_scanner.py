import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="글로벌 스마트 스캐너", layout="wide")

# --- 2. 데이터 로딩 함수 (Header 추가로 403 방지) ---
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
        st.error(f"❌ S&P 500 리스트 로딩 실패: {e}")
        return ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META']

@st.cache_data
def get_dax_tickers():
    return ['ADS.DE', 'AIR.DE', 'ALV.DE', 'BAS.DE', 'BAYN.DE', 'BEI.DE', 'BMW.DE', 'CON.DE', '1COV.DE', 'DTG.DE', 'DBK.DE', 'DB1.DE', 'LHA.DE', 'DPW.DE', 'DTE.DE', 'EOAN.DE', 'FRE.DE', 'FME.DE', 'HEI.DE', 'HEN3.DE', 'IFX.DE', 'MBG.DE', 'MRK.DE', 'MTX.DE', 'MUV2.DE', 'PUM.DE', 'RWE.DE', 'SAP.DE', 'SIE.DE', 'SY1.DE', 'VOW3.DE', 'VNA.DE']

# --- 3. 상세 분석 로직 ---
def analyze_stock(ticker):
    try:
        # 60일치 데이터를 가져옴
        data = yf.download(ticker, period="60d", interval="1d", progress=False)
        
        if data.empty:
            return None, f"{ticker}: 데이터 없음"
        if len(data) < 30:
            return None, f"{ticker}: 데이터 부족"
        
        # yfinance 최신 버전의 MultiIndex 대응
        if isinstance(data.columns, pd.MultiIndex):
            close = data['Close'][ticker]
        else:
            close = data['Close']
            
        # 지표 계산
        ma20 = close.rolling(window=20).mean()
        ma5 = close.rolling(window=5).mean()
        
        last_price = float(close.iloc[-1])
        last_ma20 = float(ma20.iloc[-1])
        last_ma5 = float(ma5.iloc[-1])
        prev_price = float(close.iloc[-2])
        prev_ma20 = float(ma20.iloc[-2])
        
        change = ((last_price - prev_price) / prev_price) * 100
        disparity = ((last_price / last_ma20) - 1) * 100
        
        # 상태 판별 로직
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

        # 차트 링크 생성
        chart_url = f"https://finance.yahoo.com/chart/{ticker}"
        
        return [ticker, round(change, 2), round(last_price, 2), round(last_ma20, 2), f"{round(disparity, 2)}%", status, trend, chart_url], None
    except Exception as e:
        return None, f"{ticker}: 시스템 에러 ({str(e)})"

# --- 4. 메인 UI ---
st.sidebar.title("🌍 글로벌 마켓 스캐너")
market = st.sidebar.radio("시장 선택", ["독일 (DAX)", "미국 (S&P 500)"])
full_list = get_dax_tickers() if market == "독일 (DAX)" else get_sp500_tickers()

items_per_page = 40
total_pages = (len(full_list) // items_per_page) + 1
page_num = st.sidebar.number_input(f"페이지 선택 (1-{total_pages})", min_value=1, max_value=total_pages, value=1)

start_idx = (page_num - 1) * items_per_page
target_tickers = full_list[start_idx : start_idx + items_per_page]

if st.sidebar.button("🚀 분석 시작"):
    results = []
    error_logs = []
    prog = st.progress(0)
    
    for i, t in enumerate(target_tickers):
        res, err = analyze_stock(t)
        if res: results.append(res)
        if err: error_logs.append(err)
        prog.progress((i + 1) / len(target_tickers))
    
    if results:
        df = pd.DataFrame(results, columns=['티커', '등락률', '현재가', '20MA', '이격률', '상태', '해석', '차트'])
        
        # 결과 표시 (차트 컬럼을 클릭 가능한 링크로 설정)
        st.dataframe(
            df, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "차트": st.column_config.LinkColumn("차트 보기", display_text="Open Chart 🔗")
            }
        )
    
    if error_logs:
        with st.expander("⚠️ 일부 종목 분석 실패 로그"):
            for log in error_logs: st.write(log)
            
    st.success(f"✅ {len(results)}개 종목 분석 완료!")
