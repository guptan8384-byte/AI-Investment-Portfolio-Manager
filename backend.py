
import requests, urllib.parse, gzip, json, pandas as pd, numpy as np
from datetime import datetime
from io import BytesIO
from xgboost import XGBRegressor
from pypfopt import EfficientFrontier, risk_models, expected_returns, HRPOpt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os, warnings, random

warnings.filterwarnings("ignore")

_cached_token = None

class APIConfig:
    CLIENT_ID = '543e49a1-de8d-4b61-b3ad-fdc7c39058f9'
    CLIENT_SECRET = 'n62ykvkckl'
    REDIRECT_URI = 'https://stocksprediction.com'
    BASE_URL = 'https://api.upstox.com/v2/'

def authenticate():
    global _cached_token
    if _cached_token:
        return _cached_token
    if os.path.exists("token.json"):
        with open("token.json", "r") as f:
            _cached_token = json.load(f).get("access_token")
            return _cached_token
    encoded = urllib.parse.quote(APIConfig.REDIRECT_URI, safe="")
    print("🔗 Visit this URL to authorize:")
    print(f"{APIConfig.BASE_URL}login/authorization/dialog?response_type=code&client_id={APIConfig.CLIENT_ID}&redirect_uri={encoded}")
    code = input("\n🔑 Enter the authorization code: ").strip()
    r = requests.post(
        f"{APIConfig.BASE_URL}login/authorization/token",
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'code': code,
            'client_id': APIConfig.CLIENT_ID,
            'client_secret': APIConfig.CLIENT_SECRET,
            'redirect_uri': APIConfig.REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
    )
    if r.status_code != 200:
        raise Exception("Authentication failed")
    with open("token.json", "w") as f:
        json.dump(r.json(), f)
    _cached_token = r.json()['access_token']
    return _cached_token

class DataHandler:
    def __init__(self, token):
        self.token = token
        self.instruments = self._load_instruments()

    def _load_instruments(self):
        r = requests.get("https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz")
        with gzip.GzipFile(fileobj=BytesIO(r.content)) as gz:
            df = pd.DataFrame(json.loads(gz.read().decode()))
        df = df[df['instrument_key'].str.startswith(('NSE_EQ|', 'BSE_EQ|'))]
        df = df[~df['name'].str.contains("TEST|PVT|BOND|ZC", case=False)]
        df['name'] = df['name'].str.strip().str.rstrip('.')
        return df.drop_duplicates('name')

    def get_historical_data(self, instrument_key, interval, from_date, to_date):
        url = f"{APIConfig.BASE_URL}historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        r = requests.get(url, headers={'Authorization': f'Bearer {self.token}'})
        if r.status_code == 200:
            candles = r.json()['data']['candles']
            return self._process_candles(candles)
        return None

    def _process_candles(self, candles):
        df = pd.DataFrame(candles, columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        df['datetime'] = pd.to_datetime(df['datetime'].str[:19])
        df.set_index('datetime', inplace=True)
        df['MA20'] = df['close'].rolling(20).mean()
        df['RSI'] = self._calculate_rsi(df['close'])
        df['volatility_10d'] = df['close'].pct_change().rolling(10).std()
        return df.ffill().dropna()

    def _calculate_rsi(self, series, window=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window).mean()
        avg_loss = loss.rolling(window).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

class ReturnPredictor:
    def __init__(self):
        self.model = XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.05)

    def create_features(self, df):
        features = pd.DataFrame(index=df.index)
        features['MA_ratio'] = df['MA20'] / df['close']
        features['RSI'] = df['RSI']
        features['volatility_10d'] = df['volatility_10d']
        features['day'] = df.index.dayofweek
        features['month'] = df.index.month
        return features.dropna()

    def train_predict(self, df):
        X = self.create_features(df)
        y = df['close'].pct_change().shift(-1)
        data = pd.concat([X, y], axis=1).dropna()
        if len(data) < 10:
            return -1
        split = int(len(data) * 0.8)
        self.model.fit(data.iloc[:split, :-1], data.iloc[:split, -1])
        return self.model.predict(data.iloc[split:, :-1])[-1]

def generate_unique_portfolios(token, investment, risk, goal):
    handler = DataHandler(token)
    predictor = ReturnPredictor()
    from_date = '2020-01-01'
    to_date = datetime.today().strftime('%Y-%m-%d')
    interval = 'day' if goal == 'short' else 'week'

    valid_stocks = {}
    for key, name in handler.instruments[['instrument_key', 'name']].values[:100]:
        try:
            df = handler.get_historical_data(key, interval, from_date, to_date)
            if df is not None and len(df) >= 100:
                pred = predictor.train_predict(df)
                if pred > 0:
                    valid_stocks[name] = {'returns': df['close'].pct_change().dropna(), 'predicted_return': pred}
        except:
            continue

    portfolios = []
    used_stocks = set()
    durations = {
        'short': ['1 month', '3 months', '6 months', '1 year'],
        'long': ['1.5 years', '2 years', '3 years', '5 years']
    }

    for i in range(5):
        available = list(set(valid_stocks.keys()) - used_stocks)
        if len(available) < 4:
            break
        selected = random.sample(available, min(len(available), random.randint(3, 6)))
        used_stocks.update(selected)

        sub_returns = pd.DataFrame({k: valid_stocks[k]['returns'] for k in selected}).dropna()
        sub_preds = pd.Series({k: valid_stocks[k]['predicted_return'] for k in selected})

        strategy_name = ""
        try:
            if i == 0:
                ef = EfficientFrontier(expected_returns.mean_historical_return(sub_returns),
                                       risk_models.sample_cov(sub_returns))
                ef.max_sharpe()
                weights = ef.clean_weights()
                strategy_name = "Max Sharpe Ratio"
            elif i == 1:
                ef = EfficientFrontier(expected_returns.mean_historical_return(sub_returns),
                                       risk_models.sample_cov(sub_returns))
                ef.min_volatility()
                weights = ef.clean_weights()
                strategy_name = "Minimum Volatility"
            elif i == 2:
                ef = EfficientFrontier(expected_returns.mean_historical_return(sub_returns),
                                       risk_models.sample_cov(sub_returns))
                ef.efficient_return(target_return=sub_preds.mean())
                weights = ef.clean_weights()
                strategy_name = "Target Return Strategy"
            elif i == 3:
                hrp = HRPOpt(sub_returns)
                weights = hrp.optimize()
                strategy_name = "Risk Parity (HRP)"
            else:
                rand_weights = np.random.dirichlet(np.ones(len(selected)), size=1)[0]
                weights = {s: float(w) for s, w in zip(selected, rand_weights)}
                strategy_name = "Random Diversified"
        except:
            rand_weights = np.random.dirichlet(np.ones(len(selected)), size=1)[0]
            weights = {s: float(w) for s, w in zip(selected, rand_weights)}
            strategy_name = "Random Fallback"

        alloc = pd.Series(weights).mul(investment)
        exp_ret = (sub_preds * pd.Series(weights)).sum()

        duration_label = random.choice(durations[goal])
        text = duration_label.lower()
        if 'month' in text:
            num = float(text.split()[0])
            years = num / 12
        elif 'week' in text:
            num = float(text.split()[0])
            years = num / 52
        elif 'day' in text:
            num = float(text.split()[0])
            years = num / 365
        elif 'half' in text and 'year' in text:
            years = 0.5
        else:
            years = float(text.split()[0])

        fv = round(investment * (1 + exp_ret) ** years, 2)
        profit = round(fv - investment, 2)

        os.makedirs("static", exist_ok=True)
        chart_filename = f"portfolio_{i+1}.png"
        chart_path = os.path.join("static", chart_filename)
        plt.figure(figsize=(6, 6))
        alloc.plot(kind='pie', autopct='%1.1f%%', startangle=90)
        plt.title("Portfolio Allocation")
        plt.ylabel('')
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()

        portfolios.append({
            'allocation': alloc.round(2).to_dict(),
            'expected_return_percent': round(((1 + exp_ret) ** (1/12) - 1) * 100, 2) if goal == 'short' else round(exp_ret * 100, 2),
            'investment': round(investment, 2),
            'future_value': fv,
            'net_profit': profit,
            'suggested_duration': duration_label,
            'return_period': 'monthly' if goal == 'short' else 'yearly',
            'chart_filename': chart_filename,
            'strategy': strategy_name
        })

    return portfolios
