from typing import List, Dict, Any, Optional, Tuple
from tools.google_maps_client import GoogleMapsClient
from tools.tsp_solver import solve_tsp


class RouteOptimizer:
    """
    High-level pipeline orchestrator that combines geocoding, distance matrix
    construction, TSP solving, and result formatting.
    """

    def __init__(self, api_key: str):
        self.gmaps = GoogleMapsClient(api_key)
        self.geocoded_locations: List[Dict] = []
        self.distance_matrix: List[List[int]] = []
        self.duration_matrix: List[List[int]] = []

    def geocode(self, addresses: List[str]) -> Tuple[List[Dict], List[str]]:
        """
        Phase 1: Geocode all addresses.

        Returns:
            (successes, failed_addresses) where successes is a list of geocoded
            location dicts and failed_addresses is a list of input strings that
            could not be geocoded.
        """
        results = self.gmaps.geocode_addresses(addresses)

        successes = []
        failures = []
        for result in results:
            if result["status"] == "OK":
                successes.append(result)
            else:
                failures.append(result["input_address"])

        self.geocoded_locations = successes
        return successes, failures

    def compute_distance_matrix(
        self, use_haversine: bool = False
    ) -> Dict[str, Any]:
        """
        Phase 2: Build the NxN distance (and duration) matrices.

        Args:
            use_haversine: If True, use straight-line distances (free, no API
                calls). If False, use the Google Distance Matrix API.

        Returns:
            Dict with distance_matrix, duration_matrix, element_count, and
            estimated_cost.
        """
        n = len(self.geocoded_locations)

        if use_haversine:
            self.distance_matrix = self.gmaps.build_haversine_matrix(
                self.geocoded_locations
            )
            # Estimate duration assuming an average speed of 50 km/h (13.89 m/s)
            avg_speed_mps = 13.89
            self.duration_matrix = [
                [int(d / avg_speed_mps) if avg_speed_mps > 0 else 0 for d in row]
                for row in self.distance_matrix
            ]
            element_count = n * n
            estimated_cost = 0.0
        else:
            self.distance_matrix, self.duration_matrix = (
                self.gmaps.build_distance_matrix(self.geocoded_locations)
            )
            element_count = n * n
            # Google charges $5 per 1000 elements (basic), $10 per 1000 (advanced)
            estimated_cost = (element_count / 1000) * 5.0

        return {
            "distance_matrix": self.distance_matrix,
            "duration_matrix": self.duration_matrix,
            "element_count": element_count,
            "estimated_cost": estimated_cost,
        }

    def optimize(
        self,
        home_index: int = 0,
        return_home: bool = True,
        time_limit: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Phase 3 + 4: Solve the TSP and format the results.

        Args:
            home_index: Index of the starting (depot) location.
            return_home: Whether the route should return to the start.
            time_limit: Maximum solver time in seconds.

        Returns:
            Formatted route dict with ordered_stops, legs, totals, and solver
            status — or None if no solution is found.
        """
        if not self.distance_matrix:
            return None

        solution = solve_tsp(
            distance_matrix=self.distance_matrix,
            depot=home_index,
            return_to_depot=return_home,
            time_limit_seconds=time_limit,
        )

        if solution is None:
            return None

        route = solution["route"]
        locations = self.geocoded_locations

        # Build ordered_stops
        ordered_stops = []
        for seq, idx in enumerate(route):
            loc = locations[idx]
            ordered_stops.append({
                "sequence": seq,
                "index": idx,
                "address": loc.get("formatted_address", loc.get("input_address", "")),
                "lat": loc["lat"],
                "lng": loc["lng"],
                "is_home": idx == home_index,
            })

        # Build legs
        legs = []
        total_distance_m = 0
        total_duration_s = 0

        for i in range(len(route) - 1):
            from_idx = route[i]
            to_idx = route[i + 1]
            dist_m = self.distance_matrix[from_idx][to_idx]
            dur_s = self.duration_matrix[from_idx][to_idx]

            total_distance_m += dist_m
            total_duration_s += dur_s

            from_loc = locations[from_idx]
            to_loc = locations[to_idx]

            legs.append({
                "from_address": from_loc.get(
                    "formatted_address", from_loc.get("input_address", "")
                ),
                "to_address": to_loc.get(
                    "formatted_address", to_loc.get("input_address", "")
                ),
                "distance_m": dist_m,
                "distance_mi": round(dist_m / 1609.344, 2),
                "duration_s": dur_s,
                "duration_text": self._format_duration(dur_s),
            })

        total_distance_mi = round(total_distance_m / 1609.344, 2)

        return {
            "ordered_stops": ordered_stops,
            "legs": legs,
            "total_distance_m": total_distance_m,
            "total_distance_mi": total_distance_mi,
            "total_duration_s": total_duration_s,
            "total_duration_text": self._format_duration(total_duration_s),
            "solver_status": solution["solver_status"],
        }

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Convert a number of seconds to a human-readable 'Xh Ym' string."""
        if seconds <= 0:
            return "0m"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
