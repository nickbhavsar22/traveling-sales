# TSP Route Optimizer

## Overview

Streamlit web application that solves the Traveling Salesman Problem (TSP) for US addresses. Users paste a list of addresses, provide a Google Maps API key, and get the optimal driving route minimizing total distance.

## Tech Stack

- **Streamlit** — Web UI framework
- **OR-Tools** — Google's combinatorial optimization solver for TSP
- **Google Maps APIs** — Geocoding (address to lat/lng) + Distance Matrix (driving distances)
- **Folium** — Interactive map visualization (free, no API key needed)
- **Pandas** — Data handling and CSV export

## Entry Point

```bash
streamlit run app.py
```

## Directory Layout

```
app.py                  # Main Streamlit application (UI + orchestration)
tools/
  google_maps_client.py # Geocoding and distance matrix API calls
  tsp_solver.py         # OR-Tools TSP solver
  route_optimizer.py    # Result formatting (ordered stops, legs, totals)
  export.py             # CSV generation and Google Maps URL builder
workflows/
  route_optimization.md # WAT Framework SOP for the optimization pipeline
requirements.txt        # Python dependencies
.env.example            # Template for API key configuration
README.md               # GitHub-facing documentation
```

## WAT Framework Compliance

This project inherits from the parent `d:\Claude\CLAUDE.md` WAT Framework:

- **Workflows** define the optimization pipeline steps in `workflows/route_optimization.md`
- **Agents** (Claude) handle orchestration, sequencing, and error recovery
- **Tools** in `tools/` are deterministic Python scripts for API calls, solving, and formatting

## Key Architecture Decisions

- **OR-Tools solver strategy:** `PATH_CHEAPEST_ARC` for initial solution, `GUIDED_LOCAL_SEARCH` metaheuristic for improvement. Time limit: 30 seconds.
- **Distance matrix batching:** Google Maps Distance Matrix API allows max 100 elements per request. We batch as 10 origins x 10 destinations (100 elements) to stay within limits.
- **User-provided API key:** The API key is entered in the UI by the user, not stored server-side. This avoids billing surprises and keeps secrets out of deployment.
- **Folium for maps:** Free, open-source map rendering. No additional API key or billing required.
- **Preview mode:** Uses haversine (straight-line) distances instead of driving distances. Costs only geocoding fees. Useful for large address lists or cost-conscious users.

## API Cost Notes

Google Maps API pricing (Pay-As-You-Go):
- Geocoding: $5 per 1,000 requests
- Distance Matrix: $5 per 1,000 elements
- Estimated cost for 50 addresses: ~$12.75
- Preview mode (haversine) for 50 addresses: ~$0.25 (geocoding only)

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Deploy via Streamlit Community Cloud directly from the GitHub repository. No server-side secrets needed since users provide their own API key.
