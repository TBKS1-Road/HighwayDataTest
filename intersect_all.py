import os
import re
import math
import argparse
import networkx as nx
from collections import defaultdict
from tqdm import tqdm
import folium


# ----------------------------
# SETTINGS (tweak for speed)
# ----------------------------
TARGETS_PER_HIGHWAY = 1  


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
        for file in tqdm(files, desc="Loading WPT files"):
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

    for name, coord in tqdm(roads, desc="Building graph"):
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
# BUILD TARGETS
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

        best_node = max(nodes, key=lambda n: G.degree(n))

        targets[hwy] = [best_node]

    print(f"Highway groups: {len(targets)}")
    return targets


# ----------------------------
# PRECOMPUTE DISTANCES (BIG WIN)
# ----------------------------
def precompute_distances(G, targets):
    print("Precomputing distances...")

    all_nodes = set()
    for nodes in targets.values():
        all_nodes.update(nodes)

    dist_map = {}

    for node in tqdm(all_nodes, desc="Distance precompute"):
        lengths = nx.single_source_dijkstra_path_length(G, node, weight="weight")
        dist_map[node] = lengths

    return dist_map


# ----------------------------
# FAST DISTANCE LOOKUP
# ----------------------------
def fast_distance(dist_map, a, b):
    return dist_map.get(a, {}).get(b, float("inf"))


# ----------------------------
# COMPUTE ORDER (OPTIMIZED)
# ----------------------------
def compute_order(G, targets):
    dist_map = precompute_distances(G, targets)

    highways = list(targets.keys())
    remaining = set(highways)

    current = remaining.pop()
    order = [current]

    with tqdm(total=len(remaining), desc="Computing route order") as pbar:
        while remaining:
            best = None
            best_cost = float("inf")

            for hwy in remaining:
                for a in targets[current]:
                    for b in targets[hwy]:
                        d = fast_distance(dist_map, a, b)
                        if d < best_cost:
                            best_cost = d
                            best = hwy

            if best is None:
                best = remaining.pop()
            else:
                remaining.remove(best)

            order.append(best)
            current = best

            pbar.update(1)

    return order


# ----------------------------
# BUILD ROUTE
# ----------------------------
def build_route(G, order, targets):
    route = []

    current = targets[order[0]][0]

    for hwy in tqdm(order[1:], desc="Building route"):
        candidates = targets[hwy]

        best = None
        best_cost = float("inf")

        for t in candidates:
            try:
                d = nx.shortest_path_length(G, current, t, weight="weight")
                if d < best_cost:
                    best_cost = d
                    best = t
            except:
                continue

        if best is None:
            continue

        try:
            segment = list(nx.shortest_path(G, current, best, weight="weight"))
        except:
            continue

        if len(segment) > 1:
            route.extend(segment[:-1])

        current = best

    route.append(current)
    return route


# ----------------------------
# SAVE TXT
# ----------------------------
def save(route, filename):
    if not route:
        print("❌ No route generated")
        return

    if not filename.endswith(".txt"):
        filename += ".txt"

    with open(filename, "w", encoding="utf-8") as f:
        for x, y in route:
            f.write(f"{y} {x}\n")

    print(f"Saved: {filename}")


# ----------------------------
# MAP OUTPUT
# ----------------------------
def plot_route(route, output_html="route_map.html"):
    if not route:
        return

    start_lat, start_lon = route[0][1], route[0][0]
    m = folium.Map(location=[start_lat, start_lon], zoom_start=6)

    latlon = [(lat, lon) for lon, lat in route]

    folium.PolyLine(latlon, color="blue", weight=3).add_to(m)

    folium.Marker(latlon[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker(latlon[-1], popup="End", icon=folium.Icon(color="red")).add_to(m)

    m.save(output_html)
    print(f"Map saved to {output_html}")


# ----------------------------
# MAIN
# ----------------------------
def solve(folder):
    roads = load_highways(folder)
    G = build_graph(roads)
    targets = build_targets(G)

    print("Computing order...")
    order = compute_order(G, targets)

    print("Building route...")
    route = build_route(G, order, targets)

    return route


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--output", default="path.txt")

    args = parser.parse_args()

    route = solve(args.folder)

    save(route, args.output)
    plot_route(route)
