import DashboardPage from './pages/DashboardPage'

function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Ontario EV Charging Planner</p>
          <h1>Plan EV chargers city by city, then drill down to each FSA.</h1>
        </div>
      </header>
      <DashboardPage />
    </div>
  )
}

export default App
