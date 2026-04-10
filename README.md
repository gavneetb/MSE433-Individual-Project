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

## Interface Design

<img width="1217" height="301" alt="433_image1" src="https://github.com/user-attachments/assets/eef8fb2a-e63e-4d32-90b9-e8bf59002112" />

Figure 1: When a certain area is selected, the area name, FSA, and details regarding EVs and EV charging stations appear.

<img width="1216" height="881" alt="433_image2" src="https://github.com/user-attachments/assets/70b274b7-86b8-4abd-bde3-d5f01b9006d9" />

Figure 2: Province-wide planner takes in the area name, the number of quarters a user may want to forecast for, the service radius, the budget, and the type of charger. Then it outputs information about the area, forecasted data, the type of chargers and maps out the existing chargers.

<img width="1211" height="803" alt="433_image3" src="https://github.com/user-attachments/assets/b4900e6d-51bc-4f18-a464-da41d2637536" />

Figure 3: Local planner that focuses on the area, it takes the number of EV charging stations wanted and the budget available, and outputs information for the new potential sites. This component also has a map that pins where the new charging stations should be installed.

<img width="1181" height="216" alt="433_image4" src="https://github.com/user-attachments/assets/f89e3cbe-6106-42de-9c5f-d25c3bef8407" />

Figure 4: Lists where the charging stations should be placed, the type, the busy score, how many EVs could be going to this station, the average drive length, and how much distance it will save.

<img width="1207" height="361" alt="433_image5" src="https://github.com/user-attachments/assets/031dcb7a-950a-406b-8bf9-13656a8cd093" />
Figure 5: Forecasted output of EV outlook in Ontario


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
