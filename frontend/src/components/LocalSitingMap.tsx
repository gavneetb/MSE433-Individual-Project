import type { LatLngTuple } from 'leaflet'
import { useEffect } from 'react'
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'
import type { LocalPlanSite, RegionMetric } from '../types/api'

type LocalSitingMapProps = {
  focusRegion: RegionMetric
  localSites: LocalPlanSite[]
  serviceRadiusKm: number
}

function FitToLocalPlan({
  focusRegion,
  localSites,
}: {
  focusRegion: RegionMetric
  localSites: LocalPlanSite[]
}) {
  const map = useMap()

  useEffect(() => {
    const points: LatLngTuple[] = [
      [focusRegion.latitude, focusRegion.longitude],
      ...localSites.map((site) => [site.latitude, site.longitude] as LatLngTuple),
    ]
    if (points.length === 1) {
      map.flyTo(points[0], 12, {
        animate: true,
        duration: 0.8,
      })
      return
    }

    map.fitBounds(points, {
      animate: true,
      duration: 0.8,
      padding: [36, 36],
    })
  }, [focusRegion, localSites, map])

  return null
}

export default function LocalSitingMap({ focusRegion, localSites, serviceRadiusKm }: LocalSitingMapProps) {
  const center: LatLngTuple = [focusRegion.latitude, focusRegion.longitude]

  return (
    <div className="map-shell local-map-shell">
      <MapContainer center={center} zoom={12} scrollWheelZoom={true} style={{ height: '100%' }}>
        <FitToLocalPlan focusRegion={focusRegion} localSites={localSites} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Circle
          center={center}
          radius={serviceRadiusKm * 1000}
          pathOptions={{
            color: '#c96e2b',
            fillColor: '#c96e2b',
            fillOpacity: 0.06,
            weight: 2,
            dashArray: '6 6',
          }}
        />
        <CircleMarker
          center={center}
          radius={9}
          pathOptions={{
            color: '#155f4d',
            fillColor: '#155f4d',
            fillOpacity: 0.92,
            weight: 2,
          }}
        >
          <Popup>
            <strong>
              {focusRegion.fsa} - {focusRegion.city_label}
            </strong>
            <div>Existing FSA center used as the local planning anchor.</div>
          </Popup>
        </CircleMarker>
        {localSites.map((site) => (
          <CircleMarker
            key={site.site_name}
            center={[site.latitude, site.longitude] as LatLngTuple}
            radius={10}
            pathOptions={{
              color: '#102433',
              fillColor: '#102433',
              fillOpacity: 0.94,
              weight: 2,
            }}
          >
            <Popup>
              <strong>{site.site_name}</strong>
              <div>Candidate type: {site.candidate_type}</div>
              <div>Busy-area score: {site.busy_area_score.toFixed(1)}</div>
              <div>Assigned forecast EVs: {Math.round(site.assigned_forecast_evs).toLocaleString()}</div>
              <div>Average drive distance: {site.average_drive_km.toFixed(1)} km</div>
              <div>Distance savings: {site.distance_savings_km.toFixed(1)} km</div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
