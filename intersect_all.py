import os
import re
import math
import argparse
import networkx as nx
from collections import defaultdict
from tqdm import tqdm
import folium


# ----------------------------
# SETTINGS
# ----------------------------
TARGETS_PER_HIGHWAY = 1   # keep 1 for TM-style coverage


# ----------------------------
# PARSING
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# LOAD WPT FILES (WITH LABELS)
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

                    label = line.strip().split()[0]
                    name = file.replace(".wpt", "")

                    roads.append((name, (lon, lat), label))

    print(f"Loaded {len(roads)} points")
    return roads


# ----------------------------
# BUILD GRAPH (WITH LABELS)
# ----------------------------
def build_graph(roads):
    G = nx.Graph()
    last = {}

    for name, coord, label in tqdm(roads, desc="Building graph"):
        G.add_node(coord, label=label, highway=name)

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
# BUILD TARGETS (SMART PICK)
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

        # pick most connected node
        best_node = max(nodes, key=lambda n: G.degree(n))

        targets[hwy] = [best_node]

    print(f"Highway groups: {len(targets)}")
    return targets


# ----------------------------
# PRECOMPUTE DISTANCES
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


def fast_distance(dist_map, a, b):
    return dist_map.get(a, {}).get(b, float("inf"))


# ----------------------------
# COMPUTE ORDER
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
        return

    if not filename.endswith(".txt"):
        filename += ".txt"

    with open(filename, "w", encoding="utf-8") as f:
        for x, y in route:
            f.write(f"{y} {x}\n")

    print(f"Saved: {filename}")


# ----------------------------
# BUILD TM SEGMENTS
# ----------------------------
def build_tm_segments(route, G):
    segments = []

    if not route:
        return segments

    prev_hwy = None
    start_label = None
    prev_label = None

    for node in route:
        data = G.nodes.get(node, {})
        hwy = data.get("highway")
        label = data.get("label")

        if not hwy or not label:
            continue

        if prev_hwy is None:
            prev_hwy = hwy
            start_label = label
            prev_label = label
            continue

        if hwy != prev_hwy:
            segments.append((prev_hwy, start_label, prev_label))
            prev_hwy = hwy
            start_label = label

        prev_label = label

    if prev_hwy and start_label and prev_label:
        segments.append((prev_hwy, start_label, prev_label))

    # remove duplicates
    segments = list(dict.fromkeys(segments))

    return segments

def format_tm_route_name(raw_name):
    """
    Convert filename-style highway names to TM visual names
    Works for ANY state (TN, LA, AR, etc.)
    """

    parts = raw_name.lower().split(".")

    # If format is like tn.tn049 → ['tn', 'tn049']
    if len(parts) == 2:
        region, name = parts
        region = region.upper()
    else:
        name = parts[-1]
        region = ""

    def split_num_suffix(s):
        num = ""
        suffix = ""
        for c in s:
            if c.isdigit():
                num += c
            else:
                suffix += c
        return num, suffix

    # Interstate
    if name.startswith("i"):
        num, suffix = split_num_suffix(name[1:])
        if num:
            return f"I-{int(num)}{suffix.title()}"

    # US routes
    if name.startswith("us"):
        num, suffix = split_num_suffix(name[2:])
        if num:
            return f"US{int(num)}{suffix.title()}"

    # State routes (generic, works for TN, LA, AR, etc.)
    if name.startswith(region.lower()):
        num, suffix = split_num_suffix(name[len(region):])
        if num:
            return f"{region}{int(num)}{suffix.title()}"

    # Fallback
    return name.upper()

def detect_region(roads):
    """
    Detect region from first highway name
    Example: la.us190 -> LA
    """
    for name, _, _ in roads:
        if "." in name:
            region = name.split(".")[0]
            return region.upper()
    return "XX"
# ----------------------------
# SAVE TM LIST
# ----------------------------
def save_tm_list(segments, filename="route.list", region="AR"):
    if not segments:
        return

    if not filename.endswith(".list"):
        filename += ".list"

    with open(filename, "w", encoding="utf-8") as f:
        for hwy, start, end in segments:
            if start == end:
                continue
            pretty = format_tm_route_name(hwy)
            f.write(f"{region} {pretty} {start} {end}\n")

    print(f"TM .list saved: {filename}")


# ----------------------------
# SAVE KML
# ----------------------------
def save_kml(route, filename="route.kml"):
    if not route:
        return

    if not filename.endswith(".kml"):
        filename += ".kml"

    with open(filename, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<kml xmlns="http://www.opengis.net/kml/2.2">\n')
        f.write('<Document>\n')
        f.write('<name>Route</name>\n')

        # LineString (main path)
        f.write('<Placemark>\n')
        f.write('<name>Route Path</name>\n')
        f.write('<LineString>\n')
        f.write('<coordinates>\n')

        for lon, lat in route:
            f.write(f"{lon},{lat},0\n")

        f.write('</coordinates>\n')
        f.write('</LineString>\n')
        f.write('</Placemark>\n')

        # Start point
        start_lon, start_lat = route[0]
        f.write('<Placemark>\n')
        f.write('<name>Start</name>\n')
        f.write('<Point>\n')
        f.write(f'<coordinates>{start_lon},{start_lat},0</coordinates>\n')
        f.write('</Point>\n')
        f.write('</Placemark>\n')

        # End point
        end_lon, end_lat = route[-1]
        f.write('<Placemark>\n')
        f.write('<name>End</name>\n')
        f.write('<Point>\n')
        f.write(f'<coordinates>{end_lon},{end_lat},0</coordinates>\n')
        f.write('</Point>\n')
        f.write('</Placemark>\n')

        f.write('</Document>\n')
        f.write('</kml>\n')

    print(f"KML saved: {filename}")


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

    region = detect_region(roads)
    return route, G, region


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--output", default="path.txt")

    args = parser.parse_args()

    route, G, region = solve(args.folder)

    save(route, args.output)
    plot_route(route)

    save_kml(route, "route.kml")

    segments = build_tm_segments(route, G)
    save_tm_list(segments, "route.list", region=region)
