import requests
import urllib.parse
import gzip
import json
import pandas as pd
import numpy as np
from datetime import datetime
from io import BytesIO
import os
import warnings
import random

warnings.filterwarnings("ignore")

_cached_token = None


class APIConfig:
    CLIENT_ID = os.environ.get("UPSTOX_CLIENT_ID")
    CLIENT_SECRET = os.environ.get("UPSTOX_CLIENT_SECRET")
    REDIRECT_URI = os.environ.get("UPSTOX_REDIRECT_URI")
    BASE_URL = "https://api.upstox.com/v2/"


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
    print(
        f"{APIConfig.BASE_URL}login/authorization/dialog?"
        f"response_type=code&client_id={APIConfig.CLIENT_ID}"
        f"&redirect_uri={encoded}"
    )

    code = input("\n🔑 Enter the authorization code: ").strip()

    r = requests.post(
        f"{APIConfig.BASE_URL}login/authorization/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "code": code,
            "client_id": APIConfig.CLIENT_ID,
            "client_secret": APIConfig.CLIENT_SECRET,
            "redirect_uri": APIConfig.REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )

    if r.status_code != 200:
        raise Exception("Authentication failed")

    with open("token.json", "w") as f:
        json.dump(r.json(), f)

    _cached_token = r.json()["access_token"]
    return _cached_token


class DataHandler:
    def __init__(self, token):
        self.token = token
        self.instruments = self._load_instruments()

    def _load_instruments(self):
        r = requests.get(
            "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        )

        with gzip.GzipFile(fileobj=BytesIO(r.content)) as gz:
            df = pd.DataFrame(json.loads(gz.read().decode()))

        df = df[
            df["instrument_key"].str.startswith(("NSE_EQ|", "BSE_EQ|"))
        ]
        df = df[
            ~df["name"].str.contains(
                "TEST|PVT|BOND|ZC",
                case=False,
                na=False,
            )
        ]
        df["name"] = df["name"].str.strip().str.rstrip(".")

        return df.drop_duplicates("name")

    def get_historical_data(
        self,
        instrument_key,
        interval,
        from_date,
        to_date,
    ):
        url = (
            f"{APIConfig.BASE_URL}historical-candle/"
            f"{instrument_key}/{interval}/{to_date}/{from_date}"
        )

        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
        )

        if r.status_code == 200:
            candles = r.json()["data"]["candles"]
            return self._process_candles(candles)

        return None

    def _process_candles(self, candles):
        df = pd.DataFrame(
            candles,
            columns=[
                "datetime",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
            ],
        )

        df["datetime"] = pd.to_datetime(df["datetime"].str[:19])
        df.set_index("datetime", inplace=True)

        df["MA20"] = df["close"].rolling(20).mean()
        df["RSI"] = self._calculate_rsi(df["close"])
        df["volatility_10d"] = (
            df["close"].pct_change().rolling(10).std()
        )

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
        self.model = None

    def create_features(self, df):
        features = pd.DataFrame(index=df.index)

        features["MA_ratio"] = df["MA20"] / df["close"]
        features["RSI"] = df["RSI"]
        features["volatility_10d"] = df["volatility_10d"]
        features["day"] = df.index.dayofweek
        features["month"] = df.index.month

        return features.dropna()

    def train_predict(self, df):
        X = self.create_features(df)
        y = df["close"].pct_change().shift(-1)

        data = pd.concat([X, y], axis=1).dropna()

        if len(data) < 10:
            return -1

        split = int(len(data) * 0.8)

        X_train = data.iloc[:split, :-1].to_numpy(dtype=float)
        y_train = data.iloc[:split, -1].to_numpy(dtype=float)

        X_test = data.iloc[split:, :-1].to_numpy(dtype=float)

        if len(X_test) == 0:
            return -1

        # Standardize features
        mean = X_train.mean(axis=0)
        std = X_train.std(axis=0)
        std[std == 0] = 1

        X_train_scaled = (X_train - mean) / std
        X_test_scaled = (X_test - mean) / std

        # Add intercept
        X_train_scaled = np.column_stack(
            [np.ones(len(X_train_scaled)), X_train_scaled]
        )

        X_test_scaled = np.column_stack(
            [np.ones(len(X_test_scaled)), X_test_scaled]
        )

        # Lightweight Ridge Regression
        identity = np.eye(X_train_scaled.shape[1])
        identity[0, 0] = 0

        try:
            coefficients = np.linalg.solve(
                X_train_scaled.T @ X_train_scaled
                + 0.01 * identity,
                X_train_scaled.T @ y_train,
            )
        except np.linalg.LinAlgError:
            coefficients = np.linalg.lstsq(
                X_train_scaled,
                y_train,
                rcond=None,
            )[0]

        predictions = X_test_scaled @ coefficients

        return float(predictions[-1])


def generate_unique_portfolios(token, investment, risk, goal):
    handler = DataHandler(token)
    predictor = ReturnPredictor()

    from_date = "2020-01-01"
    to_date = datetime.today().strftime("%Y-%m-%d")
    interval = "day" if goal == "short" else "week"

    valid_stocks = {}

    for key, name in handler.instruments[
        ["instrument_key", "name"]
    ].values[:100]:
        try:
            df = handler.get_historical_data(
                key,
                interval,
                from_date,
                to_date,
            )

            if df is not None and len(df) >= 100:
                pred = predictor.train_predict(df)

                if pred > 0:
                    valid_stocks[name] = {
                        "returns": df["close"].pct_change().dropna(),
                        "predicted_return": pred,
                    }

        except Exception:
            continue

    portfolios = []
    used_stocks = set()

    durations = {
        "short": [
            "1 month",
            "3 months",
            "6 months",
            "1 year",
        ],
        "long": [
            "1.5 years",
            "2 years",
            "3 years",
            "5 years",
        ],
    }

    for i in range(5):
        available = list(set(valid_stocks.keys()) - used_stocks)

        if len(available) < 4:
            break

        selected = random.sample(
            available,
            min(len(available), random.randint(3, 6)),
        )

        used_stocks.update(selected)

        sub_returns = pd.DataFrame(
            {
                k: valid_stocks[k]["returns"]
                for k in selected
            }
        ).dropna()

        sub_preds = pd.Series(
            {
                k: valid_stocks[k]["predicted_return"]
                for k in selected
            }
        )

        strategy_name = ""

        try:
            if i == 0:
                # Max Sharpe Ratio
                mean_returns = sub_returns.mean().to_numpy()
                covariance = sub_returns.cov().to_numpy()

                inverse_cov = np.linalg.pinv(
                    covariance
                    + np.eye(len(selected)) * 1e-8
                )

                raw_weights = inverse_cov @ mean_returns
                raw_weights = np.maximum(raw_weights, 0)

                if raw_weights.sum() == 0:
                    raw_weights = np.ones(len(selected))

                raw_weights = raw_weights / raw_weights.sum()

                weights = {
                    s: float(w)
                    for s, w in zip(selected, raw_weights)
                }

                strategy_name = "Max Sharpe Ratio"

            elif i == 1:
                # Minimum Volatility
                covariance = sub_returns.cov().to_numpy()

                inverse_cov = np.linalg.pinv(
                    covariance
                    + np.eye(len(selected)) * 1e-8
                )

                raw_weights = inverse_cov @ np.ones(len(selected))
                raw_weights = np.maximum(raw_weights, 0)

                if raw_weights.sum() == 0:
                    raw_weights = np.ones(len(selected))

                raw_weights = raw_weights / raw_weights.sum()

                weights = {
                    s: float(w)
                    for s, w in zip(selected, raw_weights)
                }

                strategy_name = "Minimum Volatility"

            elif i == 2:
                # Target Return Strategy
                target_return = float(sub_preds.mean())

                best_weights = None
                best_volatility = float("inf")

                covariance = sub_returns.cov().to_numpy()

                for _ in range(2000):
                    candidate = np.random.dirichlet(
                        np.ones(len(selected))
                    )

                    predicted_return = float(
                        np.dot(
                            candidate,
                            sub_preds.to_numpy(),
                        )
                    )

                    volatility = float(
                        np.sqrt(
                            max(
                                candidate
                                @ covariance
                                @ candidate,
                                0,
                            )
                        )
                    )

                    if (
                        predicted_return >= target_return
                        and volatility < best_volatility
                    ):
                        best_weights = candidate
                        best_volatility = volatility

                if best_weights is None:
                    best_weights = (
                        np.ones(len(selected))
                        / len(selected)
                    )

                weights = {
                    s: float(w)
                    for s, w in zip(
                        selected,
                        best_weights,
                    )
                }

                strategy_name = "Target Return Strategy"

            elif i == 3:
                # Risk Parity approximation
                volatility = sub_returns.std().to_numpy()
                volatility[volatility <= 0] = 1e-8

                raw_weights = 1 / volatility
                raw_weights = (
                    raw_weights / raw_weights.sum()
                )

                weights = {
                    s: float(w)
                    for s, w in zip(
                        selected,
                        raw_weights,
                    )
                }

                strategy_name = "Risk Parity (HRP)"

            else:
                # Random Diversified
                rand_weights = np.random.dirichlet(
                    np.ones(len(selected))
                )

                weights = {
                    s: float(w)
                    for s, w in zip(
                        selected,
                        rand_weights,
                    )
                }

                strategy_name = "Random Diversified"

        except Exception:
            rand_weights = np.random.dirichlet(
                np.ones(len(selected))
            )

            weights = {
                s: float(w)
                for s, w in zip(
                    selected,
                    rand_weights,
                )
            }

            strategy_name = "Random Fallback"

        alloc = pd.Series(weights).mul(investment)
        exp_ret = (
            sub_preds * pd.Series(weights)
        ).sum()

        duration_label = random.choice(
            durations[goal]
        )

        text = duration_label.lower()

        if "month" in text:
            num = float(text.split()[0])
            years = num / 12

        elif "week" in text:
            num = float(text.split()[0])
            years = num / 52

        elif "day" in text:
            num = float(text.split()[0])
            years = num / 365

        elif "half" in text and "year" in text:
            years = 0.5

        else:
            years = float(text.split()[0])

        fv = round(
            investment * (1 + exp_ret) ** years,
            2,
        )

        profit = round(
            fv - investment,
            2,
        )

        portfolios.append(
            {
                "allocation": alloc.round(2).to_dict(),
                "expected_return_percent": (
                    round(
                        ((1 + exp_ret) ** (1 / 12) - 1)
                        * 100,
                        2,
                    )
                    if goal == "short"
                    else round(exp_ret * 100, 2)
                ),
                "investment": round(investment, 2),
                "future_value": fv,
                "net_profit": profit,
                "suggested_duration": duration_label,
                "return_period": (
                    "monthly"
                    if goal == "short"
                    else "yearly"
                ),
                "strategy": strategy_name,
            }
        )

    return portfolios
