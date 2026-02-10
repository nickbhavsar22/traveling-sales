# Route Optimizer - TSP Solver

**Find the shortest driving route through all your stops.**

A web application that takes a list of US addresses and finds the optimal visiting order to minimize total driving distance, using Google OR-Tools and real driving distances from Google Maps.

## Features

- Paste addresses (one per line) and get the optimal route in seconds
- Real driving distances via Google Maps Distance Matrix API
- Interactive map with labeled markers and route polyline
- Per-leg breakdown with distance (miles) and estimated drive time
- CSV download of the optimized route
- Shareable Google Maps directions link
- Preview mode using straight-line distances (minimal API cost)
- Supports up to 50+ addresses

## Quick Start

```bash
git clone https://github.com/your-username/traveling-sales.git
cd traveling-sales
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

## Google Maps API Setup

You need a Google Maps API key with Geocoding and Distance Matrix APIs enabled.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services > Library**
4. Enable **Geocoding API**
5. Enable **Distance Matrix API**
6. Navigate to **APIs & Services > Credentials**
7. Click **Create Credentials > API Key**
8. (Recommended) Restrict the key to only the Geocoding and Distance Matrix APIs
9. Copy the key and paste it into the app when prompted

## Cost Estimates

| Addresses | Geocoding Calls | Matrix Elements | Estimated Cost |
|-----------|----------------|-----------------|----------------|
| 10        | 10             | 100             | $0.75          |
| 25        | 25             | 625             | $3.38          |
| 50        | 50             | 2,500           | $12.75         |

Costs are based on Google Maps Platform [Pay-As-You-Go pricing](https://developers.google.com/maps/billing-and-pricing/pricing). Preview mode (straight-line distances) uses only geocoding, reducing costs significantly.

## Architecture

1. **Geocoding** — Convert each address to latitude/longitude using Google Maps Geocoding API
2. **Distance Matrix** — Build an NxN matrix of real driving distances, batched in 10x10 blocks (100 elements per API call)
3. **TSP Solver** — Google OR-Tools finds the optimal route using `PATH_CHEAPEST_ARC` initial strategy and `GUIDED_LOCAL_SEARCH` metaheuristic
4. **Visualization** — Results displayed on an interactive Folium map with an ordered stop list, total distance, and estimated time

## Deploy to Streamlit Cloud

1. Push this repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io/)
3. Click **New app**
4. Select your repository, branch (`main`), and main file (`app.py`)
5. Click **Deploy**

No server-side secrets are needed. Users provide their own Google Maps API key in the app interface.

## Tech Stack

- [Streamlit](https://streamlit.io/) — Web UI
- [Google OR-Tools](https://developers.google.com/optimization) — TSP solver
- [Google Maps Platform](https://developers.google.com/maps) — Geocoding + Distance Matrix
- [Folium](https://python-visualization.github.io/folium/) — Interactive maps
- [Pandas](https://pandas.pydata.org/) — Data handling

## License

MIT
