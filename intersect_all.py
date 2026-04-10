import os
import argparse
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

# ----------------------------
# LOAD WPT FILES
# ----------------------------
def load_highways(folder):
    highways = {}

    for root, _, files in os.walk(folder):
        for filename in files:
            if not filename.endswith(".wpt"):
                continue

            path = os.path.join(root, filename)
            coords = []

            with open(path, encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) < 3:
                        continue

                    try:
                        lat = float(parts[-2])
                        lon = float(parts[-1])
                        coords.append((lon, lat))  # shapely uses (x, y)
                    except ValueError:
                        continue

            if len(coords) >= 2:
                highways[filename] = LineString(coords)

    return highways


# ----------------------------
# CREATE ZIGZAG PATH
# ----------------------------
def make_zigzag(bounds, passes=12):
    minx, miny, maxx, maxy = bounds
    step = (maxy - miny) / passes

    points = []
    y = miny
    direction = 1

    for _ in range(passes + 1):
        if direction == 1:
            points.append((minx, y))
            points.append((maxx, y))
        else:
            points.append((maxx, y))
            points.append((minx, y))

        direction *= -1
        y += step

    return LineString(points)


# ----------------------------
# CHECK INTERSECTIONS
# ----------------------------
def check_coverage(path, highways):
    missed = []

    for name, geom in highways.items():
        if not path.intersects(geom):
            missed.append(name)

    return missed


# ----------------------------
# ADD DETOUR TO A HIGHWAY
# ----------------------------
def add_detour(path, geom):
    midpoint = geom.interpolate(0.5, normalized=True)

    coords = list(path.coords)

    # Insert detour near closest point instead of just appending
    min_dist = float("inf")
    insert_index = 0

    for i in range(len(coords) - 1):
        seg = LineString([coords[i], coords[i + 1]])
        dist = seg.distance(midpoint)

        if dist < min_dist:
            min_dist = dist
            insert_index = i + 1

    coords.insert(insert_index, (midpoint.x, midpoint.y))

    return LineString(coords)


# ----------------------------
# MAIN SOLVER
# ----------------------------
def solve(folder, passes=12, max_iter=50):
    print("Loading highways...")
    highways = load_highways(folder)
    print(f"Loaded {len(highways)} highways")

    print("Building bounding box...")
    union = unary_union(list(highways.values()))
    bounds = union.bounds

    print("Creating initial zig-zag path...")
    path = make_zigzag(bounds, passes=passes)

    for iteration in range(max_iter):
        missed = check_coverage(path, highways)

        print(f"Iteration {iteration+1}: {len(missed)} highways missed")

        if not missed:
            print("✅ All highways intersected!")
            break

        # Add detours for a batch of missed highways
        for name in missed[:10]:
            path = add_detour(path, highways[name])

    return path, highways


# ----------------------------
# OPTIONAL PLOTTING
# ----------------------------
def plot_result(path, highways):
    import matplotlib.pyplot as plt

    for geom in highways.values():
        x, y = geom.xy
        plt.plot(x, y)

    x, y = path.xy
    plt.plot(x, y, linewidth=2)

    plt.title("Intersect-All Path")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.show()


# ----------------------------
# SAVE PATH
# ----------------------------
def save_path(path, filename="path.txt"):
    with open(filename, "w") as f:
        for x, y in path.coords:
            f.write(f"{y} {x}\n")  # lat lon format


# ----------------------------
# ENTRY POINT
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intersect all highways from WPT files")
    parser.add_argument("folder", help="Path to WPT folder (e.g., hwy_data/AR)")
    parser.add_argument("--passes", type=int, default=12, help="Zig-zag density")
    parser.add_argument("--plot", action="store_true", help="Show plot")
    parser.add_argument("--output", default="path.txt", help="Output file")

    args = parser.parse_args()

    path, highways = solve(args.folder, passes=args.passes)

    save_path(path, args.output)
    print(f"Saved path to {args.output}")

    if args.plot:
        plot_result(path, highways)
