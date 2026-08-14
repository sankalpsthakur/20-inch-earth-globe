# Scripts

| Script | What it does |
|---|---|
| `make_etopo_relief_globe_stl.py` | Build a closed globe STL from NOAA ETOPO 2022 |
| `split_and_cap_hemispheres.py` | Cut a closed globe at the equator and cap each half |

Generator extras (`gdalwarp`, `aria2c`) are only needed when you rebuild
from the NetCDF. Splitting an existing STL needs `numpy` only.

The released north/south files are already split. Use the cap script if
your slicer rejects the open equatorial rim.
