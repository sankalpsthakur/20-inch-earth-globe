#!/usr/bin/env python3
"""Build a medium-res colored globe mesh for the Twitter preview clip.

Reads the existing NOAA ETOPO resampled rasters (same source as the
20-inch STLs), downsamples to 720x360, and writes a binary PLY with
vertex colors. This is a preview mesh, not a print file.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


EVEREST_M = 8849.0
CHALLENGER_DEEP_M = 10935.0
MOUNTAIN_RELIEF_MM = 13.5
TRENCH_RELIEF_MM = 11.0
MINOR_GRID_MM = 0.7
MAJOR_GRID_MM = 1.6
RADIUS_MM = 254.0

SRC_LON, SRC_LAT = 2160, 1080
DATA_DIR = Path("/Users/sankalp/Projects/experiment/global-grids/data")


def load_feature_elevation() -> np.ndarray:
    def read(name: str) -> np.ndarray:
        path = DATA_DIR / f"etopo2022_60s_bed_{SRC_LON}x{SRC_LAT}_{name}.dat"
        arr = np.fromfile(path, dtype=np.float32).reshape(SRC_LAT, SRC_LON)[::-1].copy()
        return arr

    avg, mx, mn = read("average"), read("max"), read("min")
    feature = np.where(avg >= 0.0, mx, mn)
    feature = np.where((avg < 0.0) & (mx > 750.0), mx, feature)
    feature = np.where((avg >= 0.0) & (mn < -250.0) & (mx < 400.0), mn, feature)
    return feature.astype(np.float32)


def signed_elevation_to_mm(elevation_m: np.ndarray) -> np.ndarray:
    positive = np.clip(elevation_m, 0.0, EVEREST_M)
    negative = np.clip(-elevation_m, 0.0, CHALLENGER_DEEP_M)
    land = (positive / EVEREST_M) ** 0.74 * MOUNTAIN_RELIEF_MM
    ocean = -((negative / CHALLENGER_DEEP_M) ** 0.62) * TRENCH_RELIEF_MM
    return np.where(elevation_m >= 0.0, land, ocean).astype(np.float32)


def smooth_ridge(distance_deg: np.ndarray, half_width_deg: float) -> np.ndarray:
    x = np.clip(1.0 - np.abs(distance_deg) / half_width_deg, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def distance_to_multiple(values: np.ndarray, spacing_deg: float) -> np.ndarray:
    return np.abs((values + spacing_deg / 2.0) % spacing_deg - spacing_deg / 2.0)


def downsample(arr: np.ndarray, n_lon: int, n_lat: int) -> np.ndarray:
    step_lon = arr.shape[1] // n_lon
    step_lat = arr.shape[0] // n_lat
    return arr[::step_lat, ::step_lon][:n_lat, :n_lon]


def build(n_lon: int, n_lat: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    elevation = downsample(load_feature_elevation(), n_lon, n_lat)
    lons = np.linspace(-180.0 + 180.0 / n_lon, 180.0 - 180.0 / n_lon, n_lon)
    lats = np.linspace(-90.0 + 90.0 / n_lat, 90.0 - 90.0 / n_lat, n_lat)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    terrain = signed_elevation_to_mm(elevation)
    lon_minor = smooth_ridge(distance_to_multiple(lon_grid, 15.0), 0.18)
    lat_minor = smooth_ridge(distance_to_multiple(lat_grid, 15.0), 0.18)
    lon_major = smooth_ridge(distance_to_multiple(lon_grid, 30.0), 0.28)
    lat_major = smooth_ridge(distance_to_multiple(lat_grid, 30.0), 0.28)
    grid = np.maximum(
        MINOR_GRID_MM * np.maximum(lon_minor, lat_minor),
        MAJOR_GRID_MM * np.maximum(lon_major, lat_major),
    )
    relief = terrain + grid
    radius = (RADIUS_MM - float(relief.max())) + relief

    lat_rad = np.radians(lat_grid)
    lon_rad = np.radians(lon_grid)
    cos_lat = np.cos(lat_rad)
    verts = np.stack(
        (
            radius * cos_lat * np.cos(lon_rad),
            radius * cos_lat * np.sin(lon_rad),
            radius * np.sin(lat_rad),
        ),
        axis=-1,
    ).reshape(-1, 3)

    # Faces wrap longitude. Skip poles as a fan-less strip mesh.
    faces = []
    for i in range(n_lat - 1):
        for j in range(n_lon):
            jn = (j + 1) % n_lon
            a = i * n_lon + j
            b = i * n_lon + jn
            c = (i + 1) * n_lon + jn
            d = (i + 1) * n_lon + j
            faces.append((a, b, c))
            faces.append((a, c, d))
    faces = np.asarray(faces, dtype=np.int32)

    normalized = np.where(
        elevation >= 0,
        0.55 + 0.45 * np.clip(elevation / EVEREST_M, 0, 1),
        0.55 * (1.0 - np.clip(-elevation / CHALLENGER_DEEP_M, 0, 1)),
    )
    colors = (plt.cm.terrain(normalized.ravel())[:, :3] * 255.0).astype(np.uint8)
    # Lift grid ribs so they read on camera.
    rib = (grid.ravel() > 0.35).astype(np.float32)
    colors = colors.astype(np.float32)
    colors = colors * (1.0 - 0.35 * rib[:, None]) + np.array([235, 228, 210]) * (0.35 * rib[:, None])
    colors = np.clip(colors, 0, 255).astype(np.uint8)
    return verts.astype(np.float32), faces, colors


def write_ply(path: Path, verts: np.ndarray, faces: np.ndarray, colors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {len(verts)}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        f"element face {len(faces)}\n"
        "property list uchar int vertex_indices\n"
        "end_header\n"
    ).encode("ascii")
    vert_rec = np.zeros(
        len(verts),
        dtype=[("xyz", "<f4", 3), ("rgb", "u1", 3)],
    )
    vert_rec["xyz"] = verts
    vert_rec["rgb"] = colors
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(vert_rec.tobytes())
        for tri in faces:
            handle.write(struct.pack("<Biii", 3, int(tri[0]), int(tri[1]), int(tri[2])))
    print(f"wrote {path}  verts={len(verts)} faces={len(faces)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lon", type=int, default=720)
    parser.add_argument("--lat", type=int, default=360)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/Users/sankalp/Projects/20-inch-earth-globe/docs/preview-video/globe_preview.ply"),
    )
    args = parser.parse_args()
    verts, faces, colors = build(args.lon, args.lat)
    write_ply(args.out, verts, faces, colors)


if __name__ == "__main__":
    main()
