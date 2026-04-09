from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pulp
import requests

from app.config import CACHE_DIR, OVERPASS_API_URL, SITE_TYPE_COSTS
from app.schemas import LocalPlanRequest, OptimizeRequest


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _km_to_lat(delta_km: float) -> float:
    return delta_km / 111.0


def _km_to_lon(delta_km: float, latitude: float) -> float:
    scale = 111.320 * math.cos(math.radians(latitude))
    if abs(scale) < 1e-6:
        return 0.0
    return delta_km / scale


def _candidate_cache_path(fsa: str, radius_km: float) -> Path:
    return CACHE_DIR / f"local_candidates_{fsa.lower()}_{int(round(radius_km))}km.json"


def _candidate_label(tags: dict[str, str]) -> str:
    for key in ("name", "brand", "operator"):
        value = tags.get(key)
        if value:
            return str(value)
    amenity = tags.get("amenity")
    shop = tags.get("shop")
    public_transport = tags.get("public_transport")
    railway = tags.get("railway")
    parking = tags.get("parking")
    if amenity:
        return f"{str(amenity).replace('_', ' ').title()} site"
    if shop:
        return f"{str(shop).replace('_', ' ').title()} site"
    if public_transport:
        return f"{str(public_transport).replace('_', ' ').title()} hub"
    if railway:
        return f"{str(railway).replace('_', ' ').title()} hub"
    if parking:
        return f"{str(parking).replace('_', ' ').title()} parking"
    return "Public access site"


def _candidate_type(tags: dict[str, str]) -> str:
    if tags.get("shop") in {"mall", "supermarket", "department_store", "convenience", "retail"}:
        return "retail"
    if tags.get("amenity") in {"parking", "parking_entrance"} or tags.get("park_ride") == "yes":
        return "parking"
    if tags.get("amenity") in {"fuel", "bus_station"} or tags.get("railway") == "station":
        return "transport"
    if tags.get("public_transport") in {"station", "platform", "stop_position"}:
        return "transport"
    if tags.get("amenity") in {"hospital", "college", "university", "library", "community_centre", "townhall"}:
        return "civic"
    if tags.get("building") in {"commercial", "retail", "civic"}:
        return "commercial"
    return "mixed-use"


def _base_busy_score(tags: dict[str, str]) -> float:
    score = 0.0
    amenity = str(tags.get("amenity", "")).lower()
    shop = str(tags.get("shop", "")).lower()
    public_transport = str(tags.get("public_transport", "")).lower()
    railway = str(tags.get("railway", "")).lower()
    building = str(tags.get("building", "")).lower()

    if shop in {"mall", "department_store"}:
        score += 5.0
    elif shop in {"supermarket", "retail"}:
        score += 4.2
    elif shop == "convenience":
        score += 2.8

    if amenity == "parking":
        score += 4.0
        if str(tags.get("parking", "")).lower() in {"multi-storey", "surface", "underground"}:
            score += 0.6
    elif amenity == "fuel":
        score += 3.5
    elif amenity in {"bus_station", "hospital", "college", "university"}:
        score += 3.8
    elif amenity in {"library", "community_centre", "townhall", "marketplace"}:
        score += 2.8

    if public_transport in {"station", "platform", "stop_position"}:
        score += 2.2
    if railway == "station":
        score += 2.8
    if tags.get("park_ride") == "yes":
        score += 1.8
    if building in {"commercial", "retail"}:
        score += 1.5

    return score


def _fetch_busy_area_candidates(
    focus_fsa: str,
    latitude: float,
    longitude: float,
    radius_km: float,
) -> list[dict[str, float | str]]:
    cache_file = _candidate_cache_path(focus_fsa, radius_km)
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    radius_m = int(max(radius_km, 4.0) * 1000)
    query = f"""
    [out:json][timeout:25];
    (
      nwr(around:{radius_m},{latitude},{longitude})["amenity"~"parking|fuel|bus_station|hospital|college|university"];
      nwr(around:{radius_m},{latitude},{longitude})["shop"~"mall|supermarket|department_store|retail"];
      nwr(around:{radius_m},{latitude},{longitude})["railway"="station"];
      nwr(around:{radius_m},{latitude},{longitude})["park_ride"="yes"];
    );
    out center tags;
    """
    try:
        response = requests.post(OVERPASS_API_URL, data=query, timeout=40)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    candidates: list[dict[str, float | str]] = []
    seen: set[tuple[float, float]] = set()
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue
        key = (round(float(lat), 5), round(float(lon), 5))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "site_name": _candidate_label(tags),
                "latitude": round(float(lat), 6),
                "longitude": round(float(lon), 6),
                "candidate_type": _candidate_type(tags),
                "busy_area_score": round(_base_busy_score(tags), 2),
            }
        )

    cache_file.write_text(json.dumps(candidates), encoding="utf-8")
    return candidates


def _generate_local_candidates(
    latitude: float,
    longitude: float,
    spacing_km: float,
    target_count: int,
) -> list[dict[str, float | str]]:
    candidates: list[dict[str, float | str]] = []
    seen: set[tuple[float, float]] = set()
    ring = 0

    while len(candidates) < target_count:
        if ring == 0:
            lat_offset_km = 0.0
            lon_offset_km = 0.0
            candidate_lat = latitude
            candidate_lon = longitude
            key = (round(candidate_lat, 6), round(candidate_lon, 6))
            if key not in seen:
                candidates.append(
                    {
                        "site_name": "Core",
                        "latitude": candidate_lat,
                        "longitude": candidate_lon,
                        "candidate_type": "synthetic",
                        "busy_area_score": 1.0,
                    }
                )
                seen.add(key)
            ring += 1
            continue

        for lat_index in range(-ring, ring + 1):
            for lon_index in range(-ring, ring + 1):
                if max(abs(lat_index), abs(lon_index)) != ring:
                    continue
                lat_offset_km = lat_index * spacing_km * 0.78
                lon_offset_km = lon_index * spacing_km * 0.78
                candidate_lat = latitude + _km_to_lat(lat_offset_km)
                candidate_lon = longitude + _km_to_lon(lon_offset_km, latitude)
                key = (round(candidate_lat, 6), round(candidate_lon, 6))
                if key in seen:
                    continue
                candidates.append(
                    {
                        "site_name": f"Grid {lat_index:+d}/{lon_index:+d}",
                        "latitude": candidate_lat,
                        "longitude": candidate_lon,
                        "candidate_type": "synthetic",
                        "busy_area_score": 1.0,
                    }
                )
                seen.add(key)
                if len(candidates) >= target_count:
                    break
            if len(candidates) >= target_count:
                break
        ring += 1

    return candidates


def run_optimization(regions: pd.DataFrame, payload: OptimizeRequest) -> dict:
    valid_regions = regions.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    candidate_fsas = valid_regions["fsa"].tolist()
    demand_fsas = candidate_fsas[:]
    demand_weight = valid_regions["forecast_total_ev"].astype(float).tolist()
    baseline_covered = (valid_regions["nearest_existing_km"] <= payload.service_radius_km).astype(int).tolist()
    coords = list(zip(valid_regions["latitude"], valid_regions["longitude"]))

    coverage_matrix: dict[tuple[int, int], int] = {}
    for i, (cand_lat, cand_lon) in enumerate(coords):
        for j, (demand_lat, demand_lon) in enumerate(coords):
            coverage_matrix[(i, j)] = int(
                _haversine_km(float(cand_lat), float(cand_lon), float(demand_lat), float(demand_lon))
                <= payload.service_radius_km
            )

    model = pulp.LpProblem("ontario_ev_charger_placement", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("build", range(len(candidate_fsas)), lowBound=0, upBound=1, cat="Binary")
    y = pulp.LpVariable.dicts("covered", range(len(demand_fsas)), lowBound=0, upBound=1, cat="Binary")

    model += pulp.lpSum(demand_weight[j] * y[j] for j in range(len(demand_fsas)))

    for j in range(len(demand_fsas)):
        model += y[j] <= baseline_covered[j] + pulp.lpSum(
            coverage_matrix[(i, j)] * x[i] for i in range(len(candidate_fsas))
        )

    if payload.constraint_mode == "budget":
        site_cost = SITE_TYPE_COSTS[payload.charger_type]
        model += pulp.lpSum(site_cost * x[i] for i in range(len(candidate_fsas))) <= payload.budget
    else:
        model += pulp.lpSum(x[i] for i in range(len(candidate_fsas))) <= payload.max_new_sites

    solver = pulp.PULP_CBC_CMD(msg=False)
    model.solve(solver)

    selected_indexes = [i for i in range(len(candidate_fsas)) if x[i].value() and x[i].value() > 0.5]
    site_cost = float(SITE_TYPE_COSTS[payload.charger_type])
    total_demand = float(sum(demand_weight))
    covered_demand = float(sum(demand_weight[j] * (y[j].value() or 0.0) for j in range(len(demand_fsas))))
    baseline_demand = float(sum(demand_weight[j] * baseline_covered[j] for j in range(len(demand_fsas))))

    sites = []
    for idx in selected_indexes:
        fsa = candidate_fsas[idx]
        lat, lon = coords[idx]
        covered_uncovered_demand = 0.0
        newly_coverable = 0.0
        for j in range(len(demand_fsas)):
            if coverage_matrix[(idx, j)]:
                newly_coverable += demand_weight[j]
                if baseline_covered[j] == 0:
                    covered_uncovered_demand += demand_weight[j]
        sites.append(
            {
                "fsa": fsa,
                "latitude": float(lat),
                "longitude": float(lon),
                "site_cost": site_cost,
                "baseline_uncovered_ev": round(covered_uncovered_demand, 2),
                "covered_evs_within_radius": round(newly_coverable, 2),
            }
        )

    sites.sort(key=lambda item: item["baseline_uncovered_ev"], reverse=True)
    total_cost = site_cost * len(selected_indexes)

    return {
        "summary": {
            "selected_sites": len(selected_indexes),
            "projected_covered_evs": round(covered_demand, 2),
            "projected_total_evs": round(total_demand, 2),
            "projected_coverage_pct": round((covered_demand / total_demand) * 100 if total_demand else 0.0, 2),
            "baseline_coverage_pct": round((baseline_demand / total_demand) * 100 if total_demand else 0.0, 2),
            "incremental_coverage_pct": round(
                ((covered_demand - baseline_demand) / total_demand) * 100 if total_demand else 0.0, 2
            ),
            "total_cost": round(total_cost, 2),
            "constraint_mode": payload.constraint_mode,
            "service_radius_km": payload.service_radius_km,
            "charger_type": payload.charger_type,
        },
        "sites": sites,
    }


def run_local_siting(
    regions: pd.DataFrame,
    payload: LocalPlanRequest,
    station_locations: pd.DataFrame | None = None,
) -> dict:
    valid_regions = regions.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    focus_matches = valid_regions.loc[valid_regions["fsa"] == payload.focus_fsa.upper()]
    if focus_matches.empty:
        raise ValueError(f"FSA {payload.focus_fsa.upper()} was not found in the demand dataset.")

    focus_region = focus_matches.iloc[0]
    focus_lat = float(focus_region["latitude"])
    focus_lon = float(focus_region["longitude"])
    local_radius_km = max(payload.service_radius_km * 1.75, 18.0)

    local_regions = valid_regions.loc[
        valid_regions.apply(
            lambda row: _haversine_km(
                focus_lat,
                focus_lon,
                float(row["latitude"]),
                float(row["longitude"]),
            )
            <= local_radius_km,
            axis=1,
        )
    ].reset_index(drop=True)
    if local_regions.empty:
        local_regions = focus_matches.reset_index(drop=True)

    spacing_km = min(max(payload.service_radius_km * 0.28, 1.5), 5.0)
    candidate_radius_km = min(max(payload.service_radius_km * 0.8, 6.0), 12.0)
    candidate_target_count = max(payload.new_site_count * 3, 16)
    candidates = _fetch_busy_area_candidates(payload.focus_fsa.upper(), focus_lat, focus_lon, candidate_radius_km)
    if not candidates:
        candidates = _generate_local_candidates(focus_lat, focus_lon, spacing_km, candidate_target_count)

    station_coords: list[tuple[float, float]] = []
    if station_locations is not None and not station_locations.empty:
        station_coords = [
            (float(row["latitude"]), float(row["longitude"]))
            for _, row in station_locations.dropna(subset=["latitude", "longitude"]).iterrows()
            if _haversine_km(focus_lat, focus_lon, float(row["latitude"]), float(row["longitude"])) <= local_radius_km
        ]

    filtered_candidates: list[dict[str, float | str]] = []
    for candidate in candidates:
        candidate_lat = float(candidate["latitude"])
        candidate_lon = float(candidate["longitude"])
        if station_coords:
            nearest_existing = min(
                _haversine_km(candidate_lat, candidate_lon, station_lat, station_lon)
                for station_lat, station_lon in station_coords
            )
            if nearest_existing < 0.35:
                continue
        filtered_candidates.append(candidate)

    if len(filtered_candidates) < max(payload.new_site_count, 6):
        fallback_candidates = _generate_local_candidates(focus_lat, focus_lon, spacing_km, candidate_target_count)
        fallback_lookup = {
            (round(float(candidate["latitude"]), 5), round(float(candidate["longitude"]), 5))
            for candidate in filtered_candidates
        }
        for candidate in fallback_candidates:
            key = (round(float(candidate["latitude"]), 5), round(float(candidate["longitude"]), 5))
            if key in fallback_lookup:
                continue
            filtered_candidates.append(candidate)
            fallback_lookup.add(key)

    filtered_candidates.sort(
        key=lambda item: (
            float(item["busy_area_score"]),
            -_haversine_km(focus_lat, focus_lon, float(item["latitude"]), float(item["longitude"])),
        ),
        reverse=True,
    )
    filtered_candidates = filtered_candidates[: max(candidate_target_count * 3, 60)]

    candidates = filtered_candidates
    candidate_points = [
        (float(candidate["latitude"]), float(candidate["longitude"])) for candidate in candidates
    ]

    for idx, candidate in enumerate(candidates):
        candidate_lat, candidate_lon = candidate_points[idx]
        nearby_activity = sum(
            1.0
            for other_lat, other_lon in candidate_points
            if _haversine_km(candidate_lat, candidate_lon, other_lat, other_lon) <= 0.8
        ) - 1.0
        candidate["busy_area_score"] = round(float(candidate["busy_area_score"]) + max(nearby_activity, 0.0) * 0.45, 2)

    target_kept_candidates = max(payload.new_site_count * 4, 18)
    candidates.sort(
        key=lambda item: (
            float(item["busy_area_score"]),
            -_haversine_km(focus_lat, focus_lon, float(item["latitude"]), float(item["longitude"])),
        ),
        reverse=True,
    )
    thinned_candidates: list[dict[str, float | str]] = []
    for candidate in candidates:
        candidate_lat = float(candidate["latitude"])
        candidate_lon = float(candidate["longitude"])
        if any(
            _haversine_km(candidate_lat, candidate_lon, float(other["latitude"]), float(other["longitude"])) < 0.3
            for other in thinned_candidates
        ):
            continue
        thinned_candidates.append(candidate)
        if len(thinned_candidates) >= target_kept_candidates:
            break
    candidates = thinned_candidates

    selected_site_count = min(payload.new_site_count, len(candidates))
    site_cost = float(SITE_TYPE_COSTS[payload.charger_type])

    weights = local_regions["forecast_total_ev"].astype(float).tolist()
    baseline_distances = local_regions["nearest_existing_km"].astype(float).tolist()
    demand_points = list(zip(local_regions["latitude"].astype(float), local_regions["longitude"].astype(float)))
    max_busy_score = max(float(candidate["busy_area_score"]) for candidate in candidates) if candidates else 1.0
    normalized_busy_scores = [
        (float(candidate["busy_area_score"]) / max_busy_score) if max_busy_score else 0.0 for candidate in candidates
    ]
    distance_matrix = {
        (i, j): _haversine_km(candidate_lat, candidate_lon, demand_lat, demand_lon)
        for i, (candidate_lat, candidate_lon) in enumerate(candidate_points)
        for j, (demand_lat, demand_lon) in enumerate(demand_points)
    }
    attractiveness_bonus_km = 1.15
    effective_distance_matrix = {
        (i, j): max(distance_matrix[(i, j)] - attractiveness_bonus_km * normalized_busy_scores[i], 0.0)
        for i in range(len(candidates))
        for j in range(len(local_regions))
    }

    model = pulp.LpProblem("local_ev_siting_p_median", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("build_local", range(len(candidates)), lowBound=0, upBound=1, cat="Binary")
    assign_existing = pulp.LpVariable.dicts(
        "assign_existing",
        range(len(local_regions)),
        lowBound=0,
        upBound=1,
        cat="Binary",
    )
    assign_candidate = pulp.LpVariable.dicts(
        "assign_candidate",
        ((i, j) for i in range(len(candidates)) for j in range(len(local_regions))),
        lowBound=0,
        upBound=1,
        cat="Binary",
    )

    model += pulp.lpSum(
        weights[j]
        * (
            baseline_distances[j] * assign_existing[j]
            + pulp.lpSum(
                effective_distance_matrix[(i, j)] * assign_candidate[(i, j)] for i in range(len(candidates))
            )
        )
        for j in range(len(local_regions))
    )

    for j in range(len(local_regions)):
        model += assign_existing[j] + pulp.lpSum(assign_candidate[(i, j)] for i in range(len(candidates))) == 1

    for i in range(len(candidates)):
        for j in range(len(local_regions)):
            model += assign_candidate[(i, j)] <= x[i]

    model += pulp.lpSum(x[i] for i in range(len(candidates))) == selected_site_count

    solver = pulp.PULP_CBC_CMD(msg=False)
    model.solve(solver)

    selected_indexes = [i for i in range(len(candidates)) if (x[i].value() or 0.0) > 0.5]

    total_local_demand = float(sum(weights))
    weighted_distance_before = float(
        sum(weights[j] * baseline_distances[j] for j in range(len(local_regions)))
    )
    weighted_distance_after = float(
        sum(
            weights[j]
            * (
                baseline_distances[j] * (assign_existing[j].value() or 0.0)
                + sum(
                    distance_matrix[(i, j)] * (assign_candidate[(i, j)].value() or 0.0)
                    for i in range(len(candidates))
                )
            )
            for j in range(len(local_regions))
        )
    )

    sites = []
    for idx in selected_indexes:
        candidate = candidates[idx]
        assigned_forecast_evs = float(
            sum(weights[j] * (assign_candidate[(idx, j)].value() or 0.0) for j in range(len(local_regions)))
        )
        weighted_assigned_distance = float(
            sum(
                weights[j] * distance_matrix[(idx, j)] * (assign_candidate[(idx, j)].value() or 0.0)
                for j in range(len(local_regions))
            )
        )
        distance_savings = float(
            sum(
                weights[j]
                * max(baseline_distances[j] - distance_matrix[(idx, j)], 0.0)
                * (assign_candidate[(idx, j)].value() or 0.0)
                for j in range(len(local_regions))
            )
        )
        average_drive_km = weighted_assigned_distance / assigned_forecast_evs if assigned_forecast_evs else 0.0
        sites.append(
            {
                "site_name": f"{payload.focus_fsa.upper()} {candidate['site_name']}",
                "focus_fsa": payload.focus_fsa.upper(),
                "latitude": round(float(candidate["latitude"]), 6),
                "longitude": round(float(candidate["longitude"]), 6),
                "site_cost": site_cost,
                "candidate_type": str(candidate["candidate_type"]),
                "busy_area_score": round(float(candidate["busy_area_score"]), 2),
                "assigned_forecast_evs": round(assigned_forecast_evs, 2),
                "average_drive_km": round(average_drive_km, 2),
                "distance_savings_km": round(distance_savings, 2),
            }
        )

    sites.sort(key=lambda item: item["assigned_forecast_evs"], reverse=True)
    average_before = weighted_distance_before / total_local_demand if total_local_demand else 0.0
    average_after = weighted_distance_after / total_local_demand if total_local_demand else 0.0
    total_saved = max(weighted_distance_before - weighted_distance_after, 0.0)
    improvement_pct = ((average_before - average_after) / average_before * 100) if average_before else 0.0

    return {
        "summary": {
            "focus_fsa": payload.focus_fsa.upper(),
            "city_label": str(focus_region["city_label"]),
            "selected_sites": len(selected_indexes),
            "requested_sites": payload.new_site_count,
            "average_drive_before_km": round(average_before, 2),
            "average_drive_after_km": round(average_after, 2),
            "total_distance_saved_km": round(total_saved, 2),
            "improvement_pct": round(improvement_pct, 2),
            "total_local_forecast_evs": round(total_local_demand, 2),
            "total_cost": round(site_cost * len(selected_indexes), 2),
            "charger_type": payload.charger_type,
            "service_radius_km": payload.service_radius_km,
            "local_model": "p-median + busy-area score",
            "candidate_source": "OpenStreetMap public-facing sites",
        },
        "sites": sites,
    }
