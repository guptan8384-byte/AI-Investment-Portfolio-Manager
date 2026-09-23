import requests
import pandas as pd
import numpy as np
from datetime import datetime
import random
import time
import warnings

warnings.filterwarnings("ignore")


# =========================================================
# YAHOO FINANCE MARKET DATA
# =========================================================

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"

# Curated NSE stocks for the demo.
# Yahoo Finance uses .NS for NSE-listed stocks.
STOCKS = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank",
    "INFY.NS": "Infosys",
    "ICICIBANK.NS": "ICICI Bank",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "ITC.NS": "ITC",
    "SBIN.NS": "State Bank of India",
    "BHARTIARTL.NS": "Bharti Airtel",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "LT.NS": "Larsen & Toubro",
    "AXISBANK.NS": "Axis Bank",
    "MARUTI.NS": "Maruti Suzuki",
    "SUNPHARMA.NS": "Sun Pharmaceutical",
    "TITAN.NS": "Titan Company",
    "BAJFINANCE.NS": "Bajaj Finance",
    "ASIANPAINT.NS": "Asian Paints",
    "HCLTECH.NS": "HCL Technologies",
    "WIPRO.NS": "Wipro",
    "ULTRACEMCO.NS": "UltraTech Cement",
    "NTPC.NS": "NTPC",
    "POWERGRID.NS": "Power Grid Corporation",
    "ONGC.NS": "ONGC",
    "TATASTEEL.NS": "Tata Steel",
    "TECHM.NS": "Tech Mahindra",
    "ADANIENT.NS": "Adani Enterprises",
    "ADANIPORTS.NS": "Adani Ports",
    "COALINDIA.NS": "Coal India",
    "JSWSTEEL.NS": "JSW Steel",
    "HINDALCO.NS": "Hindalco Industries",
    "BAJAJFINSV.NS": "Bajaj Finserv",
    "M&M.NS": "Mahindra & Mahindra",
    "TATAMOTORS.NS": "Tata Motors",
    "DRREDDY.NS": "Dr. Reddy's Laboratories",
    "CIPLA.NS": "Cipla",
    "EICHERMOT.NS": "Eicher Motors",
    "DIVISLAB.NS": "Divi's Laboratories",
    "GRASIM.NS": "Grasim Industries",
    "HEROMOTOCO.NS": "Hero MotoCorp",
    "BRITANNIA.NS": "Britannia Industries",
    "NESTLEIND.NS": "Nestle India",
    "APOLLOHOSP.NS": "Apollo Hospitals",
    "BPCL.NS": "Bharat Petroleum",
    "IOC.NS": "Indian Oil Corporation",
    "HDFCLIFE.NS": "HDFC Life Insurance",
    "SBILIFE.NS": "SBI Life Insurance",
    "TATACONSUM.NS": "Tata Consumer Products",
    "TRENT.NS": "Trent",
    "PIDILITIND.NS": "Pidilite Industries",
    "DABUR.NS": "Dabur India",
}


# =========================================================
# MARKET DATA HANDLER
# =========================================================

class DataHandler:

    def __init__(self):
        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        })

    def get_historical_data(
        self,
        symbol,
        interval="1d",
        period1=None,
        period2=None
    ):

        if period1 is None:
            period1 = int(
                datetime(2020, 1, 1).timestamp()
            )

        if period2 is None:
            period2 = int(
                datetime.now().timestamp()
            )

        url = YAHOO_CHART_URL.format(symbol)

        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "events": "history",
            "includeAdjustedClose": "true"
        }

        try:

            response = self.session.get(
                url,
                params=params,
                timeout=15
            )

            if response.status_code != 200:
                return None

            data = response.json()

            chart = data.get("chart", {})

            results = chart.get("result")

            if not results:
                return None

            result = results[0]

            timestamps = result.get("timestamp")

            indicators = result.get(
                "indicators",
                {}
            )

            quote_list = indicators.get(
                "quote",
                []
            )

            if not timestamps or not quote_list:
                return None

            quote = quote_list[0]

            closes = quote.get("close", [])
            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            volumes = quote.get("volume", [])

            rows = []

            for i, timestamp in enumerate(timestamps):

                if i >= len(closes):
                    continue

                close = closes[i]

                if close is None:
                    continue

                rows.append({
                    "datetime": pd.to_datetime(
                        timestamp,
                        unit="s"
                    ),
                    "open": (
                        opens[i]
                        if i < len(opens)
                        else None
                    ),
                    "high": (
                        highs[i]
                        if i < len(highs)
                        else None
                    ),
                    "low": (
                        lows[i]
                        if i < len(lows)
                        else None
                    ),
                    "close": close,
                    "volume": (
                        volumes[i]
                        if i < len(volumes)
                        else 0
                    )
                })

            if len(rows) == 0:
                return None

            df = pd.DataFrame(rows)

            df.set_index(
                "datetime",
                inplace=True
            )

            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]

            for column in numeric_columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce"
                )

            df.dropna(
                subset=["close"],
                inplace=True
            )

            # Technical indicators
            df["MA20"] = (
                df["close"]
                .rolling(20)
                .mean()
            )

            df["RSI"] = self._calculate_rsi(
                df["close"]
            )

            df["volatility_10d"] = (
                df["close"]
                .pct_change()
                .rolling(10)
                .std()
            )

            return df.ffill().dropna()

        except Exception as e:

            print(
                f"Market data error for {symbol}: {e}"
            )

            return None

    def _calculate_rsi(
        self,
        series,
        window=14
    ):

        delta = series.diff()

        gain = delta.where(
            delta > 0,
            0
        )

        loss = -delta.where(
            delta < 0,
            0
        )

        avg_gain = (
            gain
            .rolling(window)
            .mean()
        )

        avg_loss = (
            loss
            .rolling(window)
            .mean()
        )

        avg_loss = avg_loss.replace(
            0,
            np.nan
        )

        rs = avg_gain / avg_loss

        return 100 - (
            100 / (1 + rs)
        )


# =========================================================
# RETURN PREDICTOR
# =========================================================

class ReturnPredictor:

    def __init__(self):
        self.model = None

    def create_features(self, df):

        features = pd.DataFrame(
            index=df.index
        )

        features["MA_ratio"] = (
            df["MA20"] /
            df["close"]
        )

        features["RSI"] = df["RSI"]

        features["volatility_10d"] = (
            df["volatility_10d"]
        )

        features["day"] = (
            df.index.dayofweek
        )

        features["month"] = (
            df.index.month
        )

        return features.dropna()

    def train_predict(self, df):

        X = self.create_features(df)

        y = (
            df["close"]
            .pct_change()
            .shift(-1)
        )

        data = pd.concat(
            [X, y],
            axis=1
        ).dropna()

        if len(data) < 10:
            return -1

        split = int(
            len(data) * 0.8
        )

        X_train = (
            data.iloc[:split, :-1]
            .to_numpy(dtype=float)
        )

        y_train = (
            data.iloc[:split, -1]
            .to_numpy(dtype=float)
        )

        X_test = (
            data.iloc[split:, :-1]
            .to_numpy(dtype=float)
        )

        if len(X_test) == 0:
            return -1

        # Standardization
        mean = X_train.mean(
            axis=0
        )

        std = X_train.std(
            axis=0
        )

        std[std == 0] = 1

        X_train_scaled = (
            X_train - mean
        ) / std

        X_test_scaled = (
            X_test - mean
        ) / std

        # Intercept
        X_train_scaled = np.column_stack(
            [
                np.ones(
                    len(X_train_scaled)
                ),
                X_train_scaled
            ]
        )

        X_test_scaled = np.column_stack(
            [
                np.ones(
                    len(X_test_scaled)
                ),
                X_test_scaled
            ]
        )

        # Ridge Regression
        identity = np.eye(
            X_train_scaled.shape[1]
        )

        identity[0, 0] = 0

        try:

            coefficients = np.linalg.solve(
                X_train_scaled.T
                @ X_train_scaled
                + 0.01 * identity,

                X_train_scaled.T
                @ y_train
            )

        except np.linalg.LinAlgError:

            coefficients = np.linalg.lstsq(
                X_train_scaled,
                y_train,
                rcond=None
            )[0]

        predictions = (
            X_test_scaled
            @ coefficients
        )

        return float(
            predictions[-1]
        )


# =========================================================
# PORTFOLIO GENERATION
# =========================================================

def generate_unique_portfolios(
    token,
    investment,
    risk,
    goal
):

    # `token` is kept in the function signature
    # for compatibility with the existing app.
    # It is NOT used anymore.

    handler = DataHandler()

    predictor = ReturnPredictor()

    from_date = int(
        datetime(
            2020,
            1,
            1
        ).timestamp()
    )

    to_date = int(
        datetime.now().timestamp()
    )

    # Short-term uses daily data.
    # Long-term uses weekly data.
    interval = (
        "1d"
        if goal == "short"
        else "1wk"
    )

    valid_stocks = {}

    # -----------------------------------------------------
    # Download and analyze market data
    # -----------------------------------------------------

    for symbol, name in STOCKS.items():

        try:

            df = handler.get_historical_data(
                symbol,
                interval,
                from_date,
                to_date
            )

            if df is None:
                continue

            if len(df) < 100:
                continue

            predicted_return = (
                predictor.train_predict(df)
            )

            if predicted_return > 0:

                valid_stocks[name] = {
                    "returns": (
                        df["close"]
                        .pct_change()
                        .dropna()
                    ),

                    "predicted_return":
                        predicted_return
                }

        except Exception as e:

            print(
                f"Skipping {name}: {e}"
            )

            continue

    # -----------------------------------------------------
    # Safety fallback
    # -----------------------------------------------------

    if len(valid_stocks) < 4:

        raise Exception(
            "Unable to retrieve enough "
            "market data. Please try again "
            "after a few seconds."
        )

    portfolios = []

    used_stocks = set()

    durations = {

        "short": [
            "1 month",
            "3 months",
            "6 months",
            "1 year"
        ],

        "long": [
            "1.5 years",
            "2 years",
            "3 years",
            "5 years"
        ]
    }

    # -----------------------------------------------------
    # Generate 5 different portfolios
    # -----------------------------------------------------

    for i in range(5):

        available = list(
            set(valid_stocks.keys())
            - used_stocks
        )

        if len(available) < 4:

            available = list(
                valid_stocks.keys()
            )

        stock_count = min(
            len(available),
            random.randint(3, 6)
        )

        selected = random.sample(
            available,
            stock_count
        )

        used_stocks.update(
            selected
        )

        sub_returns = pd.DataFrame(
            {
                stock:
                    valid_stocks[
                        stock
                    ]["returns"]

                for stock in selected
            }
        ).dropna()

        if len(sub_returns) < 10:
            continue

        sub_preds = pd.Series(
            {
                stock:
                    valid_stocks[
                        stock
                    ]["predicted_return"]

                for stock in selected
            }
        )

        strategy_name = ""

        try:

            # =================================================
            # MAX SHARPE APPROXIMATION
            # =================================================

            if i == 0:

                mean_returns = (
                    sub_returns
                    .mean()
                    .to_numpy()
                )

                covariance = (
                    sub_returns
                    .cov()
                    .to_numpy()
                )

                inverse_cov = np.linalg.pinv(
                    covariance
                    + np.eye(
                        len(selected)
                    ) * 1e-8
                )

                raw_weights = (
                    inverse_cov
                    @ mean_returns
                )

                raw_weights = np.maximum(
                    raw_weights,
                    0
                )

                if raw_weights.sum() == 0:

                    raw_weights = np.ones(
                        len(selected)
                    )

                raw_weights /= (
                    raw_weights.sum()
                )

                weights = {
                    stock: float(weight)
                    for stock, weight
                    in zip(
                        selected,
                        raw_weights
                    )
                }

                strategy_name = (
                    "Max Sharpe Ratio"
                )

            # =================================================
            # MINIMUM VOLATILITY
            # =================================================

            elif i == 1:

                covariance = (
                    sub_returns
                    .cov()
                    .to_numpy()
                )

                inverse_cov = np.linalg.pinv(
                    covariance
                    + np.eye(
                        len(selected)
                    ) * 1e-8
                )

                raw_weights = (
                    inverse_cov
                    @ np.ones(
                        len(selected)
                    )
                )

                raw_weights = np.maximum(
                    raw_weights,
                    0
                )

                if raw_weights.sum() == 0:

                    raw_weights = np.ones(
                        len(selected)
                    )

                raw_weights /= (
                    raw_weights.sum()
                )

                weights = {
                    stock: float(weight)
                    for stock, weight
                    in zip(
                        selected,
                        raw_weights
                    )
                }

                strategy_name = (
                    "Minimum Volatility"
                )

            # =================================================
            # TARGET RETURN
            # =================================================

            elif i == 2:

                target_return = float(
                    sub_preds.mean()
                )

                best_weights = None

                best_volatility = float(
                    "inf"
                )

                covariance = (
                    sub_returns
                    .cov()
                    .to_numpy()
                )

                for _ in range(1000):

                    candidate = (
                        np.random.dirichlet(
                            np.ones(
                                len(selected)
                            )
                        )
                    )

                    predicted_return = float(
                        np.dot(
                            candidate,
                            sub_preds.to_numpy()
                        )
                    )

                    volatility = float(
                        np.sqrt(
                            max(
                                candidate
                                @ covariance
                                @ candidate,
                                0
                            )
                        )
                    )

                    if (
                        predicted_return
                        >= target_return
                        and
                        volatility
                        < best_volatility
                    ):

                        best_weights = (
                            candidate
                        )

                        best_volatility = (
                            volatility
                        )

                if best_weights is None:

                    best_weights = (
                        np.ones(
                            len(selected)
                        )
                        / len(selected)
                    )

                weights = {
                    stock: float(weight)
                    for stock, weight
                    in zip(
                        selected,
                        best_weights
                    )
                }

                strategy_name = (
                    "Target Return Strategy"
                )

            # =================================================
            # RISK PARITY
            # =================================================

            elif i == 3:

                volatility = (
                    sub_returns
                    .std()
                    .to_numpy()
                )

                volatility[
                    volatility <= 0
                ] = 1e-8

                raw_weights = (
                    1 / volatility
                )

                raw_weights /= (
                    raw_weights.sum()
                )

                weights = {
                    stock: float(weight)
                    for stock, weight
                    in zip(
                        selected,
                        raw_weights
                    )
                }

                strategy_name = (
                    "Risk Parity"
                )

            # =================================================
            # RANDOM DIVERSIFIED
            # =================================================

            else:

                random_weights = (
                    np.random.dirichlet(
                        np.ones(
                            len(selected)
                        )
                    )
                )

                weights = {
                    stock: float(weight)
                    for stock, weight
                    in zip(
                        selected,
                        random_weights
                    )
                }

                strategy_name = (
                    "Random Diversified"
                )

        except Exception:

            random_weights = (
                np.random.dirichlet(
                    np.ones(
                        len(selected)
                    )
                )
            )

            weights = {
                stock: float(weight)
                for stock, weight
                in zip(
                    selected,
                    random_weights
                )
            }

            strategy_name = (
                "Diversified Portfolio"
            )

        # -----------------------------------------------------
        # Allocation
        # -----------------------------------------------------

        alloc = (
            pd.Series(weights)
            .mul(investment)
        )

        exp_ret = float(
            (
                sub_preds
                * pd.Series(weights)
            ).sum()
        )

        duration_label = random.choice(
            durations[goal]
        )

        text_value = (
            duration_label.lower()
        )

        if "month" in text_value:

            num = float(
                text_value
                .split()[0]
            )

            years = num / 12

        elif "week" in text_value:

            num = float(
                text_value
                .split()[0]
            )

            years = num / 52

        elif "day" in text_value:

            num = float(
                text_value
                .split()[0]
            )

            years = num / 365

        elif (
            "half" in text_value
            and "year" in text_value
        ):

            years = 0.5

        else:

            years = float(
                text_value
                .split()[0]
            )

        # -----------------------------------------------------
        # Future value
        # -----------------------------------------------------

        try:

            fv = round(
                investment
                * (
                    1 + exp_ret
                ) ** years,
                2
            )

        except Exception:

            fv = round(
                investment,
                2
            )

        profit = round(
            fv - investment,
            2
        )

        # -----------------------------------------------------
        # Result
        # -----------------------------------------------------

        portfolios.append(
            {
                "allocation":
                    alloc.round(2).to_dict(),

                "expected_return_percent":
                    (
                        round(
                            (
                                (
                                    1 + exp_ret
                                ) ** (
                                    1 / 12
                                )
                                - 1
                            ) * 100,
                            2
                        )
                        if goal == "short"
                        else round(
                            exp_ret * 100,
                            2
                        )
                    ),

                "investment":
                    round(
                        investment,
                        2
                    ),

                "future_value":
                    fv,

                "net_profit":
                    profit,

                "suggested_duration":
                    duration_label,

                "return_period":
                    (
                        "monthly"
                        if goal == "short"
                        else "yearly"
                    ),

                "strategy":
                    strategy_name
            }
        )

    if len(portfolios) == 0:

        raise Exception(
            "Could not generate portfolios. "
            "Please try again."
        )

    return portfolios