#!/usr/bin/env python3
"""
Generate a globe STL from real NOAA ETOPO 2022 relief data.

This version preserves narrow mountains and ocean trenches by downsampling the
source raster with extrema:
  - average: broad terrain/water classification
  - max: mountain and highland preservation
  - min: trench and abyssal preservation

The output STL is a closed, single-shell mesh in millimeters. STL does not
store units, so the companion report records the intended print scale.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np


MM_PER_INCH = 25.4
DIAMETER_INCHES = 12.0
TARGET_DIAMETER_MM = DIAMETER_INCHES * MM_PER_INCH
OUTER_RADIUS_MM = TARGET_DIAMETER_MM / 2.0

N_LON = 2160
N_LAT = 1080

ETOPO_NETCDF = Path("data/ETOPO_2022_v1_60s_N90W180_bed.nc")
ETOPO_SOURCE_URL = (
    "https://www.ngdc.noaa.gov/thredds/fileServer/global/ETOPO2022/60s/"
    "60s_bed_elev_netcdf/ETOPO_2022_v1_60s_N90W180_bed.nc"
)

OUTPUT_STL = Path("generated/globe_grid_12in_etopo_relief_extreme_mm.stl")
OUTPUT_REPORT = Path("generated/globe_grid_12in_etopo_relief_extreme_report.json")
OUTPUT_PREVIEW = Path("generated/globe_grid_12in_etopo_relief_extreme_preview.png")

RESAMPLED = {
    "average": Path(f"data/etopo2022_60s_bed_{N_LON}x{N_LAT}_average.dat"),
    "max": Path(f"data/etopo2022_60s_bed_{N_LON}x{N_LAT}_max.dat"),
    "min": Path(f"data/etopo2022_60s_bed_{N_LON}x{N_LAT}_min.dat"),
}

EVEREST_M = 8849.0
CHALLENGER_DEEP_M = 10935.0
MOUNTAIN_RELIEF_MM = 8.2
TRENCH_RELIEF_MM = 6.6
MINOR_GRID_MM = 0.45
MAJOR_GRID_MM = 1.05


def set_mesh_resolution(lon_segments: int, lat_rings: int | None = None) -> None:
    global N_LON, N_LAT, RESAMPLED

    if lat_rings is None:
        lat_rings = lon_segments // 2
    if lon_segments < 360 or lat_rings < 180:
        raise ValueError("Use at least 360 longitude segments and 180 latitude rings.")

    N_LON = lon_segments
    N_LAT = lat_rings
    RESAMPLED = {
        "average": Path(f"data/etopo2022_60s_bed_{N_LON}x{N_LAT}_average.dat"),
        "max": Path(f"data/etopo2022_60s_bed_{N_LON}x{N_LAT}_max.dat"),
        "min": Path(f"data/etopo2022_60s_bed_{N_LON}x{N_LAT}_min.dat"),
    }


def set_design_size(diameter_inches: float, output_prefix: str | None = None) -> None:
    global DIAMETER_INCHES, TARGET_DIAMETER_MM, OUTER_RADIUS_MM
    global OUTPUT_STL, OUTPUT_REPORT, OUTPUT_PREVIEW

    DIAMETER_INCHES = diameter_inches
    TARGET_DIAMETER_MM = DIAMETER_INCHES * MM_PER_INCH
    OUTER_RADIUS_MM = TARGET_DIAMETER_MM / 2.0

    if output_prefix is None:
        inch_slug = f"{diameter_inches:g}".replace(".", "p")
        output_prefix = f"globe_grid_{inch_slug}in_etopo_relief_extreme"

    OUTPUT_STL = Path(f"generated/{output_prefix}_mm.stl")
    OUTPUT_REPORT = Path(f"generated/{output_prefix}_report.json")
    OUTPUT_PREVIEW = Path(f"generated/{output_prefix}_preview.png")


def set_relief(
    mountain_relief_mm: float | None = None,
    trench_relief_mm: float | None = None,
    minor_grid_mm: float | None = None,
    major_grid_mm: float | None = None,
) -> None:
    global MOUNTAIN_RELIEF_MM, TRENCH_RELIEF_MM, MINOR_GRID_MM, MAJOR_GRID_MM

    if mountain_relief_mm is not None:
        MOUNTAIN_RELIEF_MM = mountain_relief_mm
    if trench_relief_mm is not None:
        TRENCH_RELIEF_MM = trench_relief_mm
    if minor_grid_mm is not None:
        MINOR_GRID_MM = minor_grid_mm
    if major_grid_mm is not None:
        MAJOR_GRID_MM = major_grid_mm


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required tool not found on PATH: {name}")


def maybe_download_source() -> None:
    if ETOPO_NETCDF.exists() and ETOPO_NETCDF.stat().st_size > 400_000_000:
        return
    require_tool("aria2c")
    ETOPO_NETCDF.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "aria2c",
            "--continue=true",
            "--max-tries=12",
            "--retry-wait=8",
            "--timeout=60",
            "--max-connection-per-server=1",
            "--split=1",
            f"--dir={ETOPO_NETCDF.parent}",
            f"--out={ETOPO_NETCDF.name}",
            ETOPO_SOURCE_URL,
        ]
    )


def resample_source(force: bool = False) -> None:
    require_tool("gdalwarp")
    maybe_download_source()
    source = f'NETCDF:"{ETOPO_NETCDF}":z'
    for method, output in RESAMPLED.items():
        if output.exists() and output.stat().st_size == N_LON * N_LAT * 4 and not force:
            continue
        output.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "gdalwarp",
                "-overwrite",
                "-multi",
                "-wm",
                "1024",
                "-of",
                "ENVI",
                "-ot",
                "Float32",
                "-t_srs",
                "EPSG:4326",
                "-te",
                "-180",
                "-90",
                "180",
                "90",
                "-ts",
                str(N_LON),
                str(N_LAT),
                "-r",
                method,
                source,
                str(output),
            ]
        )


def read_resampled() -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for method, path in RESAMPLED.items():
        expected = N_LON * N_LAT * 4
        if not path.exists() or path.stat().st_size != expected:
            raise FileNotFoundError(f"Missing {method} raster: {path}")
        # ENVI/GDAL writes north-to-south rows. Flip to south-to-north for mesh rings.
        arr = np.fromfile(path, dtype=np.float32).reshape(N_LAT, N_LON)[::-1].copy()
        if np.any(arr == -99999) or not np.isfinite(arr).all():
            raise RuntimeError(f"Invalid/nodata values found in {path}")
        arrays[method] = arr
    return arrays


def smooth_ridge(distance_deg: np.ndarray, half_width_deg: float) -> np.ndarray:
    x = np.clip(1.0 - np.abs(distance_deg) / half_width_deg, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def distance_to_multiple(values: np.ndarray, spacing_deg: float) -> np.ndarray:
    return np.abs((values + spacing_deg / 2.0) % spacing_deg - spacing_deg / 2.0)


def signed_elevation_to_mm(elevation_m: np.ndarray) -> np.ndarray:
    positive = np.clip(elevation_m, 0.0, EVEREST_M)
    negative = np.clip(-elevation_m, 0.0, CHALLENGER_DEEP_M)

    land = (positive / EVEREST_M) ** 0.74 * MOUNTAIN_RELIEF_MM
    ocean = -((negative / CHALLENGER_DEEP_M) ** 0.62) * TRENCH_RELIEF_MM
    return np.where(elevation_m >= 0.0, land, ocean).astype(np.float32)


def build_feature_preserving_elevation(arrays: dict[str, np.ndarray]) -> np.ndarray:
    avg = arrays["average"]
    max_elev = arrays["max"]
    min_elev = arrays["min"]

    # Use the average raster to decide whether a cell is broadly land or water,
    # then use extrema so narrow high ranges and trenches do not disappear.
    feature = np.where(avg >= 0.0, max_elev, min_elev)

    # Keep major islands/seamounts visible even if their cell average is water.
    feature = np.where((avg < 0.0) & (max_elev > 750.0), max_elev, feature)

    # Keep inland depressions and below-sea-level basins on otherwise land cells.
    feature = np.where((avg >= 0.0) & (min_elev < -250.0) & (max_elev < 400.0), min_elev, feature)

    return feature.astype(np.float32)


def build_relief_mm(elevation_m: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lons = np.linspace(-180.0 + 180.0 / N_LON, 180.0 - 180.0 / N_LON, N_LON)
    lats = np.linspace(-90.0 + 90.0 / N_LAT, 90.0 - 90.0 / N_LAT, N_LAT)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    terrain = signed_elevation_to_mm(elevation_m)

    lon_minor = smooth_ridge(distance_to_multiple(lon_grid, 15.0), 0.18)
    lat_minor = smooth_ridge(distance_to_multiple(lat_grid, 15.0), 0.18)
    lon_major = smooth_ridge(distance_to_multiple(lon_grid, 30.0), 0.28)
    lat_major = smooth_ridge(distance_to_multiple(lat_grid, 30.0), 0.28)
    grid = np.maximum(
        MINOR_GRID_MM * np.maximum(lon_minor, lat_minor),
        MAJOR_GRID_MM * np.maximum(lon_major, lat_major),
    ).astype(np.float32)

    return terrain + grid, lon_grid.astype(np.float32), lat_grid.astype(np.float32)


def build_mesh(relief_mm: np.ndarray, lon_grid: np.ndarray, lat_grid: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    base_radius = OUTER_RADIUS_MM - float(relief_mm.max())
    radius = base_radius + relief_mm

    lat_rad = np.radians(lat_grid)
    lon_rad = np.radians(lon_grid)
    cos_lat = np.cos(lat_rad)
    ring_vertices = np.stack(
        (
            radius * cos_lat * np.cos(lon_rad),
            radius * cos_lat * np.sin(lon_rad),
            radius * np.sin(lat_rad),
        ),
        axis=-1,
    ).reshape(-1, 3)

    south_radius = base_radius + float(np.mean(relief_mm[0]))
    north_radius = base_radius + float(np.mean(relief_mm[-1]))
    south = np.array([[0.0, 0.0, -south_radius]], dtype=np.float32)
    north = np.array([[0.0, 0.0, north_radius]], dtype=np.float32)
    vertices = np.vstack((south, ring_vertices.astype(np.float32), north))

    ring_ids = np.arange(1, 1 + N_LAT * N_LON, dtype=np.int32).reshape(N_LAT, N_LON)
    south_id = np.int32(0)
    north_id = np.int32(vertices.shape[0] - 1)

    face_count = N_LON + (N_LAT - 1) * N_LON * 2 + N_LON
    faces = np.empty((face_count, 3), dtype=np.int32)

    k = 0
    for j in range(N_LON):
        jn = (j + 1) % N_LON
        faces[k] = (south_id, ring_ids[0, jn], ring_ids[0, j])
        k += 1

    for i in range(N_LAT - 1):
        lower = ring_ids[i]
        upper = ring_ids[i + 1]
        for j in range(N_LON):
            jn = (j + 1) % N_LON
            faces[k] = (lower[j], lower[jn], upper[jn])
            k += 1
            faces[k] = (lower[j], upper[jn], upper[j])
            k += 1

    last = ring_ids[-1]
    for j in range(N_LON):
        jn = (j + 1) % N_LON
        faces[k] = (north_id, last[j], last[jn])
        k += 1

    if k != face_count:
        raise RuntimeError(f"Face count mismatch: wrote {k}, expected {face_count}")

    metadata = {
        "diameter_inches": DIAMETER_INCHES,
        "target_diameter_mm": TARGET_DIAMETER_MM,
        "outer_radius_mm": OUTER_RADIUS_MM,
        "base_radius_mm": base_radius,
        "mesh_resolution": {
            "longitude_segments": N_LON,
            "latitude_rings": N_LAT,
            "equator_vertex_spacing_mm": (math.pi * TARGET_DIAMETER_MM) / N_LON,
        },
        "relief_scaling": {
            "mountain_relief_mm_at_8849m": MOUNTAIN_RELIEF_MM,
            "trench_relief_mm_at_10935m": -TRENCH_RELIEF_MM,
            "minor_grid_height_mm": MINOR_GRID_MM,
            "major_grid_height_mm": MAJOR_GRID_MM,
        },
        "source": {
            "dataset": "NOAA ETOPO 2022 60 arc-second bed elevation NetCDF",
            "url": ETOPO_SOURCE_URL,
            "vertical_units": "meters relative to EGM2008 geoid",
            "resampling": "average for land/water classification, max for mountains, min for trenches",
        },
    }
    return vertices, faces, metadata


def scale_to_print_bounding_box(vertices: np.ndarray, metadata: dict) -> None:
    dimensions = vertices.max(axis=0) - vertices.min(axis=0)
    longest_dimension = float(dimensions.max())
    scale = TARGET_DIAMETER_MM / longest_dimension
    vertices *= np.float32(scale)
    metadata["print_scale"] = {
        "mode": f"uniform scale so the STL bounding box longest dimension is exactly {DIAMETER_INCHES:g} inches",
        "pre_scale_dimensions_mm": [float(v) for v in dimensions],
        "pre_scale_longest_dimension_mm": longest_dimension,
        "uniform_scale_factor": scale,
    }


def signed_volume(vertices: np.ndarray, faces: np.ndarray, chunk_size: int = 100_000) -> float:
    total = 0.0
    for start in range(0, len(faces), chunk_size):
        tri = vertices[faces[start : start + chunk_size]].astype(np.float64)
        total += np.einsum("ij,ij->", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])) / 6.0
    return float(total)


def validate_mesh(vertices: np.ndarray, faces: np.ndarray) -> dict:
    print("Validating mesh...")
    edges = np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges.sort(axis=1)
    unique_edges, counts = np.unique(edges, axis=0, return_counts=True)
    boundary_edges = int(np.count_nonzero(counts == 1))
    nonmanifold_edges = int(np.count_nonzero(counts > 2))
    euler = int(vertices.shape[0] - unique_edges.shape[0] + faces.shape[0])
    volume = signed_volume(vertices, faces)
    if volume < 0:
        faces[:, [1, 2]] = faces[:, [2, 1]]
        volume = signed_volume(vertices, faces)
    bounds_min = vertices.min(axis=0)
    bounds_max = vertices.max(axis=0)
    dimensions = bounds_max - bounds_min
    radii = np.linalg.norm(vertices.astype(np.float64), axis=1)
    return {
        "vertices": int(vertices.shape[0]),
        "faces": int(faces.shape[0]),
        "unique_edges": int(unique_edges.shape[0]),
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
        "euler_characteristic": euler,
        "signed_volume_mm3": volume,
        "bounds_min_mm": [float(v) for v in bounds_min],
        "bounds_max_mm": [float(v) for v in bounds_max],
        "dimensions_mm": [float(v) for v in dimensions],
        "max_radius_mm": float(radii.max()),
        "min_radius_mm": float(radii.min()),
        "watertight": boundary_edges == 0 and nonmanifold_edges == 0 and euler == 2,
    }


def write_binary_stl(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    print(f"Writing binary STL: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    header_text = f"{DIAMETER_INCHES:g} inch NOAA ETOPO relief globe, units=millimeters"
    header = header_text.encode("ascii", errors="replace")[:80].ljust(80, b" ")
    with path.open("wb") as f:
        f.write(header)
        f.write(struct.pack("<I", faces.shape[0]))
        chunk_size = 60_000
        for start in range(0, len(faces), chunk_size):
            tri = vertices[faces[start : start + chunk_size]].astype(np.float32)
            normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            lengths = np.linalg.norm(normals, axis=1)
            safe = lengths > 0
            normals[safe] /= lengths[safe, None]

            records = np.zeros(
                tri.shape[0],
                dtype=[("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attr", "<u2")],
            )
            records["normal"] = normals
            records["vertices"] = tri
            f.write(records.tobytes())


def write_preview(path: Path, vertices: np.ndarray, elevation_m: np.ndarray) -> None:
    print(f"Writing preview PNG: {path}")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rings = vertices[1:-1].reshape(N_LAT, N_LON, 3)
    stride = 6
    surface = rings[::stride, ::stride]
    surface = np.concatenate([surface, surface[:, :1]], axis=1)

    elev = elevation_m[::stride, ::stride]
    elev = np.concatenate([elev, elev[:, :1]], axis=1)
    normalized = np.where(elev >= 0, 0.55 + 0.45 * np.clip(elev / EVEREST_M, 0, 1), 0.55 * (1 - np.clip(-elev / CHALLENGER_DEEP_M, 0, 1)))
    colors = plt.cm.terrain(normalized)

    fig = plt.figure(figsize=(12, 5), dpi=180)
    views = [(18, -70, "Americas"), (20, 20, "Europe/Africa"), (18, 105, "Asia/Pacific")]
    for idx, (elev_angle, azim, title) in enumerate(views, start=1):
        ax = fig.add_subplot(1, 3, idx, projection="3d")
        ax.plot_surface(
            surface[:, :, 0],
            surface[:, :, 1],
            surface[:, :, 2],
            facecolors=colors,
            rstride=1,
            cstride=1,
            linewidth=0,
            shade=True,
            antialiased=True,
        )
        ax.set_title(title, fontsize=10)
        ax.view_init(elev=elev_angle, azim=azim)
        ax.set_box_aspect((1, 1, 1))
        ax.set_axis_off()
        lim = OUTER_RADIUS_MM * 1.04
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_zlim(-lim, lim)
    fig.tight_layout(pad=0.6)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diameter-inches", type=float, default=12.0)
    parser.add_argument("--lon-segments", type=int, default=2160)
    parser.add_argument("--lat-rings", type=int)
    parser.add_argument("--mountain-relief-mm", type=float)
    parser.add_argument("--trench-relief-mm", type=float)
    parser.add_argument("--minor-grid-mm", type=float)
    parser.add_argument("--major-grid-mm", type=float)
    parser.add_argument("--output-prefix")
    parser.add_argument("--force-resample", action="store_true")
    parser.add_argument("--skip-preview", action="store_true")
    args = parser.parse_args()

    set_mesh_resolution(args.lon_segments, args.lat_rings)
    set_design_size(args.diameter_inches, args.output_prefix)
    set_relief(
        mountain_relief_mm=args.mountain_relief_mm,
        trench_relief_mm=args.trench_relief_mm,
        minor_grid_mm=args.minor_grid_mm,
        major_grid_mm=args.major_grid_mm,
    )
    resample_source(force=args.force_resample)
    arrays = read_resampled()
    elevation = build_feature_preserving_elevation(arrays)
    relief_mm, lon_grid, lat_grid = build_relief_mm(elevation)
    vertices, faces, metadata = build_mesh(relief_mm, lon_grid, lat_grid)
    scale_to_print_bounding_box(vertices, metadata)

    metadata["source_elevation_stats_m"] = {
        "feature_min": float(elevation.min()),
        "feature_max": float(elevation.max()),
        "average_min": float(arrays["average"].min()),
        "average_max": float(arrays["average"].max()),
        "block_min_min": float(arrays["min"].min()),
        "block_max_max": float(arrays["max"].max()),
    }
    metadata["print_relief_stats_mm"] = {
        "surface_relief_min": float(relief_mm.min()),
        "surface_relief_max": float(relief_mm.max()),
        "surface_relief_range": float(relief_mm.max() - relief_mm.min()),
        "final_scaled_surface_relief_range": float((relief_mm.max() - relief_mm.min()) * metadata["print_scale"]["uniform_scale_factor"]),
    }

    validation = validate_mesh(vertices, faces)
    metadata["validation"] = validation
    if not validation["watertight"]:
        raise RuntimeError(f"Mesh failed watertight validation: {validation}")

    write_binary_stl(OUTPUT_STL, vertices, faces)
    OUTPUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_REPORT.write_text(json.dumps(metadata, indent=2) + "\n")
    if not args.skip_preview:
        write_preview(OUTPUT_PREVIEW, vertices, elevation)

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
