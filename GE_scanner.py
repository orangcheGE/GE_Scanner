"""
🌍 글로벌 스마트 스캐너
미국 (S&P 500 / 나스닥 100 / 다우존스 30)
독일 (DAX 40)

데이터 소스 : yfinance (Yahoo Finance)
종목 목록   : Wikipedia 자동 파싱 + 하드코딩 폴백
지표        : 일목균형표 · MACD · CCI · RSI · BB · 거래량
신호        : 12단계 (한국 스캐너와 동일 로직)

실행: streamlit run global_scanner.py
필요 패키지: pip install streamlit yfinance pandas numpy
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# 하드코딩 폴백 종목 목록
# ─────────────────────────────────────────────

DOW30 = [
    ("AAPL","Apple"),("AMGN","Amgen"),("AXP","AmEx"),("BA","Boeing"),
    ("CAT","Caterpillar"),("CRM","Salesforce"),("CSCO","Cisco"),
    ("CVX","Chevron"),("DIS","Disney"),("DOW","Dow Inc"),
    ("GS","Goldman"),("HD","Home Depot"),("HON","Honeywell"),
    ("IBM","IBM"),("INTC","Intel"),("JNJ","J&J"),("JPM","JPMorgan"),
    ("KO","Coca-Cola"),("MCD","McDonald's"),("MMM","3M"),
    ("MRK","Merck"),("MSFT","Microsoft"),("NKE","Nike"),
    ("PG","P&G"),("TRV","Travelers"),("UNH","UnitedHealth"),
    ("V","Visa"),("VZ","Verizon"),("WBA","Walgreens"),("WMT","Walmart"),
]

DAX40 = [
    ("ADS.DE","Adidas"),("AIR.DE","Airbus"),("ALV.DE","Allianz"),
    ("BAS.DE","BASF"),("BAYN.DE","Bayer"),("BEI.DE","Beiersdorf"),
    ("BMW.DE","BMW"),("BNR.DE","Brenntag"),("CON.DE","Continental"),
    ("1COV.DE","Covestro"),("DHER.DE","Delivery Hero"),("DB1.DE","Deutsche Boerse"),
    ("DBK.DE","Deutsche Bank"),("DHL.DE","DHL Group"),("DTE.DE","Deutsche Telekom"),
    ("EOAN.DE","E.ON"),("FRE.DE","Fresenius"),("HNR1.DE","Hannover Re"),
    ("HEI.DE","HeidelbergMaterials"),("HEN3.DE","Henkel"),("IFX.DE","Infineon"),
    ("INL.DE","Inlining"),("LIN.DE","Linde"),("MBG.DE","Mercedes-Benz"),
    ("MRK.DE","Merck KGaA"),("MTX.DE","MTU Aero"),("MUV2.DE","Munich Re"),
    ("PAH3.DE","Porsche Holding"),("RHM.DE","Rheinmetall"),("RWE.DE","RWE"),
    ("SAP.DE","SAP"),("SHL.DE","Siemens Healthineers"),("SIE.DE","Siemens"),
    ("SRT3.DE","Sartorius"),("SY1.DE","Symrise"),("VNA.DE","Vonovia"),
    ("VOW3.DE","Volkswagen"),("ZAL.DE","Zalando"),
]

NASDAQ100_SAMPLE = [
    ("AAPL","Apple"),("MSFT","Microsoft"),("NVDA","Nvidia"),("AMZN","Amazon"),
    ("META","Meta"),("GOOGL","Alphabet A"),("GOOG","Alphabet C"),("TSLA","Tesla"),
    ("AVGO","Broadcom"),("COST","Costco"),("NFLX","Netflix"),("AMD","AMD"),
    ("ADBE","Adobe"),("QCOM","Qualcomm"),("INTC","Intel"),("TXN","Texas Instr"),
    ("AMAT","Applied Materials"),("INTU","Intuit"),("AMGN","Amgen"),("ISRG","Intuitive Surgical"),
    ("BKNG","Booking"),("VRTX","Vertex"),("REGN","Regeneron"),("MU","Micron"),
    ("LRCX","Lam Research"),("KLAC","KLA"),("MRVL","Marvell"),("SNPS","Synopsys"),
    ("CDNS","Cadence"),("PANW","Palo Alto"),("CRWD","CrowdStrike"),("MELI","MercadoLibre"),
    ("ADI","Analog Devices"),("ABNB","Airbnb"),("ORLY","O'Reilly"),("CSX","CSX"),
    ("PYPL","PayPal"),("PCAR","Paccar"),("MAR","Marriott"),("FTNT","Fortinet"),
    ("ADP","ADP"),("DXCM","Dexcom"),("ASML","ASML"),("TEAM","Atlassian"),
    ("MNST","Monster"),("CHTR","Charter"),("BIIB","Biogen"),("IDXX","IDEXX"),
    ("WDAY","Workday"),("CTAS","Cintas"),
]

INDICES = {
    "🇺🇸 S&P 500":    "sp500",
    "🇺🇸 나스닥 100":  "nasdaq100",
    "🇺🇸 다우존스 30": "dow30",
    "🇩🇪 DAX 40":     "dax40",
}
CURRENCY = {"sp500":"USD","nasdaq100":"USD","dow30":"USD","dax40":"EUR"}


# ─────────────────────────────────────────────
# 종목 목록 로드
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_tickers(index_key: str):
    """Wikipedia 파싱 → 실패 시 하드코딩 폴백"""
    try:
        if index_key == "sp500":
            df = pd.read_html(
                "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            )[0]
            return [{"ticker": r["Symbol"].replace(".","-"),
                     "name":   r["Security"],
                     "sector": r.get("GICS Sector","")}
                    for _, r in df.iterrows()]

        elif index_key == "dow30":
            tables = pd.read_html(
                "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
            )
            for t in tables:
                if "Symbol" in t.columns:
                    return [{"ticker": str(r["Symbol"]).strip(),
                             "name":   str(r.get("Company", r["Symbol"])).strip(),
                             "sector": str(r.get("Industry","")).strip()}
                            for _, r in t.iterrows()
                            if str(r["Symbol"]).isalpha()]

        elif index_key == "nasdaq100":
            tables = pd.read_html(
                "https://en.wikipedia.org/wiki/Nasdaq-100"
            )
            for t in tables:
                cols_low = {c.lower(): c for c in t.columns}
                if "ticker" in cols_low:
                    tc = cols_low["ticker"]
                    nc = cols_low.get("company", cols_low.get("name", tc))
                    return [{"ticker": str(r[tc]).strip(),
                             "name":   str(r[nc]).strip(),
                             "sector": ""}
                            for _, r in t.iterrows()
                            if str(r[tc]).isalpha()]

        elif index_key == "dax40":
            tables = pd.read_html("https://en.wikipedia.org/wiki/DAX")
            for t in tables:
                cols_low = {c.lower(): c for c in t.columns}
                if "ticker" in cols_low:
                    tc = cols_low["ticker"]
                    nc = cols_low.get("company", cols_low.get("name", tc))
                    rows = [{"ticker": str(r[tc]).strip(),
                             "name":   str(r[nc]).strip(),
                             "sector": ""}
                            for _, r in t.iterrows()
                            if str(r[tc]).endswith(".DE")]
                    if rows:
                        return rows
    except Exception:
        pass

    # 폴백
    fallback = {
        "dow30":    DOW30,
        "dax40":    DAX40,
        "nasdaq100":NASDAQ100_SAMPLE,
        "sp500":    DOW30,   # sp500 파싱 실패 시 다우 30개로 대체
    }
    return [{"ticker": t, "name": n, "sector": ""}
            for t, n in fallback.get(index_key, [])]


# ─────────────────────────────────────────────
# 지표 계산
# ─────────────────────────────────────────────

def calc_rsi(s: pd.Series, p=14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0);  l = -d.clip(upper=0)
    ag = g.ewm(com=p-1, min_periods=p).mean()
    al = l.ewm(com=p-1, min_periods=p).mean()
    return 100 - 100/(1 + ag/al.replace(0, np.nan))

def calc_cci(hi, lo, cl, p=20) -> pd.Series:
    tp  = (hi+lo+cl)/3
    ma  = tp.rolling(p).mean()
    mad = tp.rolling(p).apply(lambda x: np.abs(x-x.mean()).mean(), raw=True)
    return (tp-ma)/(0.015*mad.replace(0,np.nan))

def calc_bb(s: pd.Series, p=20, k=2.0):
    ma = s.rolling(p).mean()
    sd = s.rolling(p).std()
    return ma+k*sd, ma-k*sd, (2*k*sd/ma*100)

def bb_squeeze(bw: pd.Series):
    cur = bw.iloc[-1]; r = bw.iloc[-20:]
    if cur <= r.quantile(0.20): return "⚡수축", True
    if cur >= r.quantile(0.80): return "💥팽창", False
    return "➖보통", False


# ─────────────────────────────────────────────
# 12단계 신호
# ─────────────────────────────────────────────

def calc_signal(last, prev, ich, rsi_v, cci_now, cci_pv, disp):
    sc = 0; det = {}

    # ① 구름대
    if   '상향돌파' in ich: s= 3
    elif '하향이탈' in ich: s=-3
    elif '상승진입' in ich: s= 1
    elif '하락진입' in ich: s=-2
    else:                   s= 0
    sc+=s; det['구름대']=s

    # ② MACD
    hn=last['mh']; hp=prev['mh']; sl=hn-hp
    if   hn>0 and hp<=0: s= 2
    elif hn<0 and hp>=0: s=-2
    elif hn<0 and sl>0:  s= 1
    elif hn>0 and sl<0:  s=-1
    else:                s= 0
    sc+=s; det['MACD']=s

    # ③ CCI
    if   cci_pv<-100 and cci_now>=-100: s= 2
    elif cci_pv<   0 and cci_now>=   0: s= 1
    elif cci_pv>   0 and cci_now<=   0: s=-1
    elif cci_pv> 100 and cci_now<= 100: s=-2
    else:                               s= 0
    sc+=s; det['CCI']=s

    # ④ 이격률
    if   disp> 20: s=-3
    elif disp> 12: s=-2
    elif disp>  6: s=-1
    elif disp>=-3: s= 0
    elif disp>=-8: s= 1
    else:          s= 2
    sc+=s; det['이격률']=s

    # ⑤ 거래량
    vr = last.get('vr', np.nan)
    ht = (det['구름대']!=0 or abs(det['MACD'])>=1 or abs(det['CCI'])>=1)
    if not pd.isna(vr):
        if   vr>=1.5 and ht: s= 1
        elif vr< 0.5:        s=-1
        else:                s= 0
    else: s=0
    sc+=s; det['거래량']=s

    # 플래그
    ab  = '구름대 위'  in ich or '상향돌파' in ich
    bel = '구름대 아래' in ich or '하향이탈' in ich
    fe  = '하락진입'   in ich
    ins = '내부'       in ich
    cb_o= det['구름대']== 3;  cb_d=det['구름대']==-3
    mu  = det['MACD']  >= 1;  md  =det['MACD']  <=-1
    cu  = det['CCI']   >  0;  cd  =det['CCI']   < 0
    hid = disp>15;  mid= 6<disp<=15;  lod=disp<-10

    if fe:
        sig="⚠️ 구름대주의"
    elif sc>=7 and cb_o and mu and cu:
        sig="🔥 적극매수"
    elif sc>=4 and not hid and (cb_o or mu or cu) and sum([cb_o,mu,cu])>=2:
        sig="📈 매수관심"
    elif sc>=2 and disp<=6 and ht and not fe:
        sig="🌱 진입준비"
    elif bel and (mu or cu) and sc>=0:
        sig="🔄 바닥탐색"
    elif bel and md and cd:
        sig="🔻 하락가속"
    elif sc<=-5 and cb_d and md and cd:
        sig="🧊 적극매도"
    elif sc<=-3:
        sig="📉 매도관심"
    elif bel and lod:
        sig="🔽 추세하락"
    elif ab and hid:
        sig="🔼 추세상승"
    elif ab and mid and not ht:
        sig="🛡️ 홀딩유지"
    elif ins:
        sig="🌫️ 구름대내부"
    else:
        sig="⏸️ 관망"
    return sc, sig


# ─────────────────────────────────────────────
# 종목 분석
# ─────────────────────────────────────────────

def analyze(ticker, name, sector, currency):
    try:
        raw = yf.download(
            ticker, period="18mo", interval="1d",
            auto_adjust=True, progress=False, timeout=15
        )
        if raw is None or len(raw) < 80:
            return None

        # MultiIndex 처리
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.columns = [str(c).strip() for c in raw.columns]

        df = raw[['High','Low','Close','Volume']].copy()
        df.columns = ['H','L','C','V']
        df = df.dropna(subset=['C']).sort_index()

        # 이동평균
        df['ma5']  = df['C'].rolling(5).mean()
        df['ma20'] = df['C'].rolling(20).mean()
        df['ma60'] = df['C'].rolling(60).mean()

        # 일목균형표
        h9 =df['H'].rolling(9).max(); l9 =df['L'].rolling(9).min()
        h26=df['H'].rolling(26).max();l26 =df['L'].rolling(26).min()
        h52=df['H'].rolling(52).max();l52 =df['L'].rolling(52).min()
        tk=(h9+l9)/2; kj=(h26+l26)/2; sb=(h52+l52)/2
        sa_fut = ((tk+kj)/2).shift(26)
        sb_fut = sb.shift(26)
        df['sa']=sa_fut; df['sb']=sb_fut

        # MACD
        e12=df['C'].ewm(span=12,adjust=False).mean()
        e26=df['C'].ewm(span=26,adjust=False).mean()
        macd=e12-e26
        df['mh']=macd - macd.ewm(span=9,adjust=False).mean()

        # RSI / CCI / BB / Volume ratio
        df['RSI'] = calc_rsi(df['C'])
        df['CCI'] = calc_cci(df['H'],df['L'],df['C'])
        df['bbu'],df['bbl'],df['bbw'] = calc_bb(df['C'])
        df['vr']  = df['V'] / df['V'].rolling(20).mean()

        df_f = df.dropna(subset=['sa','sb','RSI','CCI','bbw','mh']).copy()
        if len(df_f) < 6:
            return None

        rows = [df_f.iloc[-i] for i in range(1,6)]
        last,prev,p2,p3,p4 = rows

        # 일목 상태
        def ct(r): return max(r['sa'],r['sb'])
        def cb(r): return min(r['sa'],r['sb'])
        an = last['C']>ct(last); bn=last['C']<cb(last)

        bkd=None
        if an:
            for d,r in enumerate([prev,p2,p3,p4],1):
                if r['C']<=ct(r): bkd=d; break
        bdd=None
        if bn:
            for d,r in enumerate([prev,p2,p3,p4],1):
                if r['C']>=cb(r): bdd=d; break

        if an:
            ich = f"🔥 상향돌파({bkd}일전)" if bkd else "📈 구름대 위"
        elif bn:
            ich = f"🧊 하향이탈({bdd}일전)" if bdd else "📉 구름대 아래"
        else:
            pr=[prev,p2,p3,p4]
            wa=any(r['C']>ct(r) for r in pr)
            wb=any(r['C']<cb(r) for r in pr)
            if wa and not wb:   ich="⚠️ 구름대하락진입"
            elif wb and not wa: ich="🌱 구름대상승진입"
            else:               ich="🌫️ 구름대 내부"

        # MA 크로스
        def mx(l,p,col):
            if p['C']<=p[col] and l['C']>l[col]: return "🔥GC"
            if p['C']>=p[col] and l['C']<l[col]: return "🧊DC"
            return "📈↑" if l['C']>l[col] else "📉↓"
        mat=f"5:{mx(last,prev,'ma5')} 20:{mx(last,prev,'ma20')} 60:{mx(last,prev,'ma60')}"

        # RSI 표시
        rv=round(last['RSI'],1)
        rd=(f"{rv} 🟢과매도" if rv<=30 else f"{rv} 🔵관심" if rv<=45 else
            f"{rv} ⚪중립"   if rv<=55 else f"{rv} 🟡주의"  if rv<=70 else
            f"{rv} 🔴과매수")

        # CCI 표시
        cn=last['CCI']; cp=prev['CCI']; cv=round(cn,1)
        if   cp<-100 and cn>=-100: cd=f"{cv} 🟢과매도탈출"
        elif cp<   0 and cn>=   0: cd=f"{cv} 🔵제로크로스"
        elif cp> 100 and cn<= 100: cd=f"{cv} 🟡과매수탈출"
        elif cp>   0 and cn<=   0: cd=f"{cv} 🔴제로데드"
        elif cn> 100:              cd=f"{cv} ⚡과매수"
        elif cn<-100:              cd=f"{cv} 💧과매도"
        else:                      cd=f"{cv} ➖중립"

        # BB
        bsq,_=bb_squeeze(df_f['bbw'])
        bp=("상단" if last['C']>=last['bbu'] else
            "하단" if last['C']<=last['bbl'] else "내부")
        bbd=f"{bsq}/{bp}"

        # 거래량
        vr=round(last['vr'],1) if not pd.isna(last['vr']) else 1.0
        vd=f"{vr}배 📈" if vr>=2 else f"{vr}배 📉" if vr<0.5 else f"{vr}배"

        # 이격률
        disp=((last['C']/last['ma20'])-1)*100 if last['ma20']>0 else 0
        df_=f"{'+' if disp>=0 else ''}{round(disp,2)}%"

        # 등락률
        chg=round(((last['C']-prev['C'])/prev['C'])*100,2)
        cf=f"{'+' if chg>=0 else ''}{chg}%"

        # 신호
        sc,sig=calc_signal(last,prev,ich,rv,cn,cp,disp)

        pf=round(last['C'],2)
        chart=f"https://finance.yahoo.com/chart/{ticker}"

        return [ticker,name,sector,cf,f"{pf} {currency}",df_,sc,sig,
                ich,mat,rd,cd,bbd,vd,chart]
    except Exception:
        return None


# ─────────────────────────────────────────────
# 스타일
# ─────────────────────────────────────────────

def sty_sig(v):
    v=str(v)
    if '적극매수'   in v: return 'color:white;background-color:#b71c1c;font-weight:bold'
    if '매수관심'   in v: return 'color:#ef5350;font-weight:bold'
    if '진입준비'   in v: return 'color:#ff8f00;font-weight:bold'
    if '바닥탐색'   in v: return 'color:#8d6e63;font-weight:bold'
    if '홀딩유지'   in v: return 'color:#2e7d32;font-weight:bold'
    if '추세상승'   in v: return 'color:#558b2f'
    if '구름대내부' in v: return 'color:#78909c'
    if '구름대주의' in v: return 'color:white;background-color:#e65100;font-weight:bold'
    if '하락가속'   in v: return 'color:white;background-color:#4a148c;font-weight:bold'
    if '추세하락'   in v: return 'color:#1565c0;font-weight:bold'
    if '매도관심'   in v: return 'color:#42a5f5;font-weight:bold'
    if '적극매도'   in v: return 'color:white;background-color:#0d47a1;font-weight:bold'
    return 'color:#9e9e9e'

def sty_ich(v):
    v=str(v)
    if '상향돌파' in v: return 'color:white;background-color:#c62828;font-weight:bold'
    if '하향이탈' in v: return 'color:white;background-color:#1565c0;font-weight:bold'
    if '하락진입' in v: return 'color:white;background-color:#e65100;font-weight:bold'
    if '상승진입' in v: return 'color:#ff8f00;font-weight:bold'
    if '구름대 위'   in v: return 'color:#ef5350'
    if '구름대 아래' in v: return 'color:#64b5f6'
    return 'color:#9e9e9e'

def sty_rsi(v):
    v=str(v)
    if '과매도' in v: return 'color:#43a047;font-weight:bold'
    if '🔵' in v:     return 'color:#1e88e5'
    if '과매수' in v: return 'color:#e53935;font-weight:bold'
    if '🟡' in v:     return 'color:#fb8c00'
    return ''

def sty_cci(v):
    v=str(v)
    if '과매도탈출' in v: return 'color:#43a047;font-weight:bold'
    if '제로크로스' in v: return 'color:#1e88e5;font-weight:bold'
    if '제로데드'   in v: return 'color:#e53935;font-weight:bold'
    if '과매수탈출' in v: return 'color:#fb8c00;font-weight:bold'
    if '과매수'     in v: return 'color:#e53935'
    if '과매도'     in v: return 'color:#43a047'
    return ''

def sty_sc(v):
    try:
        n=int(v)
        if n>= 5: return 'color:white;background-color:#c62828;font-weight:bold'
        if n>= 2: return 'color:#ef5350;font-weight:bold'
        if n>=-1: return 'color:#9e9e9e'
        if n>=-4: return 'color:#42a5f5;font-weight:bold'
        return 'color:white;background-color:#1565c0;font-weight:bold'
    except: return ''

def sty_pct(v):
    v=str(v)
    if v.startswith('+'): return 'color:#ef5350'
    if v.startswith('-'): return 'color:#42a5f5'
    return ''

COLS=['티커','종목명','섹터','등락률','현재가','이격률','총점','신호',
      '일목','MA크로스','RSI','CCI','BB','거래량','차트']

def show_df(df):
    if df.empty:
        st.info("데이터 없음"); return
    h=(len(df)+1)*35+3
    styled=(
        df.style
        .map(sty_sig, subset=['신호'])
        .map(sty_ich, subset=['일목'])
        .map(sty_rsi, subset=['RSI'])
        .map(sty_cci, subset=['CCI'])
        .map(sty_sc,  subset=['총점'])
        .map(sty_pct, subset=['등락률','이격률'])
        .map(lambda x:('color:#ef5350;font-weight:bold' if '🔥' in str(x) else
                       'color:#42a5f5;font-weight:bold' if '🧊' in str(x) else
                       'color:#ef5350' if '📈' in str(x) else
                       'color:#42a5f5' if '📉' in str(x) else ''),
             subset=['MA크로스'])
        .map(lambda x:('color:#ef9a00;font-weight:bold' if '⚡' in str(x) else
                       'color:#26a69a;font-weight:bold' if '💥' in str(x) else ''),
             subset=['BB'])
        .map(lambda x:('color:#ef5350' if '📈' in str(x) else
                       'color:#64b5f6' if '📉' in str(x) else ''),
             subset=['거래량'])
    )
    import streamlit as _st
    _st.dataframe(styled, use_container_width=True, height=h,
        column_config={
            "티커":   _st.column_config.TextColumn("티커",  width="small"),
            "종목명": _st.column_config.TextColumn("종목명",width="medium"),
            "섹터":   _st.column_config.TextColumn("섹터",  width="medium"),
            "등락률": _st.column_config.TextColumn("등락",  width="small"),
            "현재가": _st.column_config.TextColumn("현재가",width="small"),
            "이격률": _st.column_config.TextColumn("이격",  width="small"),
            "총점":   _st.column_config.NumberColumn("점수",width="small"),
            "신호":   _st.column_config.TextColumn("신호",  width="medium"),
            "일목":   _st.column_config.TextColumn("일목",  width="medium"),
            "MA크로스":_st.column_config.TextColumn("MA",   width="medium"),
            "RSI":    _st.column_config.TextColumn("RSI",   width="small"),
            "CCI":    _st.column_config.TextColumn("CCI",   width="medium"),
            "BB":     _st.column_config.TextColumn("BB",    width="small"),
            "거래량": _st.column_config.TextColumn("거래량",width="small"),
            "차트":   _st.column_config.LinkColumn("차트",  width="small",
                          display_text="📊"),
        }, hide_index=True)


# ─────────────────────────────────────────────
# 메트릭 / 필터
# ─────────────────────────────────────────────

def upd_metrics(df):
    bk='적극매수|매수관심'; fk='하락가속|추세하락|적극매도'; sk='매도관심|적극매도'
    m_tot.metric("전체",     f"{len(df)}개")
    m_buy.metric("매수계열", f"{len(df[df['신호'].str.contains(bk,regex=True)])}개")
    m_ent.metric("진입/바닥",f"{len(df[df['신호'].str.contains('진입준비|바닥탐색',regex=True)])}개")
    m_cau.metric("구름대주의",f"{len(df[df['신호'].str.contains('구름대주의')])}개")
    m_fal.metric("하락계열", f"{len(df[df['신호'].str.contains(fk,regex=True)])}개")
    m_sel.metric("매도관심↓",f"{len(df[df['신호'].str.contains(sk,regex=True)])}개")

def apf(df, f):
    fm={"매수":"적극매수|매수관심","진입준비":"진입준비","바닥탐색":"바닥탐색",
        "홀딩":"홀딩유지|추세상승","구름대주의":"구름대주의",
        "하락가속":"하락가속|추세하락","매도":"매도"}
    if f in fm: return df[df['신호'].str.contains(fm[f],regex=True)]
    return df


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────

st.set_page_config(page_title="🌍 글로벌 스마트 스캐너", layout="wide")
st.title("🌍 글로벌 스마트 스캐너")
st.caption("미국(S&P 500 / 나스닥 100 / 다우존스) · 독일(DAX 40) | 데이터: Yahoo Finance")

# 사이드바
st.sidebar.header("⚙️ 설정")
idx_lbl  = st.sidebar.selectbox("지수 선택", list(INDICES.keys()))
idx_key  = INDICES[idx_lbl]
curr     = CURRENCY[idx_key]

sec_f = ""
if idx_key == "sp500":
    st.sidebar.markdown("---")
    sec_f = st.sidebar.text_input("섹터 필터 (예: Technology)", placeholder="비워두면 전체")

st.sidebar.markdown("---")
max_n = st.sidebar.slider("최대 종목 수", 10, 500, 50, 10,
    help="S&P 500 전체(500개)는 약 8~10분")
n_wk  = st.sidebar.slider("병렬 다운로드", 1, 10, 5,
    help="높을수록 빠르나 Yahoo 차단 위험↑")

st.sidebar.markdown("---")
st.sidebar.markdown("""
**📊 12단계 신호**

**매수** 🔥적극매수 📈매수관심 🌱진입준비 🔄바닥탐색

**보유** 🛡️홀딩유지 🔼추세상승 🌫️구름대내부 ⏸️관망

**하락** ⚠️구름대주의 🔻하락가속 🔽추세하락 📉매도관심 🧊적극매도

**점수 구성**
- 구름대 ±3 · MACD ±2 · CCI ±2
- 이격률 ±3 · 거래량 ±1
""")
go = st.sidebar.button("🚀 분석 시작", use_container_width=True)

# 메트릭
st.subheader("📊 진단 현황")
c1,c2,c3,c4,c5,c6 = st.columns(6)
m_tot=c1.empty(); m_buy=c2.empty(); m_ent=c3.empty()
m_cau=c4.empty(); m_fal=c5.empty(); m_sel=c6.empty()
for m,l in [(m_tot,"전체"),(m_buy,"매수계열"),(m_ent,"진입/바닥"),
            (m_cau,"구름대주의"),(m_fal,"하락계열"),(m_sel,"매도관심↓")]:
    m.metric(l,"0개")

# 필터 버튼
fb=st.columns(8)
if 'gf' not in st.session_state: st.session_state.gf="전체"
for col,lbl,key in zip(fb,
    ["🔄전체","🔥📈매수","🌱진입준비","🔄바닥탐색","🛡️홀딩","⚠️구름주의","🔻하락가속","📉🧊매도"],
    ["전체","매수","진입준비","바닥탐색","홀딩","구름대주의","하락가속","매도"]):
    if col.button(lbl, use_container_width=True): st.session_state.gf=key

st.markdown("---")
rt=st.empty(); ra=st.empty()

# 분석 실행
if go:
    st.session_state.gf="전체"
    st.session_state['gd']=pd.DataFrame()

    with st.spinner(f"{idx_lbl} 종목 목록 로드 중..."):
        tlist=load_tickers(idx_key)

    if not tlist:
        st.error("종목 목록 로드 실패"); st.stop()

    if sec_f:
        tlist=[t for t in tlist if sec_f.lower() in t.get('sector','').lower()]
    tlist=tlist[:max_n]

    tot=len(tlist)
    st.info(f"▶ {idx_lbl} | {tot}개 분석 시작 (병렬 {n_wk}개)")

    results=[]; pb=st.progress(0,"준비 중..."); done=0

    with ThreadPoolExecutor(max_workers=n_wk) as ex:
        futs={ex.submit(analyze,t['ticker'],t['name'],t.get('sector',''),curr):t
              for t in tlist}
        for fut in as_completed(futs):
            item=futs[fut]; done+=1
            try: res=fut.result()
            except: res=None
            if res:
                results.append(res)
                df_all=pd.DataFrame(results,columns=COLS)
                df_all=df_all.sort_values('총점',ascending=False).reset_index(drop=True)
                st.session_state['gd']=df_all
                upd_metrics(df_all)
                dd=apf(df_all,st.session_state.gf)
                rt.subheader(f"🔍 {idx_lbl} 결과 ({st.session_state.gf} / {len(dd)}개)")
                with ra: show_df(dd)
            pb.progress(done/tot, text=f"분석 중: {item['ticker']} ({done}/{tot})")

    pb.empty()
    st.success(f"✅ 완료! {len(results)}개 종목 분석됨")

# 필터 버튼 동작
if not go and 'gd' in st.session_state:
    df=st.session_state['gd']
    if not df.empty:
        upd_metrics(df)
        dd=apf(df,st.session_state.gf)
        rt.subheader(f"🔍 결과 ({st.session_state.gf} / {len(dd)}개)")
        with ra: show_df(dd)
        if not dd.empty:
            sm=dd[['티커','종목명','현재가','총점','신호','일목','RSI']].to_string(index=False)
            bd=urllib.parse.quote(f"글로벌 주식 분석 리포트\n\n{sm}")
            ml=f"mailto:?subject=글로벌주식리포트&body={bd}"
            st.markdown(
                f'<a href="{ml}" target="_self" style="text-decoration:none;">'
                f'<div style="background:#0078d4;color:white;padding:12px;'
                f'border-radius:8px;text-align:center;font-weight:bold;">'
                f'📧 현재 리스트 Outlook 전송</div></a>',
                unsafe_allow_html=True)

elif 'gd' not in st.session_state:
    with ra: st.info("왼쪽에서 지수를 선택하고 '분석 시작'을 눌러주세요.")
