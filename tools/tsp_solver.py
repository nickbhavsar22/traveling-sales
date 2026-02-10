from ortools.constraint_solver import routing_enums_pb2, pywrapcp
from typing import List, Optional, Dict, Any


def solve_tsp(
    distance_matrix: List[List[int]],
    depot: int = 0,
    return_to_depot: bool = True,
    time_limit_seconds: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Solve the Traveling Salesman Problem using Google OR-Tools.

    Args:
        distance_matrix: NxN matrix of distances between locations (meters).
        depot: Index of the starting location.
        return_to_depot: Whether the route must return to the depot at the end.
        time_limit_seconds: Maximum solver time in seconds.

    Returns:
        Dict with "route", "total_distance", and "solver_status", or None if
        no solution is found.
    """
    n = len(distance_matrix)

    # Trivial cases
    if n == 0:
        return {"route": [], "total_distance": 0, "solver_status": "TRIVIAL"}
    if n == 1:
        return {"route": [depot], "total_distance": 0, "solver_status": "TRIVIAL"}

    # For open-path TSP (no return to depot), zero out all distances TO the
    # depot so the solver's mandatory return leg is free.
    if not return_to_depot:
        matrix = [row[:] for row in distance_matrix]  # deep copy
        for i in range(n):
            matrix[i][depot] = 0
    else:
        matrix = distance_matrix

    # OR-Tools data model callback
    manager = pywrapcp.RoutingIndexManager(n, 1, depot)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Search parameters
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = time_limit_seconds

    # Solve
    solution = routing.SolveWithParameters(search_parameters)

    if not solution:
        status_code = routing.status()
        status_map = {
            0: "ROUTING_NOT_SOLVED",
            1: "ROUTING_SUCCESS",
            2: "ROUTING_PARTIAL_SUCCESS",
            3: "ROUTING_FAIL",
            4: "ROUTING_FAIL_TIMEOUT",
            5: "ROUTING_INVALID",
            6: "ROUTING_INFEASIBLE",
        }
        return None

    # Extract the route
    route: List[int] = []
    index = routing.Start(0)
    total_distance = 0

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        route.append(node)
        previous_index = index
        index = solution.Value(routing.NextVar(index))
        total_distance += routing.GetArcCostForVehicle(previous_index, index, 0)

    # For return_to_depot, add the depot at the end to close the loop
    if return_to_depot:
        route.append(depot)

    # Recalculate distance from the original matrix for open-path routes,
    # since we zeroed-out return-to-depot costs in the modified matrix.
    if not return_to_depot:
        total_distance = 0
        for i in range(len(route) - 1):
            total_distance += distance_matrix[route[i]][route[i + 1]]

    # Determine solver status string
    status_code = routing.status()
    status_map = {
        1: "OPTIMAL",
        2: "FEASIBLE",
    }
    solver_status = status_map.get(status_code, "FEASIBLE")

    return {
        "route": route,
        "total_distance": total_distance,
        "solver_status": solver_status,
    }
