#!/usr/bin/env python3
"""Split a closed globe STL at the equator and cap each half.

The generator writes a Z-up sphere (north = +Z). Released print files
were later rotated to Y-up. Pass --axis y for those files, or leave the
default --axis z for a fresh generator mesh.

The cap is a triangle fan from the boundary barycenter. That is enough
to make most slicers treat the half as a solid they can then hollow.
"""

from __future__ import annotations

import argparse
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np


def read_binary_stl(path: Path) -> tuple[bytes, np.ndarray]:
    with path.open("rb") as handle:
        header = handle.read(80)
        count = struct.unpack("<I", handle.read(4))[0]
        raw = handle.read(count * 50)
    if len(raw) != count * 50:
        raise RuntimeError(f"{path} looks truncated")
    records = np.frombuffer(
        raw,
        dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
    )
    return header, records.copy()


def write_binary_stl(path: Path, header: bytes, vertices: np.ndarray) -> None:
    header = header[:80].ljust(80, b" ")
    normals = np.cross(vertices[:, 1] - vertices[:, 0], vertices[:, 2] - vertices[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    safe = lengths > 0
    normals[safe] /= lengths[safe, None]
    records = np.zeros(
        len(vertices),
        dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
    )
    records["n"] = normals
    records["v"] = vertices
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(vertices)))
        handle.write(records.tobytes())


def axis_index(name: str) -> int:
    try:
        return "xyz".index(name.lower())
    except ValueError as exc:
        raise ValueError("--axis must be x, y, or z") from exc


def split_records(records: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    centroids = records["v"].mean(axis=1)
    north = records[centroids[:, axis] >= 0.0]
    south = records[centroids[:, axis] < 0.0]
    if len(north) == 0 or len(south) == 0:
        raise RuntimeError("Split produced an empty hemisphere. Check --axis.")
    return north, south


def quantize_key(point: np.ndarray, decimals: int = 4) -> tuple[float, float, float]:
    return tuple(np.round(point, decimals).tolist())


def boundary_loop(vertices: np.ndarray) -> np.ndarray:
    """Return an ordered loop of unique vertices that have a boundary edge."""
    edge_count: dict[tuple[tuple[float, float, float], tuple[float, float, float]], int] = defaultdict(int)
    edge_points: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
    for tri in vertices:
        for i in range(3):
            a = tri[i]
            b = tri[(i + 1) % 3]
            ka, kb = quantize_key(a), quantize_key(b)
            key = (ka, kb) if ka <= kb else (kb, ka)
            edge_count[key] += 1
            edge_points[key] = (a, b)

    boundary = [key for key, count in edge_count.items() if count == 1]
    if not boundary:
        raise RuntimeError("No boundary edges found; mesh may already be closed.")

    adjacency: dict[tuple, list[np.ndarray]] = defaultdict(list)
    for ka, kb in boundary:
        a, b = edge_points[(ka, kb)]
        adjacency[ka].append(b)
        adjacency[kb].append(a)

    start = boundary[0][0]
    loop = [np.array(start, dtype=np.float32)]
    previous = None
    current = start
    for _ in range(len(boundary) + 2):
        options = adjacency[current]
        nxt = None
        for candidate in options:
            ck = quantize_key(candidate)
            if previous is not None and ck == previous:
                continue
            nxt = candidate
            break
        if nxt is None:
            break
        if quantize_key(nxt) == start:
            break
        loop.append(nxt.astype(np.float32))
        previous = current
        current = quantize_key(nxt)
    return np.vstack(loop)


def cap_hemisphere(records: np.ndarray, axis: int, north: bool) -> np.ndarray:
    surface = records["v"].astype(np.float32)
    try:
        loop = boundary_loop(surface)
    except RuntimeError:
        return surface
    center = loop.mean(axis=0)
    # Fan winding: north half needs the cap normal pointing toward -axis
    # (into the solid) when viewed from outside the equator plane.
    caps = []
    for i in range(len(loop)):
        a = loop[i]
        b = loop[(i + 1) % len(loop)]
        if north:
            caps.append((center, b, a))
        else:
            caps.append((center, a, b))
    return np.concatenate([surface, np.asarray(caps, dtype=np.float32)], axis=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl", type=Path, help="Closed globe STL in millimeters")
    parser.add_argument("--axis", default="z", help="Polar axis of the input mesh (x/y/z)")
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    parser.add_argument("--prefix", default=None, help="Output filename prefix")
    args = parser.parse_args()

    axis = axis_index(args.axis)
    header, records = read_binary_stl(args.stl)
    north, south = split_records(records, axis)
    north_capped = cap_hemisphere(north, axis, north=True)
    south_capped = cap_hemisphere(south, axis, north=False)

    prefix = args.prefix or args.stl.stem
    args.output_dir.mkdir(parents=True, exist_ok=True)
    north_path = args.output_dir / f"{prefix}_NORTH_capped_mm.stl"
    south_path = args.output_dir / f"{prefix}_SOUTH_capped_mm.stl"
    write_binary_stl(north_path, f"north hemisphere capped, axis={args.axis}".encode(), north_capped)
    write_binary_stl(south_path, f"south hemisphere capped, axis={args.axis}".encode(), south_capped)
    print(f"north triangles: {len(north_capped)} -> {north_path}")
    print(f"south triangles: {len(south_capped)} -> {south_path}")


if __name__ == "__main__":
    main()
