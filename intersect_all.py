import os
import re
import argparse
from shapely.geometry import LineString
from shapely.ops import unary_union

# ----------------------------
# REGEX (robust extraction)
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# LOAD WPT FILES (FIXED)
# ----------------------------
def load_highways(folder):
    highways = {}

    for root, _, files in os.walk(folder):
        for filename in files:
            if not filename.endswith(".wpt"):
                continue

            path = os.path.join(root, filename)

            print("\nREADING:", path)

            coords = []

            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if "lat=" not in line or "lon=" not in line:
                        print("SKIP LINE:", line)
                        continue

                    import re
                    lat = re.search(r"lat=([-0-9.]+)", line)
                    lon = re.search(r"lon=([-0-9.]+)", line)

                    if not lat or not lon:
                        print("FAILED PARSE:", line)
                        continue

                    coords.append((float(lon.group(1)), float(lat.group(1))))

            print("COORDS FOUND:", len(coords))

            if len(coords) >= 2:
                highways[path] = LineString(coords)

    return highways

# ----------------------------
# CREATE ZIGZAG PATH
# ----------------------------
def make_zigzag(bounds, passes=12):
    minx, miny, maxx, maxy = bounds
    step = (maxy - miny) / max(passes, 1)

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
# CHECK COVERAGE
# ----------------------------
def check_coverage(path, highways):
    missed = []

    for name, geom in highways.items():
        if not path.intersects(geom):
            missed.append(name)

    return missed


# ----------------------------
# ADD DETOUR (unchanged logic)
# ----------------------------
def add_detour(path, geom):
    midpoint = geom.interpolate(0.5, normalized=True)

    coords = list(path.coords)

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
# SOLVER
# ----------------------------
def solve(folder, passes=12, max_iter=50):
    print("Loading highways...")
    highways = load_highways(folder)

    if not highways:
        raise ValueError("❌ No highways loaded. Check folder path or WPT parsing.")

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

        for name in missed[:10]:
            path = add_detour(path, highways[name])

    return path, highways


# ----------------------------
# PLOTTING
# ----------------------------
def plot_result(path, highways):
    import matplotlib.pyplot as plt

    for geom in highways.values():
        x, y = geom.xy
        plt.plot(x, y, linewidth=0.5)

    x, y = path.xy
    plt.plot(x, y, linewidth=2)

    plt.title("Intersect-All Path")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.show()


# ----------------------------
# SAVE OUTPUT
# ----------------------------
def save_path(path, filename="path.txt"):
    with open(filename, "w") as f:
        for x, y in path.coords:
            f.write(f"{y} {x}\n")


# ----------------------------
# ENTRY POINT
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intersect all highways from WPT files")
    parser.add_argument("folder")
    parser.add_argument("--passes", type=int, default=12)
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--output", default="path.txt")

    args = parser.parse_args()

    path, highways = solve(args.folder, passes=args.passes)

    save_path(path, args.output)
    print(f"Saved path to {args.output}")

    if args.plot:
        plot_result(path, highways)
