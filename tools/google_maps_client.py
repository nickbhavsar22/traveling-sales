import googlemaps
import math
import time
from typing import List, Dict, Tuple, Optional


class GoogleMapsClient:
    """Wrapper around the Google Maps API for geocoding and distance matrices."""

    DISTANCE_MATRIX_MAX_ELEMENTS = 100
    DISTANCE_MATRIX_MAX_DIMENSIONS = 25

    def __init__(self, api_key: str):
        self.client = googlemaps.Client(key=api_key)

    def geocode_addresses(self, addresses: List[str]) -> List[Dict]:
        """
        Geocode a list of addresses to lat/lng coordinates.

        Returns a list of dicts, one per input address, with keys:
            input_address, formatted_address, lat, lng, place_id, status
        """
        results = []
        for address in addresses:
            try:
                geocode_result = self.client.geocode(address)
                if geocode_result:
                    location = geocode_result[0]["geometry"]["location"]
                    results.append({
                        "input_address": address,
                        "formatted_address": geocode_result[0]["formatted_address"],
                        "lat": location["lat"],
                        "lng": location["lng"],
                        "place_id": geocode_result[0]["place_id"],
                        "status": "OK",
                    })
                else:
                    results.append({
                        "input_address": address,
                        "formatted_address": None,
                        "lat": None,
                        "lng": None,
                        "place_id": None,
                        "status": "FAILED",
                    })
            except Exception:
                results.append({
                    "input_address": address,
                    "formatted_address": None,
                    "lat": None,
                    "lng": None,
                    "place_id": None,
                    "status": "FAILED",
                })
        return results

    def build_distance_matrix(
        self, locations: List[Dict], mode: str = "driving"
    ) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Build NxN distance and duration matrices via batched Distance Matrix
        API calls.

        Args:
            locations: List of dicts with 'lat' and 'lng' keys.
            mode: Travel mode — "driving", "walking", "bicycling", "transit".

        Returns:
            (distance_matrix_meters, duration_matrix_seconds) — both NxN lists.
        """
        n = len(locations)
        coords = [(loc["lat"], loc["lng"]) for loc in locations]

        distance_matrix = [[0] * n for _ in range(n)]
        duration_matrix = [[0] * n for _ in range(n)]

        batch_size = 10

        origin_batches = [
            (i, coords[i : i + batch_size])
            for i in range(0, n, batch_size)
        ]
        dest_batches = [
            (j, coords[j : j + batch_size])
            for j in range(0, n, batch_size)
        ]

        for o_start, origin_batch in origin_batches:
            for d_start, dest_batch in dest_batches:
                result = self._batch_distance_matrix(
                    origin_batch, dest_batch, mode
                )

                for i, row in enumerate(result["rows"]):
                    for j, element in enumerate(row["elements"]):
                        global_i = o_start + i
                        global_j = d_start + j
                        if element["status"] == "OK":
                            distance_matrix[global_i][global_j] = (
                                element["distance"]["value"]
                            )
                            duration_matrix[global_i][global_j] = (
                                element["duration"]["value"]
                            )
                        else:
                            distance_matrix[global_i][global_j] = 999999999
                            duration_matrix[global_i][global_j] = 999999999

                time.sleep(0.1)

        return distance_matrix, duration_matrix

    def _batch_distance_matrix(
        self, origins, destinations, mode="driving"
    ) -> Dict:
        """
        Make a single Distance Matrix API call for one batch of origins
        and destinations.
        """
        result = self.client.distance_matrix(
            origins=list(origins),
            destinations=list(destinations),
            mode=mode,
        )
        return result

    @staticmethod
    def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calculate the straight-line distance in meters between two
        lat/lng points using the haversine formula.
        """
        R = 6_371_000  # Earth radius in meters

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def build_haversine_matrix(self, locations: List[Dict]) -> List[List[int]]:
        """
        Build an NxN straight-line distance matrix using the haversine formula.
        No API calls are made.
        """
        n = len(locations)
        matrix = [[0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                d = int(
                    self.haversine_distance(
                        locations[i]["lat"],
                        locations[i]["lng"],
                        locations[j]["lat"],
                        locations[j]["lng"],
                    )
                )
                matrix[i][j] = d
                matrix[j][i] = d

        return matrix
