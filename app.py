import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import html
import csv
import io
import time
import urllib.parse

from tools.google_maps_client import GoogleMapsClient
from tools.tsp_solver import solve_tsp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_STOPS = 50

DEMO_HOME = "Texas State Capitol, Austin, TX"
DEMO_STOPS = """Zilker Park, Austin, TX
The Domain, Austin, TX
Mueller Lake Park, Austin, TX
Barton Springs Pool, Austin, TX
Austin-Bergstrom International Airport, Austin, TX
Lady Bird Lake Trail, Austin, TX
Mount Bonnell, Austin, TX"""

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Donna's Drive Time",
    page_icon="\U0001F697",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #2D2D2D !important; }

    /* Primary button */
    .stButton > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #E8654A 0%, #C74E36 100%) !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(232, 101, 74, 0.3) !important;
    }

    /* Form submit button (primary) */
    .stFormSubmitButton > button,
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        background: linear-gradient(135deg, #E8654A 0%, #C74E36 100%) !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 12px rgba(232, 101, 74, 0.3) !important;
    }

    /* Input fields */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        border: 2px solid #E8DDD4 !important;
        border-radius: 8px !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #E8654A !important;
        box-shadow: 0 0 0 3px rgba(232, 101, 74, 0.1) !important;
    }

    /* Map container */
    iframe[title="streamlit_folium.st_folium"] {
        border-radius: 12px !important;
        border: 1px solid #E8DDD4 !important;
    }

    /* Download button */
    .stDownloadButton > button {
        border: 2px solid #E8DDD4 !important;
        border-radius: 8px !important;
    }

    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Mobile */
    @media (max-width: 768px) {
        iframe[title="streamlit_folium.st_folium"] { height: 350px !important; }
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# API key from Streamlit Secrets
# ---------------------------------------------------------------------------
def get_api_key():
    try:
        return st.secrets["GOOGLE_MAPS_API_KEY"]
    except (KeyError, FileNotFoundError):
        return None


api_key = get_api_key()
if not api_key:
    st.error("App not configured. The app owner must set GOOGLE_MAPS_API_KEY in Streamlit Secrets.")
    st.stop()


# ---------------------------------------------------------------------------
# Caching functions
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def cached_geocode(address: str, _api_key: str) -> dict:
    """Cache geocoding per individual address."""
    client = GoogleMapsClient(_api_key)
    results = client.geocode_addresses([address])
    return results[0]


@st.cache_data(show_spinner=False, ttl=3600)
def cached_distance_matrix(locations_tuple: tuple, _api_key: str):
    """Cache distance matrix keyed on the set of coordinates."""
    locations = [{"lat": lat, "lng": lng} for lat, lng in locations_tuple]
    client = GoogleMapsClient(_api_key)
    return client.build_distance_matrix(locations)


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


def sanitize_csv_value(value: str) -> str:
    """Prevent CSV injection by prefixing dangerous characters with a single quote."""
    if isinstance(value, str) and value and value[0] in ('=', '@', '+', '-'):
        return "'" + value
    return value


def route_to_csv(ordered_addresses, leg_distances_mi, leg_durations_sec, labels):
    """Generate a CSV string for the optimized route."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["#", "Label", "Address", "Leg Distance (mi)", "Leg Duration"])
    for i, addr in enumerate(ordered_addresses):
        safe_addr = sanitize_csv_value(addr)
        safe_label = sanitize_csv_value(labels[i])
        if i < len(leg_distances_mi):
            dist = f"{leg_distances_mi[i]:.1f}"
            dur = seconds_to_hm(leg_durations_sec[i])
        else:
            dist = ""
            dur = "-- END --"
        writer.writerow([i + 1, safe_label, safe_addr, dist, dur])
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
# Session state defaults
# ---------------------------------------------------------------------------
_defaults = {
    "home_address": "",
    "addresses_text": "",
    "route_result": None,
    "last_optimize_time": 0.0,
}
for key, value in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------------------------
# Brand header
# ---------------------------------------------------------------------------
st.markdown("""
<div style="display: flex; align-items: center; gap: 16px; padding: 8px 0 24px 0;">
    <div style="background: linear-gradient(135deg, #E8654A 0%, #E9A820 100%); border-radius: 16px; width: 56px; height: 56px; display: flex; align-items: center; justify-content: center; font-size: 28px; box-shadow: 0 4px 12px rgba(232, 101, 74, 0.3); flex-shrink: 0;">&#x1F697;</div>
    <div>
        <h1 style="margin: 0; padding: 0; font-size: 2rem; font-weight: 800; color: #2D2D2D; line-height: 1.1;">Donna's Drive Time</h1>
        <p style="margin: 4px 0 0 0; color: #6B6B6B; font-size: 1.05rem;">Find the fastest driving order for all your stops</p>
    </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Demo data button (outside the form)
# ---------------------------------------------------------------------------
if st.button("Load demo addresses"):
    st.session_state.home_address = DEMO_HOME
    st.session_state.addresses_text = DEMO_STOPS
    st.session_state.route_result = None
    st.rerun()


# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------
with st.form("route_form"):
    home_address = st.text_input(
        "Home / Starting Address",
        value=st.session_state.home_address,
        placeholder="e.g. 123 Main St, City, State",
    )

    addresses_text = st.text_area(
        "Stop addresses (one per line)",
        value=st.session_state.addresses_text,
        height=250,
        placeholder="456 Oak Ave, City, State\n789 Elm Dr, City, State\n...",
    )

    return_to_start = st.checkbox("End back at home", value=True)

    submitted = st.form_submit_button("Optimize Route", type="primary", use_container_width=True)


# ---------------------------------------------------------------------------
# Parse addresses and show info below the form
# ---------------------------------------------------------------------------
stop_lines = [line.strip() for line in addresses_text.strip().splitlines() if line.strip()]
n_stops = len(stop_lines)

all_addresses = []
if home_address.strip():
    all_addresses.append(home_address.strip())
all_addresses.extend(stop_lines)

n_total = len(all_addresses)

# Address counter
over_limit = n_stops > MAX_STOPS
if n_stops >= 40 and not over_limit:
    st.markdown(
        f'<p style="color: #E8654A; font-weight: 600;">{n_stops} of {MAX_STOPS} stops</p>',
        unsafe_allow_html=True,
    )
elif over_limit:
    st.error(f"Maximum {MAX_STOPS} stop addresses allowed. Please reduce your list.")
else:
    st.caption(f"{n_stops} of {MAX_STOPS} stops")

# Estimated API cost
if n_total >= 2 and not over_limit:
    matrix_elements = n_total * n_total
    geocode_cost = n_total * 0.005
    matrix_cost = (matrix_elements / 1000) * 5.0
    estimated_cost = geocode_cost + matrix_cost
    st.caption(f"Estimated cost: ~${estimated_cost:.2f}")


# ---------------------------------------------------------------------------
# Advanced settings (outside form)
# ---------------------------------------------------------------------------
with st.expander("Advanced settings"):
    time_limit = st.slider("Solver time limit (seconds)", 5, 60, 30)


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
if st.session_state.route_result is None and n_total < 2:
    st.markdown("""
    <div style="text-align: center; padding: 48px 24px; margin: 32px 0;">
        <div style="font-size: 4rem; margin-bottom: 16px;">&#x1F697;</div>
        <h2 style="color: #2D2D2D; font-weight: 700; margin-bottom: 8px;">Ready to hit the road?</h2>
        <p style="color: #6B6B6B; font-size: 1.1rem; max-width: 500px; margin: 0 auto 24px auto; line-height: 1.6;">
            Enter your starting address and all the stops you need to make. We'll find the shortest driving route so you spend less time behind the wheel.
        </p>
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Optimize route
# ---------------------------------------------------------------------------
if submitted:
    # Save inputs to session state
    st.session_state.home_address = home_address
    st.session_state.addresses_text = addresses_text
    st.session_state.route_result = None

    # Validation
    if over_limit:
        st.error(f"Maximum {MAX_STOPS} stop addresses allowed. Please reduce your list.")
        st.stop()

    if n_total < 2:
        st.warning("Enter a home address and at least one stop address to optimize a route.")
        st.stop()

    # Rate limiting: 30-second cooldown
    now = time.time()
    elapsed = now - st.session_state.last_optimize_time
    if elapsed < 30:
        remaining = int(30 - elapsed)
        st.warning(f"Please wait {remaining} seconds before optimizing again.")
        st.stop()

    st.session_state.last_optimize_time = now

    # ---- Progress-based optimization ----
    progress = st.progress(0, text="Getting ready...")

    # Step 1: Geocode addresses individually (with caching)
    progress.progress(10, text="Looking up your addresses...")

    geocoded = []
    cache_hits = 0
    cache_misses = 0
    for addr in all_addresses:
        # Check if result is already cached by attempting the call
        # (st.cache_data handles the caching transparently)
        result = cached_geocode(addr, api_key)
        geocoded.append(result)

    # Determine cache stats: we count successes as the total;
    # exact cache/miss tracking requires deeper hooks, so we report totals.
    failed = [g for g in geocoded if g["status"] != "OK"]
    successful = [g for g in geocoded if g["status"] == "OK"]

    progress.progress(40, text=f"Found {len(successful)} of {n_total} addresses")

    if failed:
        failed_names = ", ".join(html.escape(f["input_address"]) for f in failed)
        st.warning(f"Could not geocode {len(failed)} address(es): {failed_names}")

    if len(successful) < 2:
        progress.empty()
        st.error("Need at least 2 successfully geocoded addresses to compute a route.")
        st.stop()

    # Build index mapping from geocoded list to successful-only list
    success_indices = [i for i, g in enumerate(geocoded) if g["status"] == "OK"]

    # Step 2: Distance matrix
    progress.progress(50, text="Getting real driving distances...")

    locations_tuple = tuple((g["lat"], g["lng"]) for g in successful)
    distance_matrix, duration_matrix = cached_distance_matrix(locations_tuple, api_key)

    progress.progress(75, text="Distances computed. Finding the best route...")

    # Step 3: Solve TSP
    depot = 0
    if 0 in success_indices:
        depot = success_indices.index(0)

    progress.progress(90, text="Almost there...")

    result = solve_tsp(
        distance_matrix=distance_matrix,
        depot=depot,
        return_to_depot=return_to_start,
        time_limit_seconds=time_limit,
    )

    if result is None:
        progress.empty()
        st.error("No feasible route found. Check your addresses and try again.")
        st.stop()

    # Attach extra data
    result["successful_geocoded"] = successful
    result["duration_matrix"] = duration_matrix
    result["distance_matrix"] = distance_matrix
    result["depot"] = depot
    result["return_to_start"] = return_to_start

    st.session_state.route_result = result

    progress.progress(100, text="Route optimized!")
    time.sleep(0.5)
    progress.empty()


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

    # Compute per-leg distances and durations
    leg_distances = []
    leg_durations = []
    for i in range(len(route) - 1):
        leg_distances.append(dist_matrix[route[i]][route[i + 1]])
        leg_durations.append(dur_matrix[route[i]][route[i + 1]])

    total_distance_m = result["total_distance"]
    total_distance_mi = meters_to_miles(total_distance_m)
    total_duration_s = sum(leg_durations)

    # Compute savings vs naive (input order)
    naive_distance = 0
    for i in range(len(geocoded_list) - 1):
        naive_distance += dist_matrix[i][i + 1]
    if rts:
        naive_distance += dist_matrix[len(geocoded_list) - 1][0]

    savings_pct = ((naive_distance - total_distance_m) / naive_distance * 100) if naive_distance > 0 else 0
    savings_mi = meters_to_miles(naive_distance - total_distance_m)

    # Number of stops (excluding home and return-home)
    num_stops = len(route) - (2 if rts else 1)

    # ---- Hero metric cards ----
    st.markdown(f"""
    <div style="display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 200px; background: linear-gradient(135deg, #E8654A 0%, #C74E36 100%); border-radius: 12px; padding: 20px 24px; color: white; box-shadow: 0 4px 12px rgba(232, 101, 74, 0.3);">
            <div style="font-size: 0.85rem; opacity: 0.9; margin-bottom: 4px;">Total Distance</div>
            <div style="font-size: 1.8rem; font-weight: 800; line-height: 1.2;">{total_distance_mi:.1f} mi</div>
            <div style="font-size: 0.75rem; opacity: 0.8; margin-top: 4px;">Saved {savings_pct:.0f}% vs. original order</div>
        </div>
        <div style="flex: 1; min-width: 200px; background: linear-gradient(135deg, #2A9D8F 0%, #21867A 100%); border-radius: 12px; padding: 20px 24px; color: white; box-shadow: 0 4px 12px rgba(42, 157, 143, 0.3);">
            <div style="font-size: 0.85rem; opacity: 0.9; margin-bottom: 4px;">Total Drive Time</div>
            <div style="font-size: 1.8rem; font-weight: 800; line-height: 1.2;">{seconds_to_hm(total_duration_s)}</div>
        </div>
        <div style="flex: 1; min-width: 200px; background: white; border-radius: 12px; padding: 20px 24px; color: #2D2D2D; border: 2px solid #E8DDD4;">
            <div style="font-size: 0.85rem; color: #6B6B6B; margin-bottom: 4px;">Stops</div>
            <div style="font-size: 1.8rem; font-weight: 800; line-height: 1.2;">{num_stops}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Solver status caption
    status_labels = {"OPTIMAL": "Best route found", "FEASIBLE": "Good route found", "TRIVIAL": "Direct route"}
    st.caption(status_labels.get(result["solver_status"], result["solver_status"]))

    # ---- Build ordered addresses, labels, and coordinates ----
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

    if rts and len(labels) >= 2:
        labels[-1] = "H"

    # ---- Full-width map ----
    avg_lat = sum(c[0] for c in ordered_coords) / len(ordered_coords)
    avg_lng = sum(c[1] for c in ordered_coords) / len(ordered_coords)

    m = folium.Map(location=[avg_lat, avg_lng], zoom_start=10, tiles="CartoDB positron")

    # Add markers
    seen_depot = False
    stop_label_idx = 0
    for idx, node in enumerate(route):
        geo = geocoded_list[node]
        lat, lng = geo["lat"], geo["lng"]
        addr = html.escape(geo["formatted_address"] or geo["input_address"])

        if node == depot:
            if seen_depot and rts:
                continue
            seen_depot = True
            home_icon_html = (
                '<div style="'
                'background-color: #E9A820;'
                'color: white;'
                'border-radius: 50%;'
                'width: 36px;'
                'height: 36px;'
                'display: flex;'
                'align-items: center;'
                'justify-content: center;'
                'font-weight: bold;'
                'font-size: 16px;'
                'border: 3px solid white;'
                'box-shadow: 0 2px 8px rgba(0,0,0,0.3);'
                '">H</div>'
            )
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(f"<b>HOME</b><br>{addr}", max_width=250),
                icon=folium.DivIcon(
                    html=home_icon_html,
                    icon_size=(36, 36),
                    icon_anchor=(18, 18),
                ),
            ).add_to(m)
        else:
            label = get_stop_label(stop_label_idx)
            stop_label_idx += 1
            stop_icon_html = (
                '<div style="'
                'background-color: #2A9D8F;'
                'color: white;'
                'border-radius: 50%;'
                'width: 28px;'
                'height: 28px;'
                'display: flex;'
                'align-items: center;'
                'justify-content: center;'
                'font-weight: bold;'
                'font-size: 12px;'
                'border: 2px solid white;'
                'box-shadow: 0 2px 6px rgba(0,0,0,0.3);'
                f'">{label}</div>'
            )
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(f"<b>Stop {label}</b><br>{addr}", max_width=250),
                icon=folium.DivIcon(
                    html=stop_icon_html,
                    icon_size=(28, 28),
                    icon_anchor=(14, 14),
                ),
            ).add_to(m)

    # Route polyline
    route_line = [(geocoded_list[node]["lat"], geocoded_list[node]["lng"]) for node in route]
    folium.PolyLine(
        route_line,
        color="#E8654A",
        weight=4,
        opacity=0.85,
    ).add_to(m)

    # Auto-zoom
    bounds = [[c[0], c[1]] for c in ordered_coords]
    m.fit_bounds(bounds)

    st_folium(m, use_container_width=True, height=550, returned_objects=[])

    # ---- Stop table (styled HTML) ----
    leg_distances_mi = [meters_to_miles(d) for d in leg_distances]

    table_html = '<table style="width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 16px;">'
    table_html += (
        '<tr style="background-color: #F5EDE4;">'
        '<th style="padding: 10px 12px; text-align: left; font-weight: 600;">#</th>'
        '<th style="padding: 10px 12px; text-align: left; font-weight: 600;">Stop</th>'
        '<th style="padding: 10px 12px; text-align: left; font-weight: 600;">Address</th>'
        '<th style="padding: 10px 12px; text-align: left; font-weight: 600;">Next Leg</th>'
        '</tr>'
    )

    for i, (addr, label) in enumerate(zip(ordered_addresses, labels)):
        escaped_addr = html.escape(addr)

        if rts and i == len(ordered_addresses) - 1:
            next_leg = "-- END --"
        elif i < len(leg_distances_mi):
            next_leg = f"{leg_distances_mi[i]:.1f} mi / {seconds_to_hm(leg_durations[i])}"
        else:
            next_leg = "-- END --"

        row_bg = "white" if i % 2 == 0 else "#FDF8F4"

        # Badge
        if label == "H":
            badge = (
                '<span style="display: inline-flex; align-items: center; justify-content: center; '
                'background-color: #E9A820; color: white; border-radius: 50%; width: 26px; height: 26px; '
                'font-weight: bold; font-size: 11px;">H</span>'
            )
        else:
            badge = (
                '<span style="display: inline-flex; align-items: center; justify-content: center; '
                'background-color: #2A9D8F; color: white; border-radius: 50%; width: 26px; height: 26px; '
                f'font-weight: bold; font-size: 11px;">{html.escape(label)}</span>'
            )

        table_html += (
            f'<tr style="background-color: {row_bg};">'
            f'<td style="padding: 10px 12px;">{i + 1}</td>'
            f'<td style="padding: 10px 12px;">{badge}</td>'
            f'<td style="padding: 10px 12px;">{escaped_addr}</td>'
            f'<td style="padding: 10px 12px;">{next_leg}</td>'
            '</tr>'
        )

    table_html += '</table>'
    st.markdown(table_html, unsafe_allow_html=True)

    # ---- Export section ----
    st.divider()

    # Google Maps link
    gmaps_url = generate_google_maps_url(ordered_addresses, rts)
    n_waypoints = len(ordered_addresses) - 2

    st.markdown(f"""
    <a href="{gmaps_url}" target="_blank" rel="noopener noreferrer" style="
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: linear-gradient(135deg, #E8654A 0%, #C74E36 100%);
        color: white;
        text-decoration: none;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.95rem;
        box-shadow: 0 4px 12px rgba(232, 101, 74, 0.3);
        margin-bottom: 12px;
    ">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
        </svg>
        Open in Google Maps
    </a>
    """, unsafe_allow_html=True)

    if n_waypoints > 11:
        st.warning(
            f"Your route has {n_waypoints} waypoints. Google Maps URLs support "
            f"a maximum of ~11 waypoints. The link may not include all stops."
        )

    # CSV download
    csv_data = route_to_csv(
        ordered_addresses,
        leg_distances_mi,
        [leg_durations[i] if i < len(leg_durations) else 0 for i in range(len(ordered_addresses))],
        labels,
    )
    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name="donnas_drive_time_route.csv",
        mime="text/csv",
    )
