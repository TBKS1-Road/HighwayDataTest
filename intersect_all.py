import os
import re
import math
import argparse
import networkx as nx
from collections import defaultdict

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2


# ----------------------------
# PARSING
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# LOAD WPT FILES
# ----------------------------
def load_highways(folder):
    roads = []

    for root, _, files in os.walk(folder):
        for file in files:
            if not file.lower().endswith(".wpt"):
                continue

            path = os.path.join(root, file)

            with open(path, encoding="utf-8") as f:
                for line in f:
                    if "lat=" not in line or "lon=" not in line:
                        continue

                    lm = LAT_RE.search(line)
                    nm = LON_RE.search(line)

                    if not lm or not nm:
                        continue

                    lat = float(lm.group(1))
                    lon = float(nm.group(1))

                    name = file.replace(".wpt", "")
                    roads.append((name, (lon, lat)))

    return roads


# ----------------------------
# BUILD GRAPH
# ----------------------------
def build_graph(roads):
    G = nx.Graph()

    last = {}

    for name, coord in roads:
        if name in last:
            a = last[name]
            b = coord

            dist = math.hypot(a[0]-b[0], a[1]-b[1])

            G.add_edge(a, b, weight=dist, highway=name)

        last[name] = coord

    print(f"Graph nodes: {len(G.nodes)}")
    print(f"Graph edges: {len(G.edges)}")

    return G


# ----------------------------
# HIGHWAY TARGETS (ONE PER HIGHWAY)
# ----------------------------
def build_targets(G):
    targets = defaultdict(list)

    for u, v, d in G.edges(data=True):
        targets[d["highway"]].append(u)
        targets[d["highway"]].append(v)

    for k in targets:
        targets[k] = list(set(targets[k]))

    return targets


# ----------------------------
# DISTANCE MATRIX (CRITICAL STEP)
# ----------------------------
def build_distance_matrix(G, targets):
    print("Precomputing shortest path distances...")

    highways = list(targets.keys())
    n = len(highways)

    dist_matrix = [[0]*n for _ in range(n)]

    def shortest(a, b):
        try:
            return nx.shortest_path_length(G, a, b, weight="weight")
        except:
            return float("inf")

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            h1 = highways[i]
            h2 = highways[j]

            best = float("inf")

            for a in targets[h1]:
                for b in targets[h2]:
                    best = min(best, shortest(a, b))

            dist_matrix[i][j] = int(best)

        print(f"Row {i+1}/{n}")

    return highways, dist_matrix


# ----------------------------
# OR-TOOLS TSP SOLVER (GLOBAL OPTIMIZATION)
# ----------------------------
def solve_tsp(distance_matrix):
    n = len(distance_matrix)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(30)

    solution = routing.SolveWithParameters(params)

    if not solution:
        raise Exception("No solution found")

    index = routing.Start(0)

    order = []

    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        order.append(node)
        index = solution.Value(routing.NextVar(index))

    return order


# ----------------------------
# BUILD FINAL ROUTE
# ----------------------------
def build_route(G, highway_order, highways, targets):
    route = []

    current = targets[highway_order[0]][0]

    for hwy in highway_order[1:]:
        best = None
        best_cost = float("inf")

        for t in targets[hwy]:
            try:
                cost = nx.shortest_path_length(G, current, t, weight="weight")
                if cost < best_cost:
                    best_cost = cost
                    best = t
            except:
                continue

        segment = nx.shortest_path(G, current, best, weight="weight")

        route.extend(segment[:-1])
        current = best

    route.append(current)
    return route


# ----------------------------
# SAVE
# ----------------------------
def save(route, filename):
    with open(filename, "w") as f:
        for x, y in route:
            f.write(f"{y} {x}\n")


# ----------------------------
# SOLVE PIPELINE
# ----------------------------
def solve(folder):
    roads = load_highways(folder)

    G = build_graph(roads)

    targets = build_targets(G)

    highways, dist_matrix = build_distance_matrix(G, targets)

    print("Solving global TSP (OR-Tools)...")
    order = solve_tsp(dist_matrix)

    ordered_highways = [highways[i] for i in order]

    print("Building final route...")
    route = build_route(G, ordered_highways, targets)

    return route, G


# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--output", default="path.txt")

    args = parser.parse_args()

    route, G = solve(args.folder)

    save(route, args.output)

    print(f"Saved {args.output}")
