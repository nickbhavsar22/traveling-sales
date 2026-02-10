import csv
import io
import urllib.parse
from typing import Dict


def sanitize_csv_value(val):
    """Prevent CSV formula injection by prefixing dangerous characters."""
    if isinstance(val, str) and val and val[0] in ('=', '@', '+', '-'):
        return "'" + val
    return val


def route_to_csv(route_data: Dict) -> str:
    """
    Convert optimized route data to a CSV string.

    Columns: Stop#, Address, Distance to Next (mi), Time to Next, Lat, Lng
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Stop#",
        "Address",
        "Distance to Next (mi)",
        "Time to Next",
        "Lat",
        "Lng",
    ])

    stops = route_data["ordered_stops"]
    legs = route_data["legs"]

    for i, stop in enumerate(stops):
        if i < len(legs):
            dist_mi = legs[i]["distance_mi"]
            time_next = legs[i]["duration_text"]
        else:
            dist_mi = ""
            time_next = ""

        writer.writerow([
            stop["sequence"] + 1,
            sanitize_csv_value(stop["address"]),
            dist_mi,
            time_next,
            stop["lat"],
            stop["lng"],
        ])

    return output.getvalue()


def generate_google_maps_url(route_data: Dict) -> str:
    """
    Generate a shareable Google Maps directions URL from optimized route data.

    Google Maps URLs support a maximum of approximately 9 waypoints between
    origin and destination. If the route has more, the waypoints are truncated
    and a warning is appended.
    """
    stops = route_data["ordered_stops"]

    if not stops:
        return ""

    if len(stops) == 1:
        addr = stops[0]["address"]
        return (
            "https://www.google.com/maps/search/?api=1&query="
            + urllib.parse.quote(addr)
        )

    origin = stops[0]["address"]
    destination = stops[-1]["address"]

    # Waypoints are everything between origin and destination
    waypoint_stops = stops[1:-1]

    MAX_WAYPOINTS = 9
    truncated = False
    if len(waypoint_stops) > MAX_WAYPOINTS:
        waypoint_stops = waypoint_stops[:MAX_WAYPOINTS]
        truncated = True

    params = {
        "api": "1",
        "origin": origin,
        "destination": destination,
        "travelmode": "driving",
    }

    if waypoint_stops:
        waypoints = "|".join(stop["address"] for stop in waypoint_stops)
        params["waypoints"] = waypoints

    url = "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )

    if truncated:
        url += "&_warning=route_truncated_to_first_9_waypoints"

    return url
