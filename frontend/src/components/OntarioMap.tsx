import type { LatLngTuple } from 'leaflet'
import { useEffect } from 'react'
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'
import type { RegionMetric, StationLocation } from '../types/api'

type OntarioMapProps = {
  regions: RegionMetric[]
  currentStations: StationLocation[]
  selectedRegion?: RegionMetric | null
  onSelectRegion?: (fsa: string) => void
  serviceRadiusKm?: number
}

function circleColor(score: number) {
  if (score > 0.72) return '#b94a3b'
  if (score > 0.52) return '#db8d33'
  return '#1f7a63'
}

function FocusOnSelection({
  selectedRegion,
  currentStations,
}: {
  selectedRegion: RegionMetric | null
  currentStations: StationLocation[]
}) {
  const map = useMap()

  useEffect(() => {
    if (!selectedRegion) return

    const points: LatLngTuple[] = [
      [selectedRegion.latitude, selectedRegion.longitude],
      ...currentStations.map((station) => [station.latitude, station.longitude] as LatLngTuple),
    ]

    if (points.length === 1) {
      map.flyTo(points[0], 10, {
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
  }, [map, selectedRegion, currentStations])

  return null
}

export default function OntarioMap({
  regions,
  currentStations,
  selectedRegion = null,
  onSelectRegion = () => {},
  serviceRadiusKm = 15,
}: OntarioMapProps) {
  const ontarioCenter: LatLngTuple = [50.0, -85.0]

  return (
    <div className="map-shell">
      <MapContainer center={ontarioCenter} zoom={5.4} scrollWheelZoom={true} style={{ height: 520 }}>
        <FocusOnSelection selectedRegion={selectedRegion} currentStations={currentStations} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {selectedRegion ? (
          <Circle
            center={[selectedRegion.latitude, selectedRegion.longitude] as LatLngTuple}
            radius={serviceRadiusKm * 1000}
            pathOptions={{
              color: '#102433',
              fillColor: '#102433',
              fillOpacity: 0.07,
              weight: 2,
              dashArray: '6 6',
            }}
          />
        ) : null}
        {regions.map((region) => (
          <CircleMarker
            key={region.fsa}
            center={[region.latitude, region.longitude] as LatLngTuple}
            radius={Math.max(4, Math.min(14, region.forecast_total_ev / 1800))}
            pathOptions={{
              color: selectedRegion?.fsa === region.fsa ? '#102433' : circleColor(region.underserved_score),
              fillColor: selectedRegion?.fsa === region.fsa ? '#102433' : circleColor(region.underserved_score),
              fillOpacity: selectedRegion?.fsa === region.fsa ? 0.72 : 0.28,
              weight: selectedRegion?.fsa === region.fsa ? 2 : 1,
            }}
            eventHandlers={{
              click: () => onSelectRegion(region.fsa),
            }}
          >
            <Popup>
              <strong>
                {region.fsa} · {region.city_label}
              </strong>
              <div>Current EVs: {Math.round(region.current_total_ev).toLocaleString()}</div>
              <div>Forecast EVs: {Math.round(region.forecast_total_ev).toLocaleString()}</div>
              <div>Existing ports: {region.total_ports}</div>
            </Popup>
          </CircleMarker>
        ))}
        {currentStations.map((station) => (
          <CircleMarker
            key={`station-${station.id}`}
            center={[station.latitude, station.longitude] as LatLngTuple}
            radius={station.fast_ports > 0 ? 8 : 6}
            pathOptions={{
              color: station.fast_ports > 0 ? '#b94a3b' : '#155f4d',
              fillColor: station.fast_ports > 0 ? '#b94a3b' : '#155f4d',
              fillOpacity: 0.94,
              weight: 1.6,
            }}
          >
            <Popup>
              <strong>{station.station_name}</strong>
              <div>FSA: {station.fsa}</div>
              <div>Level 2 ports: {station.level2_ports}</div>
              <div>Fast ports: {station.fast_ports}</div>
              <div>Total ports: {station.total_ports}</div>
              <div>Network: {station.network ?? 'Unknown'}</div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
