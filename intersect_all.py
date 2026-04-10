import os
import re
import argparse
import math
import networkx as nx
from shapely.geometry import LineString

# ----------------------------
# PARSING
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# LOAD WPT FILES
# ----------------------------
def load_highways(folder):
    highways = {}

    for root, _, files in os.walk(folder):
        for file in files:
            if not file.lower().endswith(".wpt"):
                continue

            path = os.path.join(root, file)
            coords = []

            try:
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

                        coords.append((lon, lat))

            except Exception:
                continue

            if len(coords) >= 2:
                highways[file] = coords

    print(f"Loaded {len(highways)} highways")
    return highways


# ----------------------------
# BUILD ROAD GRAPH
# ----------------------------
def build_graph(highways):
    G = nx.Graph()

    for name, coords in highways.items():
        for i in range(len(coords) - 1):
            a = coords[i]
            b = coords[i + 1]

            dist = math.hypot(a[0] - b[0], a[1] - b[1])

            G.add_edge(
                a, b,
                weight=dist,
                highway=name
            )

    print(f"Graph nodes: {len(G.nodes)}")
    print(f"Graph edges: {len(G.edges)}")
    return G


# ----------------------------
# SNAP POINT TO GRAPH
# ----------------------------
def nearest_node(G, point):
    return min(
        G.nodes,
        key=lambda n: (n[0] - point[0])**2 + (n[1] - point[1])**2
    )


# ----------------------------
# PICK REPRESENTATIVE TARGETS
# (one per highway)
# ----------------------------
def build_targets(highways, G):
    targets = []

    for coords in highways.values():
        mid = coords[len(coords) // 2]
        node = nearest_node(G, mid)
        targets.append(node)

    return targets


# ----------------------------
# BUILD ROUTE (REAL ROAD FOLLOWING)
# ----------------------------
def build_route(G, targets):
    route = []

    current = targets[0]

    for nxt in targets[1:]:
        try:
            path = nx.shortest_path(G, current, nxt, weight="weight")
        except nx.NetworkXNoPath:
            continue

        route.extend(path[:-1])
        current = nxt

    route.append(current)
    return route


# ----------------------------
# COVERAGE CHECK (OPTIONAL)
# ----------------------------
def check_coverage(route, highways, G):
    route_set = set(route)
    missed = []

    for name, coords in highways.items():
        ok = False
        for c in coords:
            node = nearest_node(G, c)
            if node in route_set:
                ok = True
                break
        if not ok:
            missed.append(name)

    return missed


# ----------------------------
# SAVE OUTPUT
# ----------------------------
def save_path(route, filename="path.txt"):
    with open(filename, "w") as f:
        for x, y in route:
            f.write(f"{y} {x}\n")


# ----------------------------
# FOLIUM VISUALIZATION
# ----------------------------
def plot_folium(route, highways, output="map.html"):
    import folium

    first_lon, first_lat = route[0]
    m = folium.Map(location=[first_lat, first_lon], zoom_start=7)

    # highways
    for coords in highways.values():
        folium.PolyLine(
            [(lat, lon) for lon, lat in coords],
            color="blue",
            weight=1
        ).add_to(m)

    # route
    folium.PolyLine(
        [(lat, lon) for lon, lat in route],
        color="red",
        weight=3
    ).add_to(m)

    m.save(output)
    print(f"Saved map: {output}")


# ----------------------------
# MAIN SOLVER
# ----------------------------
def solve(folder):
    highways = load_highways(folder)

    G = build_graph(highways)

    print("Building targets...")
    targets = build_targets(highways, G)

    print("Routing over real road network...")
    route = build_route(G, targets)

    return route, highways


# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--output", default="path.txt")
    parser.add_argument("--map", action="store_true")

    args = parser.parse_args()

    route, highways = solve(args.folder)

    save_path(route, args.output)
    print(f"Saved {args.output}")

    if args.map:
        plot_folium(route, highways)
