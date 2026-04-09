# Ontario EV Charging Planner

Full-stack course project for forecasting Ontario EV demand and recommending new public charging sites.

## Stack

- Frontend: React + TypeScript + Vite + React Leaflet + Recharts
- Backend: FastAPI + pandas + scikit-learn + PuLP
- Forecasting: panel-style EV demand forecast by FSA with `GradientBoostingRegressor` and `LinearRegression` baseline
- Optimization: budget-aware maximal coverage style ILP over FSA centroid candidate sites

## Data Sources

- Ontario EV registrations by FSA: Ontario open data catalogue
- Charging infrastructure:
  - Primary path: NREL Alternative Fuel Stations API when `NREL_API_KEY` is provided
  - Default fallback: Overpass / OpenStreetMap Ontario charging-station query for a no-key startup path

## App Structure

- `backend/app/main.py`: FastAPI app and API routes
- `backend/app/services/data_loader.py`: data ingestion, caching, FSA centroids, charger aggregation
- `backend/app/services/forecasting.py`: EV demand forecasting
- `backend/app/services/optimization.py`: charger siting optimization
- `frontend/src/pages/DashboardPage.tsx`: main planner view

## API Routes

- `GET /api/health`
- `GET /api/overview?horizon_quarters=4`
- `GET /api/regions?horizon_quarters=4`
- `GET /api/stations`
- `GET /api/timeline?horizon_quarters=4`
- `POST /api/local-plan`

Example local-plan payload:

```json
{
  "focus_fsa": "L6H",
  "horizon_quarters": 4,
  "service_radius_km": 15,
  "new_site_count": 3,
  "charger_type": "level2"
}
```

## Run Locally

Backend:

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000`. You can override that with `frontend/.env`.

## Notes

- The local siting model keeps the course-aligned `p-median` logic and adds a busy-area score over realistic public-facing candidate sites.
- The first backend startup can take longer because it caches Ontario EV history, centroid data, charging-station supply data, and local candidate-site lookups.
- If you add a real NREL API key in `backend/.env`, the backend will prefer NREL over the no-key fallback.
