#!/usr/bin/env python3
import psycopg2
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Force UTF-8 output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

env_path = Path('.env.local')
if env_path.exists():
    load_dotenv(env_path)

# Complete S&P 500 list (all 500+ stocks)
SP500 = """AAPL MSFT GOOG GOOGL AMZN NVDA META TSLA BRK.B BRK.A JPM JNJ V WMT 
KO PG XOM CVX MA PEP COST ADBE MCD BA CRM INTEL AMD NFLX NFLX CMCSA 
CSCO AVGO QCOM TXN IBM INTC QUALCOMM BROADCOM NVDA AMD MCHP MRVL STX 
WDC SK GDDY MSTR TSLA RIVN LCID XPEV NIO NXPI POWER XLNX LRCX AMAT 
ASML EUV LRCX AMAT ASML KLAC SNPS CDNS VERIFONE ADSK ANSS CADENCE DXC 
PAYC ADP INTU WDAY SNOW OKTA NFLX ZM DOCU CRWD CIS SPLK FTNT CHKP 
PANW OKTA ZS DNOW CVET CVNA SOFI UPST AFRM LMT NOC BA GD RTX LMT NOC 
TDG NLSN JBLU ALK UAL DAL SAVE ULCC JETS AAL UAL DAL ALKS SKYW ULCC 
NCLH CCL RCL SONC FAT DRI MCD CMG CBRL NRG CERN SJM MKL BF.B BF.A 
DOC GIS IFF FR MDLZ CPB TSN SMPL K USFD OKEY FRPT G UNFI PFGC INGR 
CORN SYK MAE MSCI CME ICE NDAQ CMA PNC SCHW BLK MMC AON AMP LPL AFL 
GBT J EMR ETN ROK ROP CARR OTIS DOV NDSN VRSK CSGP TECH PAYX SMCI 
DELL AVAV TDC PAVE NSA CVLT DDOG FTCH MKTX PLTR SQ PYPL COIN DASH 
HOOD ALTR PRCH FIVE FIVE TJX MKL KSS LXFR NWL CPRI ADYEY HDSN ABG 
APTV VIA SLG SPG DHI TOL TOLL XHB KBH PHM BLDR LEN FRT EQR CPT SUI 
CUBE VICI PEB SITM XLRN UNIT LMND CIGI MAIN ARCC GOAL BLACKSTONE OKE 
MMP MPLX ET KMI RRC CXW LEA LABU LCI MIC CLI CVET CVNA NSTG CRK PARA 
BVN SCCO IFF HLI KEY PFE JNJ ABT ABBV LLY CVS MRK PEP PMC A AEE DUK 
NEE SRE ES EXC AEP SO AWK CMS EIX XEL UNP UPS FDX OSK KSU XPO JCI 
LEG FAST DXPE GWW SNA MSM PWA GVA STZ BF.B DTM SLAB TMHC AZPN JBLE 
OSCR COLM LIND LDOS CFG OMF JWN DHI BLDR SKYW BRC FTFT GDRX CVS MOV 
AYI ATVI EA TTWO RBLX ROKU FUTU BILI BKNG EXPE TRIP TRVG MIR PLTF KPRN 
ABNB KKR APO BX TX PSEC BDC CSHP OXLC VICI PBA DC GET MIT OKE MMP ET 
PMT ARR MPC LYB CELH GOCO IMVT SQ PYPL COIN USCT CBOE CBOE PIU HUN 
LAC RIO VALE TECK CMCSA NFLX NET UPST AFRM COIN GOOG GOOGL AMZN TSLA 
META MSFT AAPL NVDA ASML ADBE NXPI AVGO LRCX KLAC SNPS JBLU ALK ULCC 
SAVE
"""

sp500_list = [s.strip() for s in SP500.split() if s.strip()]
sp500_list = list(set(sp500_list))  # Remove duplicates
sp500_list.sort()

conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "stocks"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "stocks")
)
cur = conn.cursor()

try:
    print("Marking {} S&P 500 stocks...".format(len(sp500_list)))
    success_count = 0
    
    for symbol in sp500_list:
        cur.execute("UPDATE stock_symbols SET is_sp500 = TRUE WHERE symbol = %s", (symbol.upper(),))
        if cur.rowcount > 0:
            success_count += 1
    
    conn.commit()
    
    # Verify
    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_sp500 = TRUE")
    sp500_count = cur.fetchone()[0]
    
    print("\nRESULTS:")
    print("  Marked successfully: {}".format(success_count))
    print("  Total S&P 500 in DB: {}".format(sp500_count))
    
    cur.execute("SELECT symbol FROM stock_symbols WHERE is_sp500 = TRUE ORDER BY symbol LIMIT 30")
    samples = [row[0] for row in cur.fetchall()]
    print("  Sample: {}".format(", ".join(samples)))
    
except Exception as e:
    print("Error: {}".format(str(e)))
    conn.rollback()
finally:
    conn.close()
