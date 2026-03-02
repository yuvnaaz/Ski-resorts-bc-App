 BC Ski Resort Planner (Flask)

A Flask web app that collects British Columbia ski resort data, scores resorts against rider preferences, and suggests the best day/time window to ride using weather forecasts.

 Features

- Scrapes BC resort stats from `skiresort.info` (terrain mix, vertical, lifts, pass info)
- Caches resort data locally to reduce repeated scraping
- Recommends ranked resorts using preferences such as skill level, terrain mix, budget, drive time, crowd tolerance, and weather sensitivity
- Provides a browser UI for running the planner, comparing top picks, and saving profiles/favorites
- Exposes JSON API endpoints for frontend or external integrations

Tech Stack

- Python 3
- Flask + Flask-CORS
- Requests + BeautifulSoup4
- Gunicorn (production)

 Project Structure

- `app.py`: Main Flask app and API routes
- `resorts_service.py`: Resort scraping + cache management
- `planner_service.py`: Scoring engine, weather lookup, geocoding, and persistence
- `templates/index.html`: Frontend UI
- `static/styles.css`: Frontend styling
- `data/`: Local cache and user-saved files

Quick Start

 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

 2. Install dependencies

```bash
pip install -r requirements.txt
```
 3. Run the app

```bash
python app.py
```

The app starts on `http://127.0.0.1:5000` by default.

API Endpoints

 Health

- `GET /health`
- Returns: `{"status": "ok"}`

 Resort Data

- `GET /api/resorts` (alias: `GET /resorts`)
  - Query: `refresh=1` to force fresh scrape
- `GET /api/resorts/<resort_id>`
  - Query: `refresh=1` to force fresh scrape

 Planner

- `POST /api/planner/recommend`
  - Body supports:
    - `skill_level` (`beginner|intermediate|expert`)
    - `terrain_mix` (`blue`, `red`, `black` percentages)
    - `max_drive_hours`
    - `budget_cad`
    - `crowd_tolerance` (`low|medium|high`)
    - `powder_preference` (`0-10`)
    - `preferred_temp_c`
    - `wind_tolerance_kmh`
    - Optional location: `user_lat`, `user_lon`
    - Optional `refresh_resorts` (boolean)
- Response includes:
  - `results` (ranked list)
  - `compare_top_3`
  - `alert`
  - `computed_at`

 Profiles

- `GET /api/planner/profiles`
- `POST /api/planner/profiles`
  - Body: `{ "name": "...", "preferences": { ... } }`

 Favorites

- `GET /api/planner/favorites`
- `POST /api/planner/favorites`
  - Body: `{ "resort_id": "...", "note": "..." }`

 Example Request

```bash
curl -X POST http://127.0.0.1:5000/api/planner/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "skill_level": "intermediate",
    "terrain_mix": {"blue": 35, "red": 45, "black": 20},
    "max_drive_hours": 5,
    "budget_cad": 260,
    "user_lat": 49.2827,
    "user_lon": -123.1207,
    "powder_preference": 7,
    "preferred_temp_c": -5,
    "wind_tolerance_kmh": 30,
    "crowd_tolerance": "medium"
  }'
```

 Data and Caches

The app writes runtime files under `data/`:

- `bc_resorts_cache.json`: Scraped resort list cache
- `resort_coordinates.json`: Geocoded coordinates cache
- `weather_cache.json`: Forecast cache (short-lived)
- `planner_profiles.json`: Saved profile presets
- `planner_favorites.json`: Saved favorite resorts

These files are generated/updated automatically.

 Legacy Scripts in Repository

This repository also contains older standalone scripts and mini Flask apps (`api.py`, `flaskApi.py`, `data.py`, `data2.py`, `mountainBikedata.py`). The main application entrypoint is `app.py`.

 Deployment

For production serving, use Gunicorn against the Flask app object:

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

 Notes

- The app depends on external services/sites (`skiresort.info`, OpenStreetMap Nominatim, Open-Meteo). Network outages or upstream HTML/API changes can impact freshness or completeness.
- If scraping fails, cached data is used when available.
