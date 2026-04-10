import os
import re
import math
import argparse
import networkx as nx
from collections import defaultdict
import folium   # ✅ NEW


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
# BUILD HIGHWAY GROUPS
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
        targets[hwy] = nodes[:3]  # keep a few representatives

    print(f"Highway groups: {len(targets)}")
    return targets


# ----------------------------
# COMPONENT MAP
# ----------------------------
def build_components(G):
    comps = list(nx.connected_components(G))
    node_to_comp = {}

    for i, c in enumerate(comps):
        for n in c:
            node_to_comp[n] = i

    print(f"Connected components: {len(comps)}")
    return node_to_comp


# ----------------------------
# SAFE DISTANCE
# ----------------------------
def safe_distance(G, node_to_comp, a, b):
    if node_to_comp.get(a) != node_to_comp.get(b):
        return float("inf")

    try:
        return nx.shortest_path_length(G, a, b, weight="weight")
    except:
        return float("inf")


# ----------------------------
# ORDER
# ----------------------------
def compute_order(G, targets, node_to_comp):
    highways = list(targets.keys())
    remaining = set(highways)

    current = remaining.pop()
    order = [current]

    while remaining:
        best = None
        best_cost = float("inf")

        for hwy in remaining:
            for a in targets[current]:
                for b in targets[hwy]:
                    d = safe_distance(G, node_to_comp, a, b)
                    if d < best_cost:
                        best_cost = d
                        best = hwy

        if best is None:
            best = remaining.pop()
        else:
            remaining.remove(best)

        order.append(best)
        current = best

    return order


# ----------------------------
# ROUTE BUILDER
# ----------------------------
def build_route(G, order, targets):
    route = []

    start_list = targets[order[0]]
    if not start_list:
        return []

    current = start_list[0]

    for hwy in order[1:]:
        candidates = targets[hwy]
        if not candidates:
            continue

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
# ✅ NEW: PLOT WITH FOLIUM
# ----------------------------
def plot_route(route, output_html="route_map.html"):
    if not route:
        print("No route to plot")
        return

    # center map
    start_lat, start_lon = route[0][1], route[0][0]
    m = folium.Map(location=[start_lat, start_lon], zoom_start=6)

    # convert (lon, lat) -> (lat, lon)
    latlon = [(lat, lon) for lon, lat in route]

    # draw line
    folium.PolyLine(latlon, color="blue", weight=3).add_to(m)

    # start marker
    folium.Marker(latlon[0], popup="Start", icon=folium.Icon(color="green")).add_to(m)

    # end marker
    folium.Marker(latlon[-1], popup="End", icon=folium.Icon(color="red")).add_to(m)

    m.save(output_html)
    print(f"Map saved to {output_html}")


# ----------------------------
# MAIN SOLVER
# ----------------------------
def solve(folder):
    roads = load_highways(folder)
    G = build_graph(roads)
    targets = build_targets(G)
    node_to_comp = build_components(G)

    print("Computing order...")
    order = compute_order(G, targets, node_to_comp)

    print("Building route...")
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

    # ✅ Automatically create map
    plot_route(route, "route_map.html")
