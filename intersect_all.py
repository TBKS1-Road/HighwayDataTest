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

    print(f"Loaded {len(roads)} points")
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

            dist = math.hypot(a[0] - b[0], a[1] - b[1])

            G.add_edge(a, b, weight=dist, highway=name)

        last[name] = coord

    print(f"Graph nodes: {len(G.nodes)}")
    print(f"Graph edges: {len(G.edges)}")

    return G


# ----------------------------
# BUILD TARGETS (FIXED + REDUCED)
# ----------------------------
def build_targets(G):
    raw = defaultdict(list)

    for u, v, d in G.edges(data=True):
        hwy = d["highway"]
        raw[hwy].append(u)
        raw[hwy].append(v)

    targets = {}

    for hwy, nodes in raw.items():
        nodes = list(set(nodes))

        # 🔥 CRITICAL REDUCTION (prevents explosion)
        if len(nodes) > 3:
            nodes = nodes[:3]

        targets[hwy] = nodes

    print(f"Highway groups: {len(targets)}")
    return targets


# ----------------------------
# DISTANCE MATRIX (FIXED + CACHED)
# ----------------------------
def build_distance_matrix(G, targets):
    highways = list(targets.keys())
    n = len(highways)

    print(f"Building distance matrix: {n} nodes")

    cache = {}

    def shortest(a, b):
        if (a, b) in cache:
            return cache[(a, b)]

        try:
            val = nx.shortest_path_length(G, a, b, weight="weight")
        except:
            val = float("inf")

        cache[(a, b)] = val
        cache[(b, a)] = val

        return val

    matrix = [[0] * n for _ in range(n)]

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

            matrix[i][j] = int(best)

        print(f"Row {i+1}/{n}")

    return highways, matrix


# ----------------------------
# OR-TOOLS TSP SOLVER
# ----------------------------
def solve_tsp(matrix):
    n = len(matrix)

    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def cost(i, j):
        a = manager.IndexToNode(i)
        b = manager.IndexToNode(j)
        return matrix[a][b]

    cb = routing.RegisterTransitCallback(cost)
    routing.SetArcCostEvaluatorOfAllVehicles(cb)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(20)

    sol = routing.SolveWithParameters(params)

    index = routing.Start(0)
    order = []

    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = sol.Value(routing.NextVar(index))

    return order


# ----------------------------
# BUILD FINAL ROUTE
# ----------------------------
def build_route(G, order, targets, highways):
    route = []

    current = targets[highways[order[0]]][0]

    for idx in order[1:]:
        hwy = highways[idx]

        best = None
        best_cost = float("inf")

        for t in targets[hwy]:
            try:
                c = nx.shortest_path_length(G, current, t, weight="weight")
                if c < best_cost:
                    best_cost = c
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
# MAIN PIPELINE
# ----------------------------
def solve(folder):
    roads = load_highways(folder)

    G = build_graph(roads)

    targets = build_targets(G)

    highways, matrix = build_distance_matrix(G, targets)

    print("Solving TSP...")
    order = solve_tsp(matrix)

    print("Building route...")
    route = build_route(G, order, targets, highways)

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
