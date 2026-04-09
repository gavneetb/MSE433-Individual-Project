from __future__ import annotations

import io
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pgeocode
import requests

from app.config import (
    CACHE_DIR,
    NREL_API_KEY,
    NREL_STATIONS_URL,
    ONTARIO_EV_DATASET_PAGE,
    ONTARIO_PREFIXES,
    OVERPASS_API_URL,
)


def _cache_path(name: str) -> Path:
    return CACHE_DIR / name


def _download_text(url: str) -> str:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.text


def _download_json(url: str, params: dict[str, object]) -> dict:
    retries = 6
    for attempt in range(retries):
        response = requests.get(url, params=params, timeout=120)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        retry_after = float(response.headers.get("Retry-After", "3"))
        time.sleep(retry_after + attempt)
    response.raise_for_status()
    return response.json()


def _standardize_fsa(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    raw = re.sub(r"[^A-Za-z0-9]", "", str(value).upper())
    if len(raw) < 3:
        return None
    prefix = raw[:3]
    if prefix[0] not in ONTARIO_PREFIXES:
        return None
    return prefix


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


def _nearest_distance_km(lat: float, lon: float, station_coords: list[tuple[float, float]]) -> float:
    if not station_coords:
        return float("nan")
    return min(_haversine_km(lat, lon, station_lat, station_lon) for station_lat, station_lon in station_coords)


def _normalize_place_name(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\s*\(.*?\)", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


@dataclass
class DataRepository:
    region_frame: pd.DataFrame | None = None
    station_frame: pd.DataFrame | None = None
    ev_history_frame: pd.DataFrame | None = None
    station_updated_at: str | None = None

    def _build_fsa_city_labels(self, fsas: list[str]) -> pd.DataFrame:
        nomi = pgeocode.Nominatim("CA")
        place_data = nomi._data[["postal_code", "place_name", "county_name"]].copy()
        place_data["FSA"] = place_data["postal_code"].map(_standardize_fsa)
        place_data["label"] = place_data["place_name"].map(_normalize_place_name)
        place_data["county_label"] = place_data["county_name"].map(_normalize_place_name)
        place_data = place_data.dropna(subset=["FSA"])
        place_data = place_data[place_data["FSA"].isin(fsas)].copy()

        rows: list[dict[str, str]] = []
        for fsa, frame in place_data.groupby("FSA"):
            labels = [label for label in frame["label"].dropna().tolist() if label and label.lower() != "ontario"]
            if not labels:
                labels = [label for label in frame["county_label"].dropna().tolist() if label]
            unique_labels: list[str] = []
            for label in labels:
                if label not in unique_labels:
                    unique_labels.append(label)
            if not unique_labels:
                unique_labels = ["Ontario"]
            city_label = " / ".join(unique_labels[:3])
            rows.append({"FSA": fsa, "city_label": city_label})
        labels_frame = pd.DataFrame(rows)
        existing_fsas = set(labels_frame["FSA"]) if not labels_frame.empty else set()
        missing_fsas = [fsa for fsa in fsas if fsa not in existing_fsas]
        if missing_fsas and not labels_frame.empty:
            labels_frame["prefix2"] = labels_frame["FSA"].str[:2]
            prefix2_labels = labels_frame.groupby("prefix2", as_index=False).first()[["prefix2", "city_label"]]
            fallback_rows = []
            for fsa in missing_fsas:
                row = prefix2_labels[prefix2_labels["prefix2"] == fsa[:2]]
                fallback_rows.append(
                    {
                        "FSA": fsa,
                        "city_label": row["city_label"].iloc[0] if not row.empty else "Ontario",
                    }
                )
            labels_frame = pd.concat([labels_frame.drop(columns=["prefix2"]), pd.DataFrame(fallback_rows)], ignore_index=True)
        return labels_frame

    def _load_osm_station_fallback(self) -> pd.DataFrame:
        query = """
        [out:json][timeout:180];
        area["name"="Ontario"]["boundary"="administrative"]->.searchArea;
        (
          node["amenity"="charging_station"](area.searchArea);
          way["amenity"="charging_station"](area.searchArea);
          relation["amenity"="charging_station"](area.searchArea);
        );
        out center;
        """
        response = requests.post(OVERPASS_API_URL, data=query, timeout=240)
        response.raise_for_status()
        payload = response.json()
        rows = []
        fast_keys = ("ccs", "chademo", "tesla_supercharger", "supercharger", "nacs")
        for element in payload.get("elements", []):
            tags = element.get("tags", {})
            access = str(tags.get("access", "yes")).lower()
            if access in {"private", "no"}:
                continue
            latitude = element.get("lat") or element.get("center", {}).get("lat")
            longitude = element.get("lon") or element.get("center", {}).get("lon")
            if latitude is None or longitude is None:
                continue
            total_ports = 0
            fast_ports = 0
            for key, value in tags.items():
                if not key.startswith("socket:") or key == "socket:type":
                    continue
                try:
                    count = int(str(value).split(";")[0])
                except ValueError:
                    count = 1 if str(value).strip().lower() in {"yes", "true"} else 0
                total_ports += count
                if any(marker in key.lower() for marker in fast_keys):
                    fast_ports += count
            if total_ports == 0:
                total_ports = int(tags.get("capacity", 1)) if str(tags.get("capacity", "")).isdigit() else 1
            rows.append(
                {
                    "id": f"osm-{element.get('type', 'node')}-{element['id']}",
                    "station_name": tags.get("name", "Charging Station"),
                    "city": tags.get("addr:city"),
                    "state": "ON",
                    "zip": tags.get("addr:postcode"),
                    "latitude": latitude,
                    "longitude": longitude,
                    "ev_level1_evse_num": 0,
                    "ev_level2_evse_num": max(total_ports - fast_ports, 0),
                    "ev_dc_fast_num": fast_ports,
                    "ev_network": tags.get("network") or tags.get("operator") or "OpenStreetMap",
                    "open_date": tags.get("start_date"),
                    "updated_at": payload.get("osm3s", {}).get("timestamp_osm_base"),
                }
            )
        self.station_updated_at = payload.get("osm3s", {}).get("timestamp_osm_base")
        return pd.DataFrame(rows)

    def get_ev_history(self) -> pd.DataFrame:
        if self.ev_history_frame is not None:
            return self.ev_history_frame.copy()

        cache_file = _cache_path("ontario_ev_history.csv")
        if cache_file.exists():
            history = pd.read_csv(cache_file, parse_dates=["period_end"])
            self.ev_history_frame = history
            return history.copy()

        page = _download_text(ONTARIO_EV_DATASET_PAGE)
        urls = re.findall(r"https://data\.ontario\.ca/dataset/[^\"]+/download/[^\"]+\.csv", page)
        records: list[pd.DataFrame] = []
        for url in urls:
            match = re.search(r"(\d{4}-\d{2}-\d{2})", url)
            if not match:
                continue
            period_end = pd.Timestamp(match.group(1))
            csv_text = _download_text(url)
            frame = pd.read_csv(io.StringIO(csv_text))
            frame.columns = [col.strip() for col in frame.columns]
            frame = frame.rename(columns={"TotalEV": "Total EV"})
            frame["period_end"] = period_end
            frame["FSA"] = frame["FSA"].map(_standardize_fsa)
            frame = frame.dropna(subset=["FSA"]).copy()
            numeric_columns = ["BEV", "PHEV", "Total EV"]
            for col in numeric_columns:
                frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0)
            records.append(frame[["FSA", "BEV", "PHEV", "Total EV", "period_end"]])

        if not records:
            raise RuntimeError("No Ontario EV history files were discovered.")

        history = pd.concat(records, ignore_index=True).sort_values(["FSA", "period_end"])
        history.to_csv(cache_file, index=False)
        self.ev_history_frame = history
        return history.copy()

    def get_station_frame(self) -> pd.DataFrame:
        if self.station_frame is not None:
            return self.station_frame.copy()

        cache_file = _cache_path("nrel_ontario_stations.csv")
        meta_file = _cache_path("nrel_station_meta.txt")
        if cache_file.exists():
            frame = pd.read_csv(cache_file)
            self.station_frame = frame
            if meta_file.exists():
                self.station_updated_at = meta_file.read_text(encoding="utf-8").strip()
            return frame.copy()

        use_live_api = NREL_API_KEY != "DEMO_KEY"
        if use_live_api:
            try:
                base_params = {
                    "api_key": NREL_API_KEY,
                    "fuel_type": "ELEC",
                    "country": "CA",
                    "state": "ON",
                    "access": "public",
                    "status": "E",
                    "limit": 200,
                }
                offset = 0
                rows: list[dict] = []
                total_results = None
                while total_results is None or offset < total_results:
                    payload = _download_json(NREL_STATIONS_URL, {**base_params, "offset": offset})
                    if total_results is None:
                        total_results = int(payload.get("total_results", 0))
                    fuel_stations = payload.get("fuel_stations", [])
                    if not fuel_stations:
                        break
                    rows.extend(fuel_stations)
                    offset += len(fuel_stations)
                    time.sleep(0.4)
                stations = pd.DataFrame(rows)
                if stations.empty:
                    raise RuntimeError("The NREL Ontario station query returned no records.")
            except Exception:
                stations = self._load_osm_station_fallback()
        else:
            stations = self._load_osm_station_fallback()

        keep = [
            "id",
            "station_name",
            "city",
            "state",
            "zip",
            "latitude",
            "longitude",
            "ev_level1_evse_num",
            "ev_level2_evse_num",
            "ev_dc_fast_num",
            "ev_network",
            "open_date",
            "updated_at",
        ]
        stations = stations[keep].copy()
        stations["fsa"] = stations["zip"].map(_standardize_fsa)
        for col in ["ev_level1_evse_num", "ev_level2_evse_num", "ev_dc_fast_num"]:
            stations[col] = pd.to_numeric(stations[col], errors="coerce").fillna(0).astype(int)
        stations["total_ports"] = (
            stations["ev_level1_evse_num"] + stations["ev_level2_evse_num"] + stations["ev_dc_fast_num"]
        )
        if not self.station_updated_at:
            self.station_updated_at = str(stations["updated_at"].max())
        stations.to_csv(cache_file, index=False)
        if self.station_updated_at:
            meta_file.write_text(self.station_updated_at, encoding="utf-8")
        self.station_frame = stations
        return stations.copy()

    def get_station_locations(self) -> pd.DataFrame:
        stations = self.get_station_frame().copy()
        history = self.get_ev_history()
        latest_period = history["period_end"].max()
        latest_fsas = sorted(history.loc[history["period_end"] == latest_period, "FSA"].dropna().unique().tolist())
        centroids = self.get_fsa_centroids(latest_fsas).rename(columns={"FSA": "fsa"})
        centroid_lookup = centroids.set_index("fsa")[["latitude", "longitude"]].to_dict("index")

        station_geo = stations.dropna(subset=["latitude", "longitude"]).copy()
        station_geo["fsa"] = station_geo["fsa"].map(_standardize_fsa)
        missing_indexes = station_geo[station_geo["fsa"].isna()].index.tolist()
        for idx in missing_indexes:
            lat = float(station_geo.at[idx, "latitude"])
            lon = float(station_geo.at[idx, "longitude"])
            nearest = min(
                centroid_lookup.items(),
                key=lambda item: _haversine_km(lat, lon, item[1]["latitude"], item[1]["longitude"]),
            )[0]
            station_geo.at[idx, "fsa"] = nearest

        station_geo["id"] = station_geo["id"].astype(str)
        station_geo["ev_level2_evse_num"] = pd.to_numeric(
            station_geo["ev_level2_evse_num"], errors="coerce"
        ).fillna(0).astype(int)
        station_geo["ev_dc_fast_num"] = pd.to_numeric(
            station_geo["ev_dc_fast_num"], errors="coerce"
        ).fillna(0).astype(int)
        station_geo["total_ports"] = pd.to_numeric(station_geo["total_ports"], errors="coerce").fillna(0).astype(int)
        station_geo["city"] = station_geo["city"].where(station_geo["city"].notna(), None)
        station_geo["ev_network"] = station_geo["ev_network"].where(station_geo["ev_network"].notna(), None)

        return station_geo[
            [
                "id",
                "station_name",
                "fsa",
                "city",
                "latitude",
                "longitude",
                "ev_level2_evse_num",
                "ev_dc_fast_num",
                "total_ports",
                "ev_network",
            ]
        ].rename(
            columns={
                "ev_level2_evse_num": "level2_ports",
                "ev_dc_fast_num": "fast_ports",
                "ev_network": "network",
            }
        )

    def get_fsa_centroids(self, fsas: list[str]) -> pd.DataFrame:
        cache_file = _cache_path("ontario_fsa_centroids.csv")
        if cache_file.exists():
            centroids = pd.read_csv(cache_file)
        else:
            nomi = pgeocode.Nominatim("CA")
            postal_data = nomi._data[["postal_code", "latitude", "longitude"]].copy()
            postal_data["fsa"] = postal_data["postal_code"].map(_standardize_fsa)
            postal_data = postal_data.dropna(subset=["fsa", "latitude", "longitude"])
            centroids = (
                postal_data.groupby("fsa", as_index=False)[["latitude", "longitude"]]
                .mean()
                .rename(columns={"fsa": "FSA"})
            )
            centroids.to_csv(cache_file, index=False)

        centroids["FSA"] = centroids["FSA"].map(_standardize_fsa)
        centroids = centroids[centroids["FSA"].isin(fsas)].copy()
        existing_fsas = set(centroids["FSA"])
        missing_fsas = [fsa for fsa in fsas if fsa not in existing_fsas]
        if missing_fsas:
            enriched = centroids.copy()
            enriched["prefix2"] = enriched["FSA"].str[:2]
            prefix2_means = enriched.groupby("prefix2", as_index=False)[["latitude", "longitude"]].mean()
            prefix1_means = (
                enriched.assign(prefix1=enriched["FSA"].str[:1])
                .groupby("prefix1", as_index=False)[["latitude", "longitude"]]
                .mean()
            )
            fallback_rows = []
            for fsa in missing_fsas:
                row = prefix2_means[prefix2_means["prefix2"] == fsa[:2]]
                if row.empty:
                    row = prefix1_means[prefix1_means["prefix1"] == fsa[:1]]
                if row.empty:
                    continue
                fallback_rows.append(
                    {
                        "FSA": fsa,
                        "latitude": float(row["latitude"].iloc[0]),
                        "longitude": float(row["longitude"].iloc[0]),
                    }
                )
            if fallback_rows:
                centroids = pd.concat([centroids, pd.DataFrame(fallback_rows)], ignore_index=True)
        return centroids

    def get_region_frame(self) -> pd.DataFrame:
        if self.region_frame is not None:
            return self.region_frame.copy()

        history = self.get_ev_history()
        latest_period = history["period_end"].max()
        latest = history[history["period_end"] == latest_period].copy()
        latest = latest.rename(
            columns={
                "FSA": "fsa",
                "BEV": "current_bev",
                "PHEV": "current_phev",
                "Total EV": "current_total_ev",
            }
        )

        stations = self.get_station_frame()
        centroids = self.get_fsa_centroids(sorted(latest["fsa"].unique().tolist()))
        centroids = centroids.rename(columns={"FSA": "fsa"})
        city_labels = self._build_fsa_city_labels(sorted(latest["fsa"].unique().tolist()))
        city_labels = city_labels.rename(columns={"FSA": "fsa"})

        station_geo = stations.dropna(subset=["latitude", "longitude"]).copy()
        station_coords = list(zip(station_geo["latitude"], station_geo["longitude"]))

        assigned_fsa = station_geo["fsa"].copy()
        if assigned_fsa.isna().any():
            centroid_lookup = centroids.set_index("fsa")[["latitude", "longitude"]].to_dict("index")
            missing_indexes = assigned_fsa[assigned_fsa.isna()].index.tolist()
            for idx in missing_indexes:
                lat = float(station_geo.at[idx, "latitude"])
                lon = float(station_geo.at[idx, "longitude"])
                nearest = min(
                    centroid_lookup.items(),
                    key=lambda item: _haversine_km(lat, lon, item[1]["latitude"], item[1]["longitude"]),
                )[0]
                station_geo.at[idx, "fsa"] = nearest

        supply = (
            station_geo.groupby("fsa", as_index=False)
            .agg(
                stations_count=("id", "count"),
                total_ports=("total_ports", "sum"),
                fast_ports=("ev_dc_fast_num", "sum"),
            )
            .fillna(0)
        )

        regions = (
            latest.merge(centroids, on="fsa", how="left")
            .merge(city_labels, on="fsa", how="left")
            .merge(supply, on="fsa", how="left")
        )
        regions["city_label"] = regions["city_label"].fillna("Ontario")
        regions[["stations_count", "total_ports", "fast_ports"]] = regions[
            ["stations_count", "total_ports", "fast_ports"]
        ].apply(pd.to_numeric, errors="coerce").fillna(0)
        regions["stations_count"] = regions["stations_count"].astype(int)
        regions["total_ports"] = regions["total_ports"].astype(int)
        regions["fast_ports"] = regions["fast_ports"].astype(int)

        regions["nearest_existing_km"] = regions.apply(
            lambda row: _nearest_distance_km(float(row["latitude"]), float(row["longitude"]), station_coords),
            axis=1,
        )
        regions["chargers_per_1000_evs"] = (
            regions["total_ports"] / regions["current_total_ev"].clip(lower=1) * 1000
        )

        ev_density_norm = regions["current_total_ev"] / regions["current_total_ev"].max()
        charger_denominator = max(float(regions["chargers_per_1000_evs"].max()), 1.0)
        distance_denominator = max(float(regions["nearest_existing_km"].max()), 1.0)
        charger_norm = regions["chargers_per_1000_evs"] / charger_denominator
        distance_norm = regions["nearest_existing_km"] / distance_denominator
        score = 0.5 * ev_density_norm + 0.35 * distance_norm + 0.15 * (1 - charger_norm.fillna(0))
        regions["underserved_score"] = score.round(4)

        regions = regions.sort_values("fsa").reset_index(drop=True)
        self.region_frame = regions
        return regions.copy()


repository = DataRepository()
