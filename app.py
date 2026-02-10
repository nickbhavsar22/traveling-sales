import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import math
import csv
import io
import urllib.parse

from tools.google_maps_client import GoogleMapsClient
from tools.tsp_solver import solve_tsp

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Route Optimizer - TSP Solver",
    page_icon="\U0001f5fa\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_defaults = {
    "api_key": "",
    "home_address": "",
    "addresses_text": "",
    "geocoded": None,
    "failed_addresses": [],
    "distance_matrix_result": None,
    "route_result": None,
}
for key, value in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def get_stop_label(index: int) -> str:
    """Convert 0-based index to letter label: 0=A, 1=B, ..., 25=Z, 26=AA, etc."""
    if index < 26:
        return chr(65 + index)
    else:
        return chr(65 + index // 26 - 1) + chr(65 + index % 26)


def meters_to_miles(meters: float) -> float:
    return meters / 1609.344


def seconds_to_hm(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def route_to_csv(ordered_addresses, leg_distances_mi, leg_durations_sec, labels):
    """Generate a CSV string for the optimized route."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["#", "Label", "Address", "Leg Distance (mi)", "Leg Duration"])
    for i, addr in enumerate(ordered_addresses):
        if i < len(leg_distances_mi):
            dist = f"{leg_distances_mi[i]:.1f}"
            dur = seconds_to_hm(leg_durations_sec[i])
        else:
            dist = ""
            dur = "-- END --"
        writer.writerow([i + 1, labels[i], addr, dist, dur])
    return buf.getvalue()


def generate_google_maps_url(ordered_addresses, return_to_start: bool) -> str:
    """Build a Google Maps directions URL for the optimized route."""
    if not ordered_addresses:
        return ""
    origin = urllib.parse.quote_plus(ordered_addresses[0])
    if return_to_start:
        destination = origin
        waypoints_list = ordered_addresses[1:]
    else:
        destination = urllib.parse.quote_plus(ordered_addresses[-1])
        waypoints_list = ordered_addresses[1:-1]
    waypoints = "|".join(urllib.parse.quote_plus(a) for a in waypoints_list)
    url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin}"
        f"&destination={destination}"
    )
    if waypoints:
        url += f"&waypoints={waypoints}"
    url += "&travelmode=driving"
    return url


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Route Optimizer")
    st.caption("Minimize driving distance for your route")

    api_key = st.text_input(
        "Google Maps API Key",
        type="password",
        value=st.session_state.api_key,
        key="sidebar_api_key",
    )
    st.session_state.api_key = api_key

    st.divider()
    st.subheader("Settings")

    return_to_start = st.checkbox("Return to starting address", value=True)
    preview_mode = st.checkbox(
        "Preview mode (straight-line distances)",
        value=False,
        help="Uses the haversine formula for distance estimates. Free -- no API cost for the distance matrix.",
    )
    time_limit = st.slider("Solver time limit (seconds)", min_value=5, max_value=60, value=30)

    st.divider()
    st.caption("Built with OR-Tools + Google Maps API")


# ---------------------------------------------------------------------------
# Main content -- input section
# ---------------------------------------------------------------------------
st.header("Plan Your Route")

col_home, col_stops = st.columns([1, 2])

with col_home:
    home_address = st.text_input(
        "Home / Starting Address",
        value=st.session_state.home_address,
        key="input_home_address",
        placeholder="e.g. 123 Main St, City, State",
    )
    st.session_state.home_address = home_address

with col_stops:
    addresses_text = st.text_area(
        "Paste stop addresses (one per line)",
        value=st.session_state.addresses_text,
        key="input_addresses_text",
        height=300,
        placeholder="456 Oak Ave, City, State\n789 Elm Dr, City, State\n...",
    )
    st.session_state.addresses_text = addresses_text

# Parse addresses
stop_lines = [line.strip() for line in addresses_text.strip().splitlines() if line.strip()]
all_addresses = []
if home_address.strip():
    all_addresses.append(home_address.strip())
all_addresses.extend(stop_lines)

n_total = len(all_addresses)
n_stops = len(stop_lines)

if n_total >= 2:
    matrix_elements = n_total * n_total
    # Distance Matrix API: $5 per 1000 elements (standard pricing)
    estimated_cost = (matrix_elements / 1000) * 5.0
    cost_str = f"~${estimated_cost:.2f}" if not preview_mode else "$0.00 (preview mode)"
    st.info(
        f"**{n_total}** total addresses (1 home + {n_stops} stops). "
        f"Distance matrix: {n_total}x{n_total} = {matrix_elements} elements. "
        f"Estimated API cost: {cost_str}"
    )

# ---------------------------------------------------------------------------
# Optimize button
# ---------------------------------------------------------------------------
show_button = bool(api_key.strip()) and n_total >= 2

if not api_key.strip() and n_total < 2:
    st.info("Enter your Google Maps API key in the sidebar and add at least two addresses to begin.")
elif not api_key.strip():
    st.info("Enter your Google Maps API key in the sidebar to begin.")

if show_button:
    if st.button("Optimize Route", type="primary", use_container_width=True):
        # Clear previous results
        st.session_state.route_result = None

        client = GoogleMapsClient(api_key)

        # Step 1 -- Geocode
        with st.spinner("Geocoding addresses..."):
            geocoded = client.geocode_addresses(all_addresses)

        failed = [g for g in geocoded if g["status"] != "OK"]
        successful = [g for g in geocoded if g["status"] == "OK"]
        st.session_state.geocoded = geocoded
        st.session_state.failed_addresses = failed

        if failed:
            failed_names = ", ".join(f['input_address'] for f in failed)
            st.warning(f"Could not geocode {len(failed)} address(es): {failed_names}")

        if len(successful) < 2:
            st.error("Need at least 2 successfully geocoded addresses to compute a route.")
            st.stop()

        # Build an index map: original position -> position in successful list
        success_indices = [i for i, g in enumerate(geocoded) if g["status"] == "OK"]

        # Step 2 -- Distance matrix
        if preview_mode:
            with st.spinner("Computing straight-line distances..."):
                distance_matrix = client.build_haversine_matrix(successful)
                # Approximate durations: assume 40 mph average
                duration_matrix = [
                    [int(d / 1609.344 / 40 * 3600) for d in row] for row in distance_matrix
                ]
        else:
            with st.spinner("Computing distance matrix..."):
                distance_matrix, duration_matrix = client.build_distance_matrix(
                    successful, mode="driving"
                )

        st.session_state.distance_matrix_result = {
            "distance": distance_matrix,
            "duration": duration_matrix,
        }

        # Step 3 -- Solve TSP
        # The depot is the home address, which is index 0 in the successful list
        # (assuming home geocoded successfully). If home failed, depot defaults to 0.
        depot = 0
        if 0 in success_indices:
            depot = success_indices.index(0)

        with st.spinner("Solving optimal route..."):
            result = solve_tsp(
                distance_matrix=distance_matrix,
                depot=depot,
                return_to_depot=return_to_start,
                time_limit_seconds=time_limit,
            )

        if result is None:
            st.error("No feasible route found. Check your addresses and try again.")
            st.stop()

        # Attach extra data to the result for display
        result["successful_geocoded"] = successful
        result["duration_matrix"] = duration_matrix
        result["distance_matrix"] = distance_matrix
        result["depot"] = depot
        result["return_to_start"] = return_to_start

        st.session_state.route_result = result


# ---------------------------------------------------------------------------
# Results section
# ---------------------------------------------------------------------------
if st.session_state.route_result is not None:
    result = st.session_state.route_result
    route = result["route"]
    geocoded_list = result["successful_geocoded"]
    dist_matrix = result["distance_matrix"]
    dur_matrix = result["duration_matrix"]
    depot = result["depot"]
    rts = result["return_to_start"]

    st.divider()
    st.header("Optimized Route")

    # Compute per-leg distances and durations
    leg_distances = []
    leg_durations = []
    for i in range(len(route) - 1):
        leg_distances.append(dist_matrix[route[i]][route[i + 1]])
        leg_durations.append(dur_matrix[route[i]][route[i + 1]])

    total_distance_m = result["total_distance"]
    total_distance_mi = meters_to_miles(total_distance_m)
    total_duration_s = sum(leg_durations)

    # --- Summary metrics ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Distance", f"{total_distance_mi:.1f} mi")
    m2.metric("Total Time", seconds_to_hm(total_duration_s))
    m3.metric("Number of Stops", len(route) - (2 if rts else 1))
    m4.metric("Solver Status", result["solver_status"])

    st.divider()

    # --- Map and table ---
    col_map, col_table = st.columns([3, 2])

    # Build ordered addresses, labels, and coordinates for display
    ordered_addresses = []
    ordered_coords = []
    labels = []
    stop_counter = 0

    for idx, node in enumerate(route):
        geo = geocoded_list[node]
        ordered_addresses.append(geo["formatted_address"] or geo["input_address"])
        ordered_coords.append((geo["lat"], geo["lng"]))

        if node == depot:
            labels.append("H")
        else:
            labels.append(get_stop_label(stop_counter))
            stop_counter += 1

    # If returning to start, the last entry is also home
    if rts and len(labels) >= 2:
        labels[-1] = "H"
        # Reset stop counter -- last was depot, not a new stop
        # (stop_counter is already correct since we skip depot assignment above)

    with col_map:
        st.subheader("Route Map")

        # Center map on midpoint of all coordinates
        avg_lat = sum(c[0] for c in ordered_coords) / len(ordered_coords)
        avg_lng = sum(c[1] for c in ordered_coords) / len(ordered_coords)

        m = folium.Map(location=[avg_lat, avg_lng], zoom_start=10)

        # Add markers
        seen_depot = False
        stop_label_idx = 0
        for idx, node in enumerate(route):
            geo = geocoded_list[node]
            lat, lng = geo["lat"], geo["lng"]
            addr = geo["formatted_address"] or geo["input_address"]

            if node == depot:
                if seen_depot and rts:
                    # Return-home marker (end of route), skip duplicate
                    continue
                seen_depot = True
                # Home marker -- green, larger
                icon_html = (
                    '<div style="'
                    "background-color: #28a745;"
                    "color: white;"
                    "border-radius: 50%;"
                    "width: 30px;"
                    "height: 30px;"
                    "display: flex;"
                    "align-items: center;"
                    "justify-content: center;"
                    "font-weight: bold;"
                    "font-size: 14px;"
                    "border: 2px solid white;"
                    "box-shadow: 0 1px 4px rgba(0,0,0,0.4);"
                    '">H</div>'
                )
                folium.Marker(
                    location=[lat, lng],
                    popup=folium.Popup(f"<b>HOME</b><br>{addr}", max_width=250),
                    icon=folium.DivIcon(
                        html=icon_html,
                        icon_size=(30, 30),
                        icon_anchor=(15, 15),
                    ),
                ).add_to(m)
            else:
                label = get_stop_label(stop_label_idx)
                stop_label_idx += 1
                # Stop marker -- blue
                icon_html = (
                    '<div style="'
                    "background-color: #007bff;"
                    "color: white;"
                    "border-radius: 50%;"
                    "width: 26px;"
                    "height: 26px;"
                    "display: flex;"
                    "align-items: center;"
                    "justify-content: center;"
                    "font-weight: bold;"
                    "font-size: 12px;"
                    "border: 2px solid white;"
                    "box-shadow: 0 1px 4px rgba(0,0,0,0.4);"
                    f'">{label}</div>'
                )
                folium.Marker(
                    location=[lat, lng],
                    popup=folium.Popup(f"<b>Stop {label}</b><br>{addr}", max_width=250),
                    icon=folium.DivIcon(
                        html=icon_html,
                        icon_size=(26, 26),
                        icon_anchor=(13, 13),
                    ),
                ).add_to(m)

        # Draw route polyline
        route_line = [(geocoded_list[node]["lat"], geocoded_list[node]["lng"]) for node in route]
        folium.PolyLine(
            route_line,
            color="red",
            weight=3,
            dash_array="10",
            opacity=0.8,
        ).add_to(m)

        # Auto-zoom to fit all markers
        bounds = [[c[0], c[1]] for c in ordered_coords]
        m.fit_bounds(bounds)

        st_folium(m, width=700, height=500, returned_objects=[])

    with col_table:
        st.subheader("Stop Order")

        leg_distances_mi = [meters_to_miles(d) for d in leg_distances]

        table_rows = []
        for i, (addr, label) in enumerate(zip(ordered_addresses, labels)):
            if rts and i == len(ordered_addresses) - 1:
                # Last stop is return to home -- skip from table if desired,
                # or show it as the final entry
                next_leg = "-- END --"
            elif i < len(leg_distances_mi):
                next_leg = f"{leg_distances_mi[i]:.1f} mi / {seconds_to_hm(leg_durations[i])}"
            else:
                next_leg = "-- END --"

            table_rows.append({
                "#": i + 1,
                "Label": label,
                "Address": addr,
                "Next Leg": next_leg,
            })

        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # --- Export section ---
    st.divider()
    st.subheader("Export")

    col_csv, col_gmaps = st.columns(2)

    with col_csv:
        csv_data = route_to_csv(
            ordered_addresses,
            leg_distances_mi,
            [leg_durations[i] if i < len(leg_durations) else 0 for i in range(len(ordered_addresses))],
            labels,
        )
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="optimized_route.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_gmaps:
        gmaps_url = generate_google_maps_url(ordered_addresses, rts)
        st.markdown(f"[Open in Google Maps]({gmaps_url})")

        # Google Maps supports max ~11 waypoints in URLs
        n_waypoints = len(ordered_addresses) - 2  # minus origin and destination
        if n_waypoints > 11:
            st.warning(
                f"Your route has {n_waypoints} waypoints. Google Maps URLs support "
                f"a maximum of ~11 waypoints. The link may not include all stops."
            )
