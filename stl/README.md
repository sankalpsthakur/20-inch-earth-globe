# Print files

The two 20-inch hemisphere STLs are too large for a normal git clone
(~200 MB each). Download them from the
[latest GitHub Release](https://github.com/sankalpsthakur/20-inch-earth-globe/releases/latest).

| File | Size | Role |
|---|---:|---|
| `globe_grid_20in_NORTH_hemisphere_mm.stl` | 200 MB | Northern hemisphere, equator cut |
| `globe_grid_20in_SOUTH_hemisphere_mm.stl` | 196 MB | Southern hemisphere, equator cut |

After download:

```bash
shasum -a 256 -c stl/SHA256SUMS
```

Units are **millimeters**. STL does not store units, so tell the slicer
explicitly: import as mm, do not scale unless you want a smaller globe.
