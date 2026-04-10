import os
import re
import argparse
import math
from shapely.geometry import LineString, Point

# ----------------------------
# PARSING PATTERN
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# LOAD HIGHWAYS
# ----------------------------
def load_highways(folder):
    highways = {}

    for root, _, files in os.walk(folder):
        for filename in files:
            if not filename.lower().endswith(".wpt"):
                continue

            path = os.path.join(root, filename)
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

            except Exception as e:
                print(f"Read error {path}: {e}")
                continue

            if len(coords) >= 2:
                key = os.path.relpath(path, folder)
                try:
                    highways[key] = LineString(coords)
                except:
                    continue

    print(f"Loaded {len(highways)} highways")
    return highways


# ----------------------------
# GEOMETRIC HELPERS
# ----------------------------
def centroid(geom):
    c = geom.centroid
    return (c.x, c.y)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ----------------------------
# BUILD HIGHWAY GRAPH (SPATIAL)
# ----------------------------
def build_graph(highways):
    nodes = {name: centroid(g) for name, g in highways.items()}

    return nodes


# ----------------------------
# GREEDY TRAVERSAL PATH
# ----------------------------
def build_traversal_path(highways):
    nodes = build_graph(highways)

    unvisited = set(nodes.keys())

    # start from an arbitrary highway
    current = next(iter(unvisited))
    unvisited.remove(current)

    path_points = [nodes[current]]

    while unvisited:
        current_pos = nodes[current]

        # find nearest unvisited highway centroid
        next_node = min(
            unvisited,
            key=lambda n: dist(current_pos, nodes[n])
        )

        path_points.append(nodes[next_node])
        unvisited.remove(next_node)
        current = next_node

    return LineString(path_points)


# ----------------------------
# COVERAGE CHECK (TRUE INTERSECTION)
# ----------------------------
def check_coverage(path, highways):
    missed = []

    for name, geom in highways.items():
        if not path.intersects(geom):
            missed.append(name)

    return missed


# ----------------------------
# OPTIONAL IMPROVEMENT LOOP
# (local refinement pass)
# ----------------------------
def refine_path(path, highways, iterations=10):
    coords = list(path.coords)

    for _ in range(iterations):
        missed = check_coverage(LineString(coords), highways)

        if not missed:
            break

        # insert centroid of missed highway near closest segment
        for name in missed[:20]:
            g = highways[name]
            mid = g.centroid

            best_i = 0
            best_d = float("inf")

            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i + 1]])
                d = seg.distance(mid)

                if d < best_d:
                    best_d = d
                    best_i = i + 1

            coords.insert(best_i, (mid.x, mid.y))

    return LineString(coords)


# ----------------------------
# SOLVE
# ----------------------------
def solve(folder, refine_iters=5):
    highways = load_highways(folder)

    if not highways:
        raise ValueError("No highways loaded")

    print("Building traversal path...")
    path = build_traversal_path(highways)

    print("Initial coverage check...")
    missed = check_coverage(path, highways)
    print(f"Missed initially: {len(missed)}")

    print("Refining path...")
    path = refine_path(path, highways, iterations=refine_iters)

    missed = check_coverage(path, highways)
    print(f"Final missed: {len(missed)}")

    return path, highways


# ----------------------------
# SAVE OUTPUT
# ----------------------------
def save_path(path, filename="path.txt"):
    with open(filename, "w") as f:
        for x, y in path.coords:
            f.write(f"{y} {x}\n")


# ----------------------------
# FOLIUM MAP
# ----------------------------
def plot_folium(path, highways, output_html="map.html"):
    import folium

    first_lon, first_lat = path.coords[0]
    m = folium.Map(location=[first_lat, first_lon], zoom_start=7)

    # highways
    for geom in highways.values():
        coords = [(lat, lon) for lon, lat in geom.coords]
        folium.PolyLine(coords, color="blue", weight=1).add_to(m)

    # path
    path_coords = [(lat, lon) for lon, lat in path.coords]
    folium.PolyLine(path_coords, color="red", weight=4).add_to(m)

    m.save(output_html)
    print(f"Saved map: {output_html}")


# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--output", default="path.txt")
    parser.add_argument("--map", action="store_true")

    args = parser.parse_args()

    path, highways = solve(args.folder)

    save_path(path, args.output)
    print(f"Saved: {args.output}")

    if args.map:
        plot_folium(path, highways)
