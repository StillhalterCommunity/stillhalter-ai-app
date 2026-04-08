"""
Scan-Universen: Watchlist, S&P 500, Nasdaq 100
Statische Listen (Stand Q1 2026) + optionaler Live-Fetch aus Wikipedia.
"""
from typing import List, Dict

# ── Nasdaq 100 (101 Komponenten, Stand 2026) ──────────────────────────────────
NASDAQ_100: List[str] = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","AVGO","TSLA","COST",
    "NFLX","AMD","ADBE","QCOM","INTU","CSCO","TXN","AMGN","HON","ISRG",
    "AMAT","BKNG","ADI","VRTX","MU","PANW","REGN","LRCX","KLAC","SNPS",
    "CDNS","MDLZ","MAR","FTNT","KDP","ABNB","ORLY","PAYX","MRVL","CEG",
    "CTAS","DXCM","IDXX","MELI","MNST","ODFL","ON","PCAR","ROP","ROST",
    "SBUX","TTD","WDAY","XEL","CHTR","CMCSA","CRWD","DLTR","EA","EXC",
    "FAST","GEHC","ILMN","KHC","MRNA","NXPI","PYPL","TMUS","VRSK","AEP",
    "ALGN","AZN","BIIB","BKR","CDW","CPRT","CSX","CTSH","DDOG","EBAY",
    "FANG","FSLR","GILD","LULU","MSTR","NTES","NVAX","OKTA","PLTR","RIVN",
    "ROKU","ZM","ENPH","SMCI","WBD","CSGP","GFS","CCEP","SIRI","TEAM","ZS",
]

# ── S&P 500 (Auswahl ~400 liquider Komponenten, Stand 2026) ───────────────────
SP500: List[str] = [
    # Technologie
    "AAPL","MSFT","NVDA","AVGO","ORCL","CRM","ADBE","QCOM","TXN","AMD",
    "INTU","CSCO","ACN","IBM","AMAT","LRCX","KLAC","SNPS","CDNS","ADI",
    "MU","HPQ","STX","WDC","INTC","MCHP","NXPI","ON","TER","ENPH",
    "FSLR","GEN","IT","JNPR","KEYS","LDOS","MPWR","MSI","NTAP","PANW",
    "PYPL","SMCI","SWKS","VRSN","WU","ZBRA","FTNT","CRWD","NOW","TEAM",
    "OKTA","ZS","DDOG","SNOW","PLTR","ARM","ALAB","MRVL",
    # Gesundheit
    "LLY","UNH","JNJ","ABT","MRK","ABBV","TMO","AMGN","ISRG","MDT",
    "DHR","VRTX","REGN","GILD","BMY","SYK","EW","ZTS","BIIB","ILMN",
    "A","BAX","BDX","BSX","CAH","CI","CVS","DVA","DGX","DXCM",
    "HCA","HOLX","HSIC","HUM","IQV","LH","MCK","MOH","MTD","RMD",
    "UHS","VTRS","WAT","XRAY","IDXX","MRNA","NVAX","GEHC","ELV","CNC",
    # Finanzen
    "JPM","BAC","WFC","MS","GS","C","USB","PNC","TFC","COF",
    "AXP","V","MA","SPGI","MCO","BLK","SCHW","CME","ICE","CB",
    "AON","MMC","PRU","MET","AFL","ALL","AIG","BK","BRK-B","CINF",
    "CMA","FITB","HBAN","HIG","KEY","L","LNC","MTB","NTRS","PFG",
    "RF","RJF","SFM","STT","SYF","TROW","UNM","ZION","IBKR","HOOD",
    "KKR","BX","COIN","PYPL","GPN","FIS","FISV","FLT","SQ","WEX",
    # Konsumgüter (Staples)
    "PG","KO","PEP","MO","PM","MDLZ","CL","KMB","CHD","MKC",
    "CLX","GIS","HRL","CPB","K","SJM","TSN","WMT","TGT","COST",
    "KR","SYY","USFD","CVGW","DOLE","CASY","BJ","GO","FIVE","DLTR",
    "DG","TJX","ROST","ULTA","BBWI","NKE","VFC","RL","ANF","AEO",
    "SBUX","MCD","YUM","DPZ","QSR","SHAK","WING","TXRH","EAT","DRI",
    # Energie
    "XOM","CVX","COP","SLB","HAL","BKR","OXY","EOG","MPC","VLO",
    "PSX","PXD","APA","DVN","CTRA","FANG","HES","MRO","OKE","WMB",
    "KMI","ET","EPD","MPLX","LNG","ENPH","NEE","CEG","VST","TTE",
    "SHEL","BP","SU","PBR","TRP","ENB","CNQ","IMO","CVE","AR",
    # Industrie
    "GE","HON","CAT","DE","BA","RTX","LMT","GD","NOC","L3H",
    "EMR","ETN","PH","ITW","ROK","SNA","SWK","TDG","TT","CARR",
    "OTIS","FAST","GWW","CMI","PCAR","UPS","FDX","CSX","NSC","UNP",
    "WAB","LUV","DAL","UAL","AAL","ALK","JBLU","SAVE","EXPD","XPO",
    "SAIA","ODFL","CHRW","GXO","MAS","MLM","VMC","NUE","STLD","RS",
    "DOV","RRX","IEX","AWK","CTAS","CPRT","VRSK","HUBB","AOS","FTV",
    # Immobilien (REITs)
    "PLD","AMT","EQIX","SPG","CCI","DLR","PSA","EQR","AVB","VTR",
    "WELL","ARE","BXP","KIM","O","VICI","WPC","NNN","STAG","COLD",
    "EXR","CUBE","LSI","NSA","REXR","IRM","SUI","ELS","UDR","CPT",
    # Telekommunikation / Kommunikation
    "META","GOOGL","GOOG","NFLX","DIS","CMCSA","TMUS","VZ","T","CHTR",
    "WBD","FOX","NWS","FOXA","NWSA","LYV","EA","TTWO","ATVI","MTCH",
    "PINS","SNAP","RDDT","SPOT","ROKU","ZM","NTES","BIDU","BABA",
    # Verbrauchsgüter (Discretionary)
    "AMZN","TSLA","HD","LOW","BKNG","ABNB","MAR","HLT","IHG","WH",
    "CCL","RCL","NCLH","MGM","LVS","WYNN","CZR","PHM","LEN","DHI",
    "NVR","TOL","BZH","LGIH","MDC","UBER","LYFT","DASH","ABNB","SHOP",
    "EBAY","ETSY","W","CVNA","KMX","AN","GPC","AZO","ORLY","AAP",
    # Versorger
    "NEE","DUK","SO","D","EXC","XEL","AEP","ED","EIX","PEG",
    "WEC","ES","ETR","FE","AES","CMS","LNT","NI","OGE","POR",
    "SRE","AWK","WTR","ARTNA","SJW","MSEX","YORW","CEG","VST","NRG",
    # Grundstoffe
    "LIN","APD","EMN","DOW","DD","CE","FMC","ALB","SQM","LTHM",
    "MP","LAC","SYM","NEM","AEM","AUY","KGC","FNV","WPM","RGLD",
    "FCX","SCCO","AA","NUE","STLD","X","CLF","AKS","MT","RIO","BHP",
    "VALE","GLD","SLV","OXY","DVN","OVV","WRK","PKG","IP","GPK",
]

# Duplikate entfernen + sortieren
SP500 = sorted(list(dict.fromkeys(SP500)))


def get_universe_tickers(universe: str) -> List[str]:
    """
    Gibt Ticker-Liste für ein Universum zurück.
    universe: "Watchlist (225)", "S&P 500 (~400)", "Nasdaq 100 (101)"
    """
    from data.watchlist import ALL_TICKERS

    if universe.startswith("Nasdaq"):
        return NASDAQ_100
    elif universe.startswith("S&P"):
        return SP500
    else:
        return ALL_TICKERS


UNIVERSE_OPTIONS = [
    "Watchlist — 10WC & Masterclass (225)",
    "S&P 500 (~400 Komponenten)",
    "Nasdaq 100 (101 Komponenten)",
]

UNIVERSE_COUNTS = {
    "Watchlist — 10WC & Masterclass (225)": 225,
    "S&P 500 (~400 Komponenten)":           len(SP500),
    "Nasdaq 100 (101 Komponenten)":          len(NASDAQ_100),
}
