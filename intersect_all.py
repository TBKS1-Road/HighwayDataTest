import os
import re
import argparse
from shapely.geometry import LineString

# ----------------------------
# FAST PATTERN (compiled once)
# ----------------------------
LAT_RE = re.compile(r"lat=([-0-9.]+)")
LON_RE = re.compile(r"lon=([-0-9.]+)")


# ----------------------------
# LOAD WPT FILES (OPTIMIZED)
# ----------------------------
def load_highways(folder):
    highways = {}
    total_files = 0
    total_coords = 0

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
                        # FAST FILTER (avoid regex unless needed)
                        if "lat=" not in line or "lon=" not in line:
                            continue

                        lat_m = LAT_RE.search(line)
                        lon_m = LON_RE.search(line)

                        if not lat_m or not lon_m:
                            continue

                        coords.append((
                            float(lon_m.group(1)),
                            float(lat_m.group(1))
                        ))

            except Exception as e:
                print(f"❌ Read error {path}: {e}")
                continue

            if len(coords) >= 2:
                key = os.path.relpath(path, folder)
                try:
                    highways[key] = LineString(coords)
                    total_coords += len(coords)
                except Exception as e:
                    print(f"❌ Geometry error {key}: {e}")

            if total_files % 200 == 0:
                print(f"📦 Processed {total_files} files...")

    print("\n========================")
    print(f"📁 Files scanned: {total_files}")
    print(f"🧭 Highways loaded: {len(highways)}")
    print(f"📍 Total coords: {total_coords}")
    print("========================\n")

    return highways


# ----------------------------
# FAST BOUNDS (NO unary_union)
# ----------------------------
def compute_bounds(highways):
    minx = min(g.bounds[0] for g in highways.values())
    miny = min(g.bounds[1] for g in highways.values())
    maxx = max(g.bounds[2] for g in highways.values())
    maxy = max(g.bounds[3] for g in highways.values())

    return (minx, miny, maxx, maxy)


# ----------------------------
# ZIGZAG PATH
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
# COVERAGE CHECK
# ----------------------------
def check_coverage(path, highways):
    return [
        name for name, geom in highways.items()
        if not path.intersects(geom)
    ]


# ----------------------------
# DETOUR INSERTION
# ----------------------------
def add_detour(path, geom):
    midpoint = geom.interpolate(0.5, normalized=True)
    coords = list(path.coords)

    best_i = 0
    best_d = float("inf")

    for i in range(len(coords) - 1):
        seg = LineString([coords[i], coords[i + 1]])
        d = seg.distance(midpoint)

        if d < best_d:
            best_d = d
            best_i = i + 1

    coords.insert(best_i, (midpoint.x, midpoint.y))
    return LineString(coords)


# ----------------------------
# SOLVER
# ----------------------------
def solve(folder, passes=12, max_iter=50):
    print("Loading highways...")
    highways = load_highways(folder)

    if not highways:
        raise ValueError("❌ No highways loaded. Check folder path or WPT format.")

    print("Computing bounds (fast)...")
    bounds = compute_bounds(highways)

    print("Creating initial zig-zag path...")
    path = make_zigzag(bounds, passes)

    for i in range(max_iter):
        missed = check_coverage(path, highways)

        print(f"Iteration {i+1}: missed {len(missed)}")

        if not missed:
            print("✅ All highways intersected!")
            break

        for name in missed[:10]:
            path = add_detour(path, highways[name])

    return path, highways


# ----------------------------
# SAVE OUTPUT
# ----------------------------
def save_path(path, filename="path.txt"):
    with open(filename, "w") as f:
        for x, y in path.coords:
            f.write(f"{y} {x}\n")


# ----------------------------
# OPTIONAL PLOT
# ----------------------------
def plot_result(path, highways):
    import matplotlib.pyplot as plt

    for g in highways.values():
        x, y = g.xy
        plt.plot(x, y, linewidth=0.4)

    x, y = path.xy
    plt.plot(x, y, linewidth=2)

    plt.title("Intersect-All Path")
    plt.show()


# ----------------------------
# ENTRY
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--passes", type=int, default=12)
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--output", default="path.txt")

    args = parser.parse_args()

    path, highways = solve(args.folder, passes=args.passes)

    save_path(path, args.output)
    print(f"Saved to {args.output}")

    if args.plot:
        plot_result(path, highways)
