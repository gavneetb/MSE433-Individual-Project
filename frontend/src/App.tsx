import DashboardPage from './pages/DashboardPage'

function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Plan EV chargers city by city, then drill down to each FSA.</p>
          <h1>Ontario EV Charging Planner</h1>
        </div>
      </header>
      <DashboardPage />
    </div>
  )
}

export default App
