# Donna's Drive Time

## Overview

Streamlit web application that solves the Traveling Salesman Problem (TSP) for US addresses. Users paste a list of addresses and get the optimal driving route minimizing total distance. The Google Maps API key is managed server-side via Streamlit Secrets -- users never need to provide one.

## Tech Stack

- **Streamlit** -- Web UI framework
- **OR-Tools** -- Google's combinatorial optimization solver for TSP
- **Google Maps APIs** -- Geocoding (address to lat/lng) + Distance Matrix (driving distances)
- **Folium** -- Interactive map visualization (free, no API key needed)
- **Pandas** -- Data handling and CSV export

## Entry Point

```bash
streamlit run app.py
```

## Directory Layout

```
app.py                  # Main Streamlit application (UI + orchestration + export)
tools/
  google_maps_client.py # Geocoding and distance matrix API calls
  tsp_solver.py         # OR-Tools TSP solver
workflows/
  route_optimization.md # WAT Framework SOP for the optimization pipeline
requirements.txt        # Python dependencies
.streamlit/
  config.toml           # Theme and server configuration
  secrets.toml          # Google Maps API key (gitignored)
README.md               # GitHub-facing documentation
```

## UI Layout

All controls and results are inline -- there is no sidebar. The flow is:

1. User pastes addresses into a text area
2. User clicks "Optimize Route"
3. Results display inline: map, ordered stop list, per-leg breakdown, export options

## Caching Strategy

- **Geocoding:** `@st.cache_data` with per-address caching and 1-hour TTL. Each unique address is cached individually so repeat lookups are free.
- **Distance Matrix:** `@st.cache_data` on the full matrix request. If the same set of addresses is optimized again within the TTL, no API calls are made.
- Caching reduces repeat costs to $0 for previously seen address sets.

## Address Limit

Maximum **50 addresses** per optimization run. This keeps API costs manageable and solver time reasonable.

## Security

- **API key:** Stored in `.streamlit/secrets.toml` (gitignored) and accessed via `st.secrets["GOOGLE_MAPS_API_KEY"]`. Never exposed to the client.
- **HTML escaping:** All user-provided text (addresses, labels) is HTML-escaped before rendering in Folium map popups to prevent XSS.
- **CSV sanitization:** Exported CSV values are sanitized to prevent formula injection (cells starting with `=`, `+`, `-`, `@` are prefixed).
- **Rate limiting:** API calls are rate-limited to prevent abuse and runaway costs.

## Color Palette -- "Sunset Road Trip"

| Role      | Color   | Hex       |
|-----------|---------|-----------|
| Primary   | Coral   | `#E8654A` |
| Accent    | Teal    | `#2A9D8F` |
| Highlight | Gold    | `#E9A820` |

## Key Architecture Decisions

- **OR-Tools solver strategy:** `PATH_CHEAPEST_ARC` for initial solution, `GUIDED_LOCAL_SEARCH` metaheuristic for improvement. Time limit: 30 seconds.
- **Distance matrix batching:** Google Maps Distance Matrix API allows max 100 elements per request. We batch as 10 origins x 10 destinations (100 elements) to stay within limits.
- **Server-side API key:** The API key is stored in Streamlit Secrets, not provided by the user. The app owner is responsible for billing.
- **Folium for maps:** Free, open-source map rendering. No additional API key or billing required.

## API Cost Notes

Google Maps API pricing (Pay-As-You-Go). The app owner pays these costs:

| Addresses | Geocoding Calls | Matrix Elements | Estimated Cost |
|-----------|----------------|-----------------|----------------|
| 10        | 10             | 100             | ~$0.75         |
| 25        | 25             | 625             | ~$3.38         |
| 50        | 50             | 2,500           | ~$12.75        |

Caching reduces repeat costs to $0 for previously seen addresses.

## WAT Framework Compliance

This project inherits from the parent `d:\Claude\CLAUDE.md` WAT Framework:

- **Workflows** define the optimization pipeline steps in `workflows/route_optimization.md`
- **Agents** (Claude) handle orchestration, sequencing, and error recovery
- **Tools** in `tools/` are deterministic Python scripts for API calls, solving, and formatting

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment

Deploy via Streamlit Community Cloud. Set `GOOGLE_MAPS_API_KEY` in the Streamlit Secrets dashboard (Settings > Secrets).
