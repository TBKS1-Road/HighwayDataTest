import os
import re
import math
import argparse
import networkx as nx
from collections import defaultdict

# ----------------------------
# PARSING
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# CLEAN HIGHWAY NAME
# ----------------------------
def normalize_name(name):
    # extract only main identifier (AR143, I-40, US165, etc.)
    return name.split()[0].strip()


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

                    parts = line.split()
                    name = normalize_name(parts[0])

                    roads.append((name, (lon, lat)))

    return roads


# ----------------------------
# BUILD GRAPH WITH LABELS
# ----------------------------
def build_graph(roads):
    G = nx.Graph()

    prev_by_file = {}

    for name, coord in roads:
        if name not in prev_by_file:
            prev_by_file[name] = coord
            continue

        prev = prev_by_file[name]
        curr = coord

        dist = math.hypot(curr[0]-prev[0], curr[1]-prev[1])

        G.add_edge(prev, curr, weight=dist, highway=name)

        prev_by_file[name] = curr

    print(f"Graph nodes: {len(G.nodes)}")
    print(f"Graph edges: {len(G.edges)}")

    return G


# ----------------------------
# MAP HIGHWAY → NODES
# ----------------------------
def build_highway_targets(G):
    targets = defaultdict(list)

    for u, v, data in G.edges(data=True):
        targets[data["highway"]].append(u)
        targets[data["highway"]].append(v)

    # reduce duplicates
    for k in targets:
        targets[k] = list(set(targets[k]))

    return targets


# ----------------------------
# SHORTEST PATH COST
# ----------------------------
def path_cost(G, a, b):
    try:
        return nx.shortest_path_length(G, a, b, weight="weight")
    except:
        return float("inf")


# ----------------------------
# GREEDY COVERAGE ORDER (CORE)
# ----------------------------
def compute_visit_order(G, targets):
    remaining = set(targets.keys())

    current_hwy = next(iter(remaining))
    remaining.remove(current_hwy)

    order = [current_hwy]

    while remaining:
        best = None
        best_cost = float("inf")

        for hwy in remaining:
            for a in targets[current_hwy]:
                for b in targets[hwy]:
                    c = path_cost(G, a, b)
                    if c < best_cost:
                        best_cost = c
                        best = hwy

        order.append(best)
        remaining.remove(best)
        current_hwy = best

    return order


# ----------------------------
# BUILD FINAL ROUTE
# ----------------------------
def build_route(G, order, targets):
    route = []

    current = targets[order[0]][0]

    for hwy in order[1:]:
        best_target = None
        best_cost = float("inf")

        for t in targets[hwy]:
            c = path_cost(G, current, t)
            if c < best_cost:
                best_cost = c
                best_target = t

        segment = nx.shortest_path(G, current, best_target, weight="weight")

        route.extend(segment[:-1])
        current = best_target

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
# SOLVER
# ----------------------------
def solve(folder):
    print("Loading roads...")
    roads = load_highways(folder)

    print("Building graph...")
    G = build_graph(roads)

    print("Building highway targets...")
    targets = build_highway_targets(G)

    print("Computing visit order...")
    order = compute_visit_order(G, targets)

    print("Building final route...")
    route = build_route(G, order, targets)

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
