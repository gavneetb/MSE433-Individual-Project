from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

from app.config import DEFAULT_FORECAST_HORIZON


FEATURE_COLUMNS = [
    "quarter_index",
    "total_ev",
    "lag_1",
    "lag_2",
    "lag_4",
    "growth_1q",
    "growth_4q",
    "bev_share",
    "stations_count",
    "total_ports",
    "fast_ports",
    "nearest_existing_km",
    "latitude",
    "longitude",
]


@dataclass
class ForecastBundle:
    regions: pd.DataFrame
    timeline: list[dict[str, float | str]]
    selected_model_name: str
    baseline_mae: float | None
    selected_model_mae: float | None


def _prepare_training_frame(history: pd.DataFrame, regions: pd.DataFrame) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    work = history.copy().rename(
        columns={
            "FSA": "fsa",
            "BEV": "bev",
            "PHEV": "phev",
            "Total EV": "total_ev",
        }
    )
    periods = sorted(work["period_end"].unique().tolist())
    period_index = {period: idx for idx, period in enumerate(periods)}
    work["quarter_index"] = work["period_end"].map(period_index).astype(int)
    work = work.sort_values(["fsa", "period_end"]).reset_index(drop=True)

    grouped = work.groupby("fsa")
    work["lag_1"] = grouped["total_ev"].shift(1)
    work["lag_2"] = grouped["total_ev"].shift(2)
    work["lag_4"] = grouped["total_ev"].shift(4)
    work["growth_1q"] = (work["total_ev"] - work["lag_1"]) / work["lag_1"]
    work["growth_4q"] = (work["total_ev"] - work["lag_4"]) / work["lag_4"]
    work["bev_share"] = work["bev"] / (work["total_ev"].replace(0, np.nan))
    work["target_next_total_ev"] = grouped["total_ev"].shift(-1)

    static_cols = [
        "fsa",
        "stations_count",
        "total_ports",
        "fast_ports",
        "nearest_existing_km",
        "latitude",
        "longitude",
    ]
    train = work.merge(regions[static_cols], on="fsa", how="left")
    train = train.dropna(subset=["lag_1", "lag_2", "lag_4", "target_next_total_ev", "latitude", "longitude"]).copy()
    train = train.fillna(0)
    return train, periods


def build_forecast(regions: pd.DataFrame, history: pd.DataFrame, horizon_quarters: int = DEFAULT_FORECAST_HORIZON) -> ForecastBundle:
    train, periods = _prepare_training_frame(history, regions)

    max_quarter_index = int(train["quarter_index"].max())
    test_mask = train["quarter_index"] == max_quarter_index - 1

    x_train = train.loc[~test_mask, FEATURE_COLUMNS]
    y_train = train.loc[~test_mask, "target_next_total_ev"]
    x_test = train.loc[test_mask, FEATURE_COLUMNS]
    y_test = train.loc[test_mask, "target_next_total_ev"]

    baseline = LinearRegression()
    boosted = GradientBoostingRegressor(random_state=42)
    baseline.fit(x_train, y_train)
    boosted.fit(x_train, y_train)

    baseline_mae = None
    boosted_mae = None
    if not x_test.empty:
        baseline_mae = float(mean_absolute_error(y_test, baseline.predict(x_test)))
        boosted_mae = float(mean_absolute_error(y_test, boosted.predict(x_test)))

    selected_model = boosted
    selected_name = "Gradient Boosting Regressor"
    selected_mae = boosted_mae
    if baseline_mae is not None and boosted_mae is not None and baseline_mae < boosted_mae:
        selected_model = baseline
        selected_name = "Linear Regression"
        selected_mae = baseline_mae

    forecast = regions.copy()
    latest_history = (
        history.rename(columns={"FSA": "fsa", "BEV": "bev", "PHEV": "phev", "Total EV": "total_ev"})
        .sort_values(["fsa", "period_end"])
        .groupby("fsa")
        .tail(4)
    )

    state = {}
    for fsa, frame in latest_history.groupby("fsa"):
        totals = frame["total_ev"].tolist()
        while len(totals) < 4:
            totals.insert(0, totals[0] if totals else 0.0)
        last = frame.iloc[-1]
        state[fsa] = {
            "quarter_index": max_quarter_index,
            "lags": totals[-4:],
            "bev_share": float(last["bev"] / max(last["total_ev"], 1)),
        }

    timeline = [
        {"label": str(period.date()), "total_ev": float(value)}
        for period, value in (
            history.groupby("period_end")["Total EV"].sum().sort_index().items()
        )
    ]

    future_totals = {}
    forecast_step_totals: list[float] = []
    for fsa in forecast["fsa"]:
        info = state.get(fsa)
        if info is None:
            current_total = float(forecast.loc[forecast["fsa"] == fsa, "current_total_ev"].iloc[0])
            info = {
                "quarter_index": max_quarter_index,
                "lags": [current_total, current_total, current_total, current_total],
                "bev_share": 0.7,
            }
        lags = info["lags"][:]
        quarter_index = max_quarter_index
        row = forecast[forecast["fsa"] == fsa].iloc[0]
        predicted = float(lags[-1])
        step_predictions: list[float] = []
        for _ in range(horizon_quarters):
            quarter_index += 1
            lag_1 = lags[-1]
            lag_2 = lags[-2]
            lag_4 = lags[0]
            features = pd.DataFrame(
                [
                    {
                        "quarter_index": quarter_index,
                        "total_ev": lag_1,
                        "lag_1": lag_1,
                        "lag_2": lag_2,
                        "lag_4": lag_4,
                        "growth_1q": (lag_1 - lag_2) / max(lag_2, 1),
                        "growth_4q": (lag_1 - lag_4) / max(lag_4, 1),
                        "bev_share": info["bev_share"],
                        "stations_count": row["stations_count"],
                        "total_ports": row["total_ports"],
                        "fast_ports": row["fast_ports"],
                        "nearest_existing_km": row["nearest_existing_km"],
                        "latitude": row["latitude"],
                        "longitude": row["longitude"],
                    }
                ]
            )
            predicted = max(float(selected_model.predict(features.fillna(0))[0]), 0.0)
            lags = lags[1:] + [predicted]
            step_predictions.append(predicted)
        future_totals[fsa] = predicted
        if not forecast_step_totals:
            forecast_step_totals = [0.0] * len(step_predictions)
        for idx, value in enumerate(step_predictions):
            forecast_step_totals[idx] += value

    forecast["forecast_total_ev"] = forecast["fsa"].map(future_totals).astype(float)
    forecast["forecast_growth_pct"] = (
        (forecast["forecast_total_ev"] - forecast["current_total_ev"]) / forecast["current_total_ev"].clip(lower=1) * 100
    )

    for step, total in enumerate(forecast_step_totals, start=1):
        timeline.append({"label": f"Forecast Q+{step}", "total_ev": float(total)})

    return ForecastBundle(
        regions=forecast,
        timeline=timeline,
        selected_model_name=selected_name,
        baseline_mae=baseline_mae,
        selected_model_mae=selected_mae,
    )
