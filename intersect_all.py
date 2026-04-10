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
    total_files = 0
    failed_files = 0

    for root, _, files in os.walk(folder):
        for filename in files:
            if not filename.lower().endswith(".wpt"):
                continue

            total_files += 1
            path = os.path.join(root, filename)
            coords = []

            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        lat_match = LAT_RE.search(line)
                        lon_match = LON_RE.search(line)

                        if not lat_match or not lon_match:
                            continue

                        lat = float(lat_match.group(1))
                        lon = float(lon_match.group(1))

                        coords.append((lon, lat))  # shapely uses (x, y)

            except Exception as e:
                print(f"❌ Failed reading {path}: {e}")
                failed_files += 1
                continue

            # IMPORTANT: avoid overwriting duplicates
            key = os.path.relpath(path, folder)

            if len(coords) < 2:
                continue

            try:
                geom = LineString(coords)

                if not geom.is_valid or geom.is_empty:
                    continue

                highways[key] = geom

            except Exception as e:
                print(f"❌ Invalid geometry {key}: {e}")

    print(f"\n📦 WPT files scanned: {total_files}")
    print(f"⚠️ Failed files: {failed_files}")
    print(f"✅ Loaded highways: {len(highways)}\n")

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
