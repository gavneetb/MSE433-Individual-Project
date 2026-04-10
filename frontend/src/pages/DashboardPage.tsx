import { useEffect, useState } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import LocalSitingMap from '../components/LocalSitingMap'
import MetricCard from '../components/MetricCard'
import OntarioMap from '../components/OntarioMap'
import { getLocalPlan, getOverview, getRegions, getStations, getTimeline } from '../lib/api'
import type {
  LocalPlanResponse,
  OverviewResponse,
  RegionMetric,
  StationLocation,
  TimelinePoint,
} from '../types/api'

function formatCompact(value: number) {
  return new Intl.NumberFormat('en-CA', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function formatInteger(value: number) {
  return Math.round(value).toLocaleString('en-CA')
}

export default function DashboardPage() {
  const [horizonQuarters, setHorizonQuarters] = useState(4)
  const [horizonInput, setHorizonInput] = useState('4')
  const [serviceRadius, setServiceRadius] = useState(15)
  const [budget, setBudget] = useState(3_000_000)
  const [budgetInput, setBudgetInput] = useState('3000000')
  const [localNewSites, setLocalNewSites] = useState(3)
  const [localNewSitesInput, setLocalNewSitesInput] = useState('3')
  const [localBudget, setLocalBudget] = useState(360_000)
  const [localBudgetInput, setLocalBudgetInput] = useState('360000')
  const [chargerType, setChargerType] = useState<'level2' | 'dc_fast'>('level2')
  const [overview, setOverview] = useState<OverviewResponse | null>(null)
  const [regions, setRegions] = useState<RegionMetric[]>([])
  const [stations, setStations] = useState<StationLocation[]>([])
  const [timeline, setTimeline] = useState<TimelinePoint[]>([])
  const [localPlan, setLocalPlan] = useState<LocalPlanResponse | null>(null)
  const [selectedCityLabel, setSelectedCityLabel] = useState<string | null>(null)
  const [selectedFsa, setSelectedFsa] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingLocalPlan, setLoadingLocalPlan] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [localPlanError, setLocalPlanError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [nextOverview, nextRegions, nextStations, nextTimeline] = await Promise.all([
          getOverview(horizonQuarters),
          getRegions(horizonQuarters),
          getStations(),
          getTimeline(horizonQuarters),
        ])
        if (cancelled) return
        setOverview(nextOverview)
        setRegions(nextRegions)
        setStations(nextStations)
        setTimeline(nextTimeline)
        const defaultRegion = [...nextRegions].sort((a, b) => b.underserved_score - a.underserved_score)[0] ?? null
        setSelectedCityLabel((current) => current ?? defaultRegion?.city_label ?? null)
        setSelectedFsa((current) => current ?? defaultRegion?.fsa ?? null)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load dashboard data.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [horizonQuarters])

  const cityOptions = [...new Set(regions.map((region) => region.city_label))].sort((left, right) => left.localeCompare(right))
  const cityRegions = selectedCityLabel ? regions.filter((region) => region.city_label === selectedCityLabel) : regions
  const hasMultipleFsasInCity = cityRegions.length > 1
  const siteCost = chargerType === 'dc_fast' ? 400_000 : 120_000
  const maxAffordableSites = Math.floor(budget / siteCost)
  const maxLocalAffordableSites = Math.floor(localBudget / siteCost)
  const effectiveLocalSites = Math.min(localNewSites, maxLocalAffordableSites)
  const localBudgetSupportsAnySite = maxLocalAffordableSites >= 1
  const previewRequestedSites = Math.max(0, Math.floor(Number(localNewSitesInput) || 0))
  const previewBudget = Math.max(0, Number(localBudgetInput) || 0)
  const previewAffordableSites = Math.floor(previewBudget / siteCost)
  const previewModeledSites = Math.min(previewRequestedSites, previewAffordableSites)

  useEffect(() => {
    if (!selectedCityLabel || cityRegions.length === 0) return
    const inCity = cityRegions.some((region) => region.fsa === selectedFsa)
    if (!inCity) {
      setSelectedFsa(cityRegions.sort((a, b) => b.underserved_score - a.underserved_score)[0]?.fsa ?? null)
    }
  }, [selectedCityLabel, selectedFsa, cityRegions])

  useEffect(() => {
    if (!overview || !selectedFsa) return
    const focusFsa = selectedFsa
    if (effectiveLocalSites < 1) {
      setLocalPlan(null)
      setLoadingLocalPlan(false)
      return
    }

    let cancelled = false

    async function loadLocalPlan() {
      setLoadingLocalPlan(true)
      setLocalPlanError(null)
      setLocalPlan(null)
      try {
        const nextPlan = await getLocalPlan({
          focus_fsa: focusFsa,
          horizon_quarters: horizonQuarters,
          service_radius_km: serviceRadius,
          new_site_count: effectiveLocalSites,
          charger_type: chargerType,
        })
        if (!cancelled) setLocalPlan(nextPlan)
      } catch (err) {
        if (!cancelled) {
          setLocalPlan(null)
          setLocalPlanError(err instanceof Error ? err.message : 'Unable to solve the local siting model.')
        }
      } finally {
        if (!cancelled) setLoadingLocalPlan(false)
      }
    }

    void loadLocalPlan()
    return () => {
      cancelled = true
    }
  }, [overview, selectedFsa, horizonQuarters, serviceRadius, effectiveLocalSites, chargerType])

  if (loading) {
    return <div className="loading">Loading Ontario EV demand, charger supply, and forecast signals.</div>
  }

  if (error || !overview) {
    return <div className="error">{error ?? 'The dashboard could not be rendered.'}</div>
  }

  const selectedRegion = cityRegions.find((region) => region.fsa === selectedFsa) ?? cityRegions[0] ?? regions[0] ?? null
  const applyScenario = () => {
    const parsedHorizon = Math.floor(Number(horizonInput))
    const parsedBudget = Number(budgetInput)
    if (!Number.isFinite(parsedHorizon) || parsedHorizon < 1) {
      setError('Enter a valid forecast horizon before applying the scenario.')
      return
    }
    if (!Number.isFinite(parsedBudget)) {
      setError('Enter a valid budget before applying the scenario.')
      return
    }
    setError(null)
    setHorizonQuarters(Math.min(8, Math.max(1, parsedHorizon)))
    setBudget(Math.max(100_000, parsedBudget))
  }
  const applyLocalScenario = () => {
    const parsedSites = Math.floor(Number(localNewSitesInput))
    const parsedBudget = Number(localBudgetInput)
    if (!Number.isFinite(parsedSites) || parsedSites < 1) {
      setLocalPlanError('Enter a valid number of requested sites before applying the local plan.')
      return
    }
    if (!Number.isFinite(parsedBudget) || parsedBudget < 0) {
      setLocalPlanError('Enter a valid local budget before applying the local plan.')
      return
    }
    setLocalPlanError(null)
    setLocalNewSites(parsedSites)
    setLocalBudget(parsedBudget)
  }

  const handleSelectFsa = (fsa: string) => {
    const nextRegion = regions.find((region) => region.fsa === fsa)
    if (!nextRegion) return
    setSelectedCityLabel(nextRegion.city_label)
    setSelectedFsa(nextRegion.fsa)
  }

  const selectedLevel2Ports = selectedRegion ? Math.max(selectedRegion.total_ports - selectedRegion.fast_ports, 0) : 0
  const selectedFsaStations = selectedRegion ? stations.filter((station) => station.fsa === selectedRegion.fsa) : []
  const localPlanSites = localPlan?.sites ?? []
  const feasibilityState = !localBudgetSupportsAnySite
    ? 'blocked'
    : localNewSites <= maxLocalAffordableSites
      ? 'ok'
      : 'warning'
  const feasibilityTitle =
    feasibilityState === 'blocked'
      ? 'Budget cannot fund a site'
      : feasibilityState === 'warning'
        ? 'Budget is below request'
        : 'Budget supports request'

  return (
    <div className="dashboard">
      <section className="selection-banner">
        <p className="selection-eyebrow">Current View</p>
        <h2>
          {selectedRegion ? `${selectedRegion.city_label} - ${selectedRegion.fsa}` : 'Ontario'}
        </h2>
        <p>
          The cards below now update for the selected FSA inside the selected city area.
        </p>
      </section>

      <section className="metrics-grid">
        <MetricCard
          label="Selected City Area"
          value={selectedRegion?.city_label ?? 'Ontario'}
          subtext={`Viewing FSA ${selectedRegion?.fsa ?? '--'}`}
        />
        <MetricCard
          label="Current EVs"
          value={formatInteger(selectedRegion?.current_total_ev ?? 0)}
          subtext={`Current registered EVs in ${selectedRegion?.fsa ?? 'the selected FSA'}`}
        />
        <MetricCard
          label="Forecast EVs"
          value={formatInteger(selectedRegion?.forecast_total_ev ?? 0)}
          subtext={`${overview.forecast_horizon_quarters} quarter outlook for ${selectedRegion?.fsa ?? 'the selected FSA'}`}
        />
        <MetricCard
          label="Existing Stations"
          value={`${selectedRegion?.stations_count ?? 0}`}
          subtext={`${selectedRegion?.total_ports ?? 0} total ports already serving this FSA`}
        />
        <MetricCard
          label="Reachability"
          value={`${selectedRegion ? selectedRegion.nearest_existing_km.toFixed(1) : '0.0'} km`}
          subtext={
            selectedRegion
              ? `${Math.max((selectedRegion.total_ports ?? 0) - (selectedRegion.fast_ports ?? 0), 0)} L2 and ${selectedRegion.fast_ports} fast ports in the selected FSA`
              : 'No FSA selected'
          }
        />
      </section>

      <div className="content-grid">
        <aside className="controls">
          <h2>Planner Controls</h2>
          <p className="panel-copy">
            Main filter is city area. Then choose an `FSA`, which is the first 3 characters of a postal code, inside that city area.
          </p>
          <div className="controls-grid">
            <div className="control-row">
              <label htmlFor="citySelect">City area</label>
              <select
                id="citySelect"
                value={selectedCityLabel ?? ''}
                onChange={(event) => setSelectedCityLabel(event.target.value)}
              >
                {cityOptions.map((city) => (
                  <option key={city} value={city}>
                    {city}
                  </option>
                ))}
              </select>
            </div>
            <div className="control-row">
              <label htmlFor="horizon">Forecast horizon (quarters)</label>
              <input
                id="horizon"
                type="number"
                min={1}
                max={8}
                step={1}
                value={horizonInput}
                onChange={(event) => setHorizonInput(event.target.value)}
              />
              <p className="control-hint">Type the number of quarters, then click Apply Scenario.</p>
            </div>
            <div className="control-row">
              <label htmlFor="radius">Service radius (km)</label>
              <input
                id="radius"
                type="range"
                min={5}
                max={50}
                value={serviceRadius}
                onChange={(event) => setServiceRadius(Number(event.target.value))}
              />
              <p className="control-hint">{serviceRadius} km coverage target</p>
            </div>
            <div className="control-row">
              <label htmlFor="budgetInput">Budget available (CAD)</label>
              <input
                id="budgetInput"
                type="number"
                min={100000}
                step={100000}
                value={budgetInput}
                onChange={(event) => setBudgetInput(event.target.value)}
              />
              <p className="control-hint">Edit the budget, then click Apply Scenario.</p>
            </div>
            <div className="control-row">
              <label htmlFor="chargerType">New charger type</label>
              <select
                id="chargerType"
                value={chargerType}
                onChange={(event) => setChargerType(event.target.value as 'level2' | 'dc_fast')}
              >
                <option value="level2">Level 2</option>
                <option value="dc_fast">DC Fast</option>
              </select>
            </div>
            <div className="control-row">
              <label htmlFor="fsaSelect">FSA focus</label>
              {hasMultipleFsasInCity ? (
                <select
                  id="fsaSelect"
                  value={selectedRegion?.fsa ?? ''}
                  onChange={(event) => handleSelectFsa(event.target.value)}
                >
                  {cityRegions.map((region) => (
                    <option key={region.fsa} value={region.fsa}>
                      {region.fsa} - {region.city_label}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="control-value" aria-live="polite">
                  {selectedRegion ? `${selectedRegion.fsa} - ${selectedRegion.city_label}` : 'No FSA available'}
                </div>
              )}
            </div>
            <button className="button-primary" type="button" onClick={applyScenario}>
              Apply Scenario
            </button>
          </div>
        </aside>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Current Charger Map</h2>
              <p className="panel-copy">
                This map shows the existing public chargers currently assigned to the selected FSA.
              </p>
              {selectedRegion ? (
                <p className="panel-copy">
                  Selected FSA: <strong>{selectedRegion.fsa} - {selectedRegion.city_label}</strong>
                </p>
              ) : null}
            </div>
            <span className="status">{selectedFsaStations.length} current station{selectedFsaStations.length === 1 ? '' : 's'}</span>
          </div>
          <OntarioMap
            regions={cityRegions}
            currentStations={selectedFsaStations}
            selectedRegion={selectedRegion}
            onSelectRegion={handleSelectFsa}
            serviceRadiusKm={serviceRadius}
          />
          {selectedRegion ? (
            <div className="detail-grid">
              <section className="detail-card">
                <p className="detail-label">Selected Planning Area</p>
                <h3>
                  {selectedRegion.fsa} - {selectedRegion.city_label}
                </h3>
                <p className="detail-copy">
                  One Ontario FSA, which is a postal-code area defined by the first 3 characters of the postal code.
                </p>
              </section>
              <section className="detail-card">
                <p className="detail-label">Current Demand</p>
                <h3>{formatInteger(selectedRegion.current_total_ev)}</h3>
                <p className="detail-copy">Estimated EVs currently registered in this FSA.</p>
              </section>
              <section className="detail-card">
                <p className="detail-label">Forecast Demand</p>
                <h3>{formatInteger(selectedRegion.forecast_total_ev)}</h3>
                <p className="detail-copy">
                  Forecast EVs after {horizonQuarters} quarter{horizonQuarters === 1 ? '' : 's'}.
                </p>
              </section>
              <section className="detail-card">
                <p className="detail-label">Existing Charger Mix</p>
                <h3>
                  {selectedLevel2Ports} L2 / {selectedRegion.fast_ports} Fast
                </h3>
                <p className="detail-copy">
                  {selectedRegion.stations_count} current station{selectedRegion.stations_count === 1 ? '' : 's'} in this FSA.
                </p>
              </section>
              <section className="detail-card">
                <p className="detail-label">Current Reachability</p>
                <h3>{selectedRegion.nearest_existing_km.toFixed(1)} km</h3>
                <p className="detail-copy">Distance from the FSA centroid to the nearest existing charger.</p>
              </section>
              <section className="detail-card">
                <p className="detail-label">Budget Threshold</p>
                <h3>{maxAffordableSites} max site{maxAffordableSites === 1 ? '' : 's'}</h3>
                <p className="detail-copy">
                  With a budget of ${Math.round(budget).toLocaleString()} and a per-site cost of $
                  {Math.round(siteCost).toLocaleString()}, the optimizer can place up to {maxAffordableSites} new site
                  {maxAffordableSites === 1 ? '' : 's'} this period, even if one FSA may need more over the next year.
                </p>
              </section>
            </div>
          ) : null}
        </section>
      </div>

      {selectedRegion ? (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Local Facility Plan For {selectedRegion.fsa}</h2>
              <p className="panel-copy">
                This section solves a local <strong>p-median</strong> siting problem over realistic public-facing
                candidate sites, then nudges the solution toward busier areas so the new placements are more practical.
              </p>
            </div>
            <span className="status">{loadingLocalPlan ? 'Solving local plan' : 'Local plan ready'}</span>
          </div>

          <div className="local-plan-toolbar">
            <div className="local-plan-controls">
              <div className="control-row inline-control">
                <label htmlFor="localNewSites">Requested new sites</label>
                <input
                  id="localNewSites"
                  type="number"
                  min={1}
                  step={1}
                  value={localNewSitesInput}
                  onChange={(event) => setLocalNewSitesInput(event.target.value)}
                />
              </div>
              <div className="control-row inline-control">
                <label htmlFor="localBudget">Local budget for this FSA (CAD)</label>
                <input
                  id="localBudget"
                  type="number"
                  min={0}
                  step={10000}
                  value={localBudgetInput}
                  onChange={(event) => setLocalBudgetInput(event.target.value)}
                />
              </div>
              <button className="button-primary local-apply-button" type="button" onClick={applyLocalScenario}>
                Apply Local Plan
              </button>
            </div>
            <p className="panel-copy">
              The local model minimizes weighted drive distance inside and around <strong>{selectedRegion.fsa}</strong>.
              If the requested site count is larger than the local budget can fund, the model automatically solves for
              the maximum affordable number of sites and shows that tradeoff below.
            </p>
          </div>
          <p className="control-hint">
            Preview: {previewRequestedSites} requested, {previewAffordableSites} affordable, {previewModeledSites} will
            be modeled for {selectedRegion.fsa} at ${Math.round(siteCost).toLocaleString()} per site.
          </p>

          {localPlanError ? <div className="error local-plan-error">{localPlanError}</div> : null}

          <div className="local-plan-grid">
            <div className="local-map-column">
              <LocalSitingMap
                focusRegion={selectedRegion}
                localSites={localPlanSites}
                serviceRadiusKm={serviceRadius}
              />
            </div>
            <div className="local-plan-side">
              <section className={`detail-card feasibility-card feasibility-card-${feasibilityState}`}>
                <p className="detail-label">Feasibility Check</p>
                <h3>{feasibilityTitle}</h3>
                <p className="detail-copy">
                  Budget: ${Math.round(localBudget).toLocaleString()} at ${Math.round(siteCost).toLocaleString()} per
                  site funds {maxLocalAffordableSites} site{maxLocalAffordableSites === 1 ? '' : 's'} in {selectedRegion.fsa}.
                  {localNewSites > maxLocalAffordableSites
                    ? ` The page requested ${localNewSites}, so the model is solving for ${effectiveLocalSites}.`
                    : ' The requested and modeled site counts are aligned.'}
                </p>
              </section>

              <div className="detail-grid local-summary-grid">
                <section className="detail-card">
                  <p className="detail-label">Model</p>
                  <h3>{localPlan?.summary.local_model.toUpperCase() ?? 'P-MEDIAN'}</h3>
                  <p className="detail-copy">
                    Candidate source: {localPlan?.summary.candidate_source ?? 'Open public-facing sites near this FSA.'}
                  </p>
                </section>
                <section className="detail-card">
                  <p className="detail-label">Requested Sites</p>
                  <h3>
                    {localNewSites} requested / {maxLocalAffordableSites} affordable / {effectiveLocalSites} modeled
                  </h3>
                  <p className="detail-copy">
                    {chargerType === 'dc_fast' ? 'DC fast' : 'Level 2'} sites for this FSA after applying the local budget cap.
                  </p>
                </section>
                <section className="detail-card">
                  <p className="detail-label">Average Drive Distance</p>
                  <h3>
                    {localPlan ? `${localPlan.summary.average_drive_before_km.toFixed(1)} -> ${localPlan.summary.average_drive_after_km.toFixed(1)} km` : '--'}
                  </h3>
                  <p className="detail-copy">Weighted average distance before and after the local build plan.</p>
                </section>
                <section className="detail-card">
                  <p className="detail-label">Distance Improvement</p>
                  <h3>{localPlan ? `${localPlan.summary.improvement_pct.toFixed(1)}%` : '--'}</h3>
                  <p className="detail-copy">Estimated reduction in weighted travel distance for nearby forecast demand.</p>
                </section>
                <section className="detail-card">
                  <p className="detail-label">Local Forecast EVs</p>
                  <h3>{localPlan ? formatInteger(localPlan.summary.total_local_forecast_evs) : '--'}</h3>
                  <p className="detail-copy">Forecast EV demand considered by the local siting model around this FSA.</p>
                </section>
                <section className="detail-card">
                  <p className="detail-label">Local Build Cost</p>
                  <h3>{localPlan ? `$${Math.round(localPlan.summary.total_cost).toLocaleString()}` : '--'}</h3>
                  <p className="detail-copy">Scenario cost for the selected number of new sites in this local plan.</p>
                </section>
              </div>
            </div>
          </div>

          <div className="local-sites-table">
            <h3>
              Recommended Placements Inside {selectedRegion.fsa}
              {localPlan ? ` (${localPlan.summary.selected_sites} selected)` : ''}
            </h3>
            {loadingLocalPlan ? (
              <p className="detail-copy">Refreshing recommended placements for the applied local plan.</p>
            ) : localPlanSites.length > 0 ? (
              <table>
                <thead>
                  <tr>
                    <th>Placement</th>
                    <th>Type</th>
                    <th>Busy score</th>
                    <th>Assigned forecast EVs</th>
                    <th>Avg. drive</th>
                    <th>Distance saved</th>
                  </tr>
                </thead>
                <tbody>
                  {localPlanSites.map((site) => (
                    <tr key={site.site_name}>
                      <td>{site.site_name}</td>
                      <td>{site.candidate_type}</td>
                      <td>{site.busy_area_score.toFixed(1)}</td>
                      <td>{Math.round(site.assigned_forecast_evs).toLocaleString()}</td>
                      <td>{site.average_drive_km.toFixed(1)} km</td>
                      <td>{site.distance_savings_km.toFixed(1)} km</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="detail-copy">No placements are currently available for this applied local plan.</p>
            )}
          </div>
        </section>
      ) : null}

      <div className="lower-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Province-Wide EV Outlook</h2>
              <p className="panel-copy">This chart stays as Ontario-wide context while the main planner is filtered city by city.</p>
            </div>
          </div>
          <div className="chart-shell">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeline}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="label" />
                <YAxis tickFormatter={(value) => formatCompact(Number(value))} />
                <Tooltip formatter={(value) => Number(value ?? 0).toLocaleString()} />
                <Area type="monotone" dataKey="total_ev" stroke="#c96e2b" fill="rgba(201,110,43,0.22)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>
    </div>
  )
}
