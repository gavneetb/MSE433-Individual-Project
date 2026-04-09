export type OverviewResponse = {
  total_regions: number
  total_current_evs: number
  total_forecast_evs: number
  total_existing_stations: number
  total_existing_ports: number
  total_fast_ports: number
  average_nearest_station_km: number
  best_forecast_model: string
  baseline_mae: number | null
  selected_model_mae: number | null
  latest_period: string
  forecast_horizon_quarters: number
}

export type RegionMetric = {
  fsa: string
  city_label: string
  latitude: number
  longitude: number
  current_total_ev: number
  forecast_total_ev: number
  stations_count: number
  total_ports: number
  fast_ports: number
  chargers_per_1000_evs: number
  nearest_existing_km: number
  underserved_score: number
}

export type TimelinePoint = {
  label: string
  total_ev: number
}

export type StationLocation = {
  id: string
  station_name: string
  fsa: string
  city: string | null
  latitude: number
  longitude: number
  level2_ports: number
  fast_ports: number
  total_ports: number
  network: string | null
}

export type OptimizeRequest = {
  horizon_quarters: number
  service_radius_km: number
  constraint_mode: 'site_count' | 'budget'
  max_new_sites: number
  budget: number
  charger_type: 'level2' | 'dc_fast'
}

export type LocalPlanRequest = {
  focus_fsa: string
  horizon_quarters: number
  service_radius_km: number
  new_site_count: number
  charger_type: 'level2' | 'dc_fast'
}

export type OptimizationSite = {
  fsa: string
  latitude: number
  longitude: number
  site_cost: number
  baseline_uncovered_ev: number
  covered_evs_within_radius: number
}

export type LocalPlanSite = {
  site_name: string
  focus_fsa: string
  latitude: number
  longitude: number
  site_cost: number
  candidate_type: string
  busy_area_score: number
  assigned_forecast_evs: number
  average_drive_km: number
  distance_savings_km: number
}

export type OptimizationResponse = {
  summary: {
    selected_sites: number
    projected_covered_evs: number
    projected_total_evs: number
    projected_coverage_pct: number
    baseline_coverage_pct: number
    incremental_coverage_pct: number
    total_cost: number
    constraint_mode: string
    service_radius_km: number
    charger_type: string
  }
  sites: OptimizationSite[]
}

export type LocalPlanResponse = {
  summary: {
    focus_fsa: string
    city_label: string
    selected_sites: number
    requested_sites: number
    average_drive_before_km: number
    average_drive_after_km: number
    total_distance_saved_km: number
    improvement_pct: number
    total_local_forecast_evs: number
    total_cost: number
    charger_type: string
    service_radius_km: number
    local_model: string
    candidate_source: string
  }
  sites: LocalPlanSite[]
}
