from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException

from app.config import DEFAULT_FORECAST_HORIZON
from app.schemas import (
    LocalPlanResponse,
    LocalPlanRequest,
    OptimizationResponse,
    OptimizeRequest,
    OverviewResponse,
    RegionMetric,
    StationLocation,
    TimelinePoint,
)
from app.services.data_loader import repository
from app.services.forecasting import ForecastBundle, build_forecast
from app.services.optimization import run_local_siting, run_optimization


app = FastAPI(title="Ontario EV Charger Planner", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache(maxsize=8)
def _forecast_bundle(horizon_quarters: int) -> ForecastBundle:
    regions = repository.get_region_frame()
    history = repository.get_ev_history()
    return build_forecast(regions, history, horizon_quarters)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview", response_model=OverviewResponse)
def overview(horizon_quarters: int = DEFAULT_FORECAST_HORIZON) -> OverviewResponse:
    bundle = _forecast_bundle(horizon_quarters)
    regions = bundle.regions
    history = repository.get_ev_history()
    latest_period = str(history["period_end"].max().date())
    return OverviewResponse(
        total_regions=int(len(regions)),
        total_current_evs=float(regions["current_total_ev"].sum()),
        total_forecast_evs=float(regions["forecast_total_ev"].sum()),
        total_existing_stations=int(regions["stations_count"].sum()),
        total_existing_ports=int(regions["total_ports"].sum()),
        total_fast_ports=int(regions["fast_ports"].sum()),
        average_nearest_station_km=float(regions["nearest_existing_km"].mean()),
        best_forecast_model=bundle.selected_model_name,
        baseline_mae=bundle.baseline_mae,
        selected_model_mae=bundle.selected_model_mae,
        latest_period=latest_period,
        forecast_horizon_quarters=horizon_quarters,
    )


@app.get("/api/regions", response_model=list[RegionMetric])
def regions(horizon_quarters: int = DEFAULT_FORECAST_HORIZON) -> list[RegionMetric]:
    bundle = _forecast_bundle(horizon_quarters)
    cols = [
        "fsa",
        "city_label",
        "latitude",
        "longitude",
        "current_total_ev",
        "forecast_total_ev",
        "stations_count",
        "total_ports",
        "fast_ports",
        "chargers_per_1000_evs",
        "nearest_existing_km",
        "underserved_score",
    ]
    return [RegionMetric(**row) for row in bundle.regions[cols].to_dict(orient="records")]


@app.get("/api/timeline", response_model=list[TimelinePoint])
def timeline(horizon_quarters: int = DEFAULT_FORECAST_HORIZON) -> list[TimelinePoint]:
    bundle = _forecast_bundle(horizon_quarters)
    cleaned = []
    for item in bundle.timeline:
        if item["total_ev"] == item["total_ev"]:
            cleaned.append(TimelinePoint(**item))
    return cleaned


@app.get("/api/stations", response_model=list[StationLocation])
def stations() -> list[StationLocation]:
    frame = repository.get_station_locations()
    return [StationLocation(**row) for row in frame.to_dict(orient="records")]


@app.post("/api/optimize", response_model=OptimizationResponse)
def optimize(payload: OptimizeRequest) -> OptimizationResponse:
    bundle = _forecast_bundle(payload.horizon_quarters)
    result = run_optimization(bundle.regions, payload)
    return OptimizationResponse(**result)


@app.post("/api/local-plan", response_model=LocalPlanResponse)
def local_plan(payload: LocalPlanRequest) -> LocalPlanResponse:
    bundle = _forecast_bundle(payload.horizon_quarters)
    try:
        result = run_local_siting(bundle.regions, payload, repository.get_station_locations())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LocalPlanResponse(**result)
