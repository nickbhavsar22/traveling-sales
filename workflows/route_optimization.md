# Route Optimization Workflow

## Objective
Optimize visiting order for US addresses to minimize total driving distance.

## Inputs
- Google Maps API key (user-provided via UI)
- Home/starting address
- List of addresses to visit (pasted, one per line)

## Tool Sequence
1. `tools/google_maps_client.py` — Geocode all addresses to lat/lng
2. `tools/google_maps_client.py` — Build NxN distance matrix (batched 10x10)
3. `tools/tsp_solver.py` — Solve TSP with OR-Tools
4. `tools/route_optimizer.py` — Format results (ordered stops, legs, totals)
5. `tools/export.py` — Generate CSV and Google Maps URL

## Outputs
- Interactive Folium map with labeled markers (A, B, C...) and route polyline
- Ordered stop list with per-leg distance (mi) and time
- Total route distance and time
- CSV download
- Shareable Google Maps link (max 9 waypoints)

## Edge Cases
- Failed geocoding: warn user, skip address, re-index
- API rate limits: googlemaps client handles automatic retry
- >50 addresses: warn about cost, suggest preview mode
- Single address: return trivially
- Invalid/missing API key: clear error message

## Cost Notes
- Geocoding: $5/1,000 requests
- Distance Matrix: $5/1,000 elements
- 50 addresses: ~$12.75 total
- Preview mode (haversine): $0.25 (geocoding only)
