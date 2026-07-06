import yfinance as yf
import requests
import datetime
import ta
import pandas as pd

MAJOR_PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CHF": "CHF=X",
    "USD/CAD": "CAD=X",
    "AUD/USD": "AUDUSD=X",
    "NZD/USD": "NZDUSD=X",
    "Gold":    "GC=F"
}

def get_pair_data(ticker: str) -> dict:
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="5d", interval="1h")
        if hist.empty:
            return None

        current = round(hist['Close'].iloc[-1], 5)
        open_price = round(hist['Open'].iloc[0], 5)
        pip_change = round((current - open_price) * 10000, 1)
        pct_change = round(((current - open_price) / open_price) * 100, 2)

        # RSI
        rsi = ta.momentum.RSIIndicator(hist['Close'], window=14)
        rsi_val = round(rsi.rsi().iloc[-1], 1)

        # trend
        if pct_change > 0.1:
            trend = "Bullish"
        elif pct_change < -0.1:
            trend = "Bearish"
        else:
            trend = "Neutral"

        return {
            "price": current,
            "pip_change": pip_change,
            "pct_change": pct_change,
            "rsi": rsi_val,
            "trend": trend
        }
    except Exception as e:
        print(f"[AURA Forex] Error fetching {ticker}: {e}")
        return None

def get_economic_calendar() -> list:
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=5)
        events = response.json()

        today = datetime.datetime.now().strftime("%m-%d-%Y")
        today_events = [e for e in events if e.get('date', '').startswith(today)]

        # filter high impact only
        high_impact = [e for e in today_events if e.get('impact') in ['High', 'Medium']]
        return high_impact[:8]
    except Exception as e:
        print(f"[AURA Forex] Calendar error: {e}")
        return []

def generate_report() -> str:
    report = f"AURA Forex Report — {datetime.datetime.now().strftime('%d %b %Y %I:%M %p')}\n"
    report += "─" * 45 + "\n"
    report += "LIVE MAJORS\n"

    for name, ticker in MAJOR_PAIRS.items():
        data = get_pair_data(ticker)
        if data:
            sign = "+" if data['pip_change'] > 0 else ""
            report += f"{name:<10} {data['price']:<10} "
            report += f"{sign}{data['pip_change']} pips  "
            report += f"RSI:{data['rsi']}  {data['trend']}\n"

    report += "\nTODAY'S HIGH IMPACT EVENTS\n"
    events = get_economic_calendar()
    if events:
        for e in events:
            time_str = e.get('time', 'All Day')
            currency = e.get('currency', '')
            title = e.get('title', '')
            forecast = e.get('forecast', '—')
            actual = e.get('actual', 'Pending')
            report += f"{time_str:<10} {currency:<5} {title}\n"
            report += f"           Forecast: {forecast}  Actual: {actual}\n"
    else:
        report += "No high impact events today\n"

    report += "─" * 45 + "\n"
    report += "[Data only — no trade advice]"
    return report

def get_quick_price(pair: str) -> str:
    # Normalize the user's query ("what's EUR/USD at" → "whatseurusdat") and
    # check whether the PAIR token appears in the QUERY — the old test was
    # reversed (query-in-pair) and never matched.
    query = pair.lower().replace("/", "").replace(" ", "").replace("-", "")
    for name, ticker in MAJOR_PAIRS.items():
        token = name.lower().replace("/", "")
        if token in query:
            data = get_pair_data(ticker)
            if data:
                sign = "+" if data['pip_change'] > 0 else ""
                return f"{name} is at {data['price']}, {sign}{data['pip_change']} pips today. RSI is {data['rsi']}, trend is {data['trend']}."
    return f"Couldn't fetch data for {pair}."