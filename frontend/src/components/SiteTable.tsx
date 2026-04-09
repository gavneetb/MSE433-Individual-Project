import type { OptimizationSite } from '../types/api'

type SiteTableProps = {
  title: string
  sites: OptimizationSite[]
}

export default function SiteTable({ title, sites }: SiteTableProps) {
  return (
    <section className="site-table">
      <h2>{title}</h2>
      <table>
        <thead>
          <tr>
            <th>FSA</th>
            <th>Baseline uncovered EVs</th>
            <th>EVs within radius</th>
            <th>Scenario cost</th>
          </tr>
        </thead>
        <tbody>
          {sites.map((site) => (
            <tr key={site.fsa}>
              <td>{site.fsa}</td>
              <td>{Math.round(site.baseline_uncovered_ev).toLocaleString()}</td>
              <td>{Math.round(site.covered_evs_within_radius).toLocaleString()}</td>
              <td>${Math.round(site.site_cost).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
