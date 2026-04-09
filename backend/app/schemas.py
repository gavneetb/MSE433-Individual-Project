from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegionMetric(BaseModel):
    fsa: str
    city_label: str
    latitude: float
    longitude: float
    current_total_ev: float
    forecast_total_ev: float
    stations_count: int
    total_ports: int
    fast_ports: int
    chargers_per_1000_evs: float
    nearest_existing_km: float
    underserved_score: float


class OverviewResponse(BaseModel):
    total_regions: int
    total_current_evs: float
    total_forecast_evs: float
    total_existing_stations: int
    total_existing_ports: int
    total_fast_ports: int
    average_nearest_station_km: float
    best_forecast_model: str
    baseline_mae: float | None
    selected_model_mae: float | None
    latest_period: str
    forecast_horizon_quarters: int


class TimelinePoint(BaseModel):
    label: str
    total_ev: float


class StationLocation(BaseModel):
    id: str
    station_name: str
    fsa: str
    city: str | None
    latitude: float
    longitude: float
    level2_ports: int
    fast_ports: int
    total_ports: int
    network: str | None


class OptimizeRequest(BaseModel):
    horizon_quarters: int = Field(default=4, ge=1, le=8)
    service_radius_km: float = Field(default=15.0, ge=1.0, le=100.0)
    constraint_mode: Literal["site_count", "budget"] = "site_count"
    max_new_sites: int = Field(default=25, ge=1, le=150)
    budget: float = Field(default=3_000_000, ge=50_000)
    charger_type: Literal["level2", "dc_fast"] = "level2"


class LocalPlanRequest(BaseModel):
    focus_fsa: str = Field(min_length=3, max_length=3)
    horizon_quarters: int = Field(default=4, ge=1, le=8)
    service_radius_km: float = Field(default=15.0, ge=1.0, le=100.0)
    new_site_count: int = Field(default=3, ge=1, le=8)
    charger_type: Literal["level2", "dc_fast"] = "level2"


class OptimizationSite(BaseModel):
    fsa: str
    latitude: float
    longitude: float
    site_cost: float
    baseline_uncovered_ev: float
    covered_evs_within_radius: float


class LocalPlanSite(BaseModel):
    site_name: str
    focus_fsa: str
    latitude: float
    longitude: float
    site_cost: float
    candidate_type: str
    busy_area_score: float
    assigned_forecast_evs: float
    average_drive_km: float
    distance_savings_km: float


class OptimizationSummary(BaseModel):
    selected_sites: int
    projected_covered_evs: float
    projected_total_evs: float
    projected_coverage_pct: float
    baseline_coverage_pct: float
    incremental_coverage_pct: float
    total_cost: float
    constraint_mode: str
    service_radius_km: float
    charger_type: str


class OptimizationResponse(BaseModel):
    summary: OptimizationSummary
    sites: list[OptimizationSite]


class LocalPlanSummary(BaseModel):
    focus_fsa: str
    city_label: str
    selected_sites: int
    requested_sites: int
    average_drive_before_km: float
    average_drive_after_km: float
    total_distance_saved_km: float
    improvement_pct: float
    total_local_forecast_evs: float
    total_cost: float
    charger_type: str
    service_radius_km: float
    local_model: str
    candidate_source: str


class LocalPlanResponse(BaseModel):
    summary: LocalPlanSummary
    sites: list[LocalPlanSite]
