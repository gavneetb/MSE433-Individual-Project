import type {
  LocalPlanRequest,
  LocalPlanResponse,
  OverviewResponse,
  RegionMetric,
  StationLocation,
  TimelinePoint,
} from '../types/api'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function getOverview(horizonQuarters: number) {
  return request<OverviewResponse>(`/api/overview?horizon_quarters=${horizonQuarters}`)
}

export function getRegions(horizonQuarters: number) {
  return request<RegionMetric[]>(`/api/regions?horizon_quarters=${horizonQuarters}`)
}

export function getTimeline(horizonQuarters: number) {
  return request<TimelinePoint[]>(`/api/timeline?horizon_quarters=${horizonQuarters}`)
}

export function getStations() {
  return request<StationLocation[]>('/api/stations')
}

export function getLocalPlan(payload: LocalPlanRequest) {
  return request<LocalPlanResponse>('/api/local-plan', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
