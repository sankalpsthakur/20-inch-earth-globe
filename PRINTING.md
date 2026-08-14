# Printing a 20-inch Earth globe

Two files. Print one northern hemisphere and one southern hemisphere.
Glue them at the equator.

## What you are printing

The released STLs are the outer surface of a 20-inch (508 mm) globe,
split at the equator. They come from the high-resolution NOAA ETOPO
master mesh (2,880 longitude segments × 1,440 latitude rings). Triangle
counts of the two halves add up to the uncut master: 8,294,400 faces.

| | North | South |
|---|---:|---:|
| File size | 200 MB | 196 MB |
| Triangles | 4,185,251 | 4,109,149 |
| Bounding box (mm) | 499 × 254 × 504 | 494 × 254 × 508 |
| Polar axis | +Y is north | −Y is south |
| Equator | near Y = 0 | near Y = 0 |

Relief on the master (after the uniform 20-inch fit):

- Everest-scale peaks sit about **13.5 mm** above the ocean surface
- Challenger Deep-scale trenches sit about **11 mm** below
- Minor grid (15°) is 0.7 mm high; major grid (30°) is 1.6 mm high
- Equator vertex spacing is about 0.55 mm — fine enough for a 0.4 mm nozzle

The cut is an **open equatorial rim**, not a solid half-ball. That is
what you want. A closed solid 20-inch hemisphere would be ~30 liters of
plastic. Treat these as shells: thicken or hollow before you print.

## Printer you actually need

Print each half **equator-down** (flat rim on the bed, pole pointing up).

Required build volume:

```
X ≥ 510 mm
Y ≥ 510 mm
Z ≥ 260 mm
```

That rules out almost every desktop machine at full size.

| Path | What to do |
|---|---|
| Large-format FDM (Modix, RatRig 500, industrial CoreXY) | Print both halves at 100% |
| Service bureau / farm with a 500 mm+ bed | Send the two Release STLs, ask for a hollow shell |
| 350 mm-class printer (Voron 350, Prusa XL, Bambu H2D) | Scale to 68% → ~13.6 inch globe, or slice into gores |
| 256 mm-class printer (Bambu X1/P1, Prusa MK4) | Scale to 50% → 10 inch globe, or print the 12 inch generator output at 84% |
| Resin | Only on a very large SLA/LCD vat. FDM is the intended path |

To regenerate a smaller globe from the same terrain:

```bash
python scripts/make_etopo_relief_globe_stl.py \
  --diameter-inches 12 \
  --lon-segments 2160 \
  --mountain-relief-mm 8.2 \
  --trench-relief-mm 6.6
```

A 12-inch globe is 305 mm and fits a 350 mm bed with room for brim.

## Prepare the mesh

Do this once per hemisphere before slicing.

1. Import the STL as **millimeters**.
2. Cap the equator if your slicer refuses an open surface.
   Blender: select the rim, *Grid Fill* or *Fill*, then *Solidify*.
   MeshLab: *Close Holes*, then *Uniform Mesh Resampling* if needed.
3. Give the shell a real wall. Target **2.4–3.2 mm** (6–8 lines at
   0.4 mm). In the slicer this is usually *Hollow* + *Wall thickness*,
   or *Surface mode* with extra perimeters.
4. Add **two drain / sand holes** on the equatorial rim, 8–12 mm,
   opposite each other. They disappear into the glue joint.
5. Optional: model a 3–4 mm alignment ring or 3× 6 mm pegs on the
   equator so the two halves register when you glue them.

Do not print these as 15% gyroid solids. You will waste a week and a
spool farm.

## Suggested FDM profile (PLA or PETG)

Tested starting point for a 0.4 mm or 0.6 mm nozzle on a large-format
printer. Change only what your machine needs.

| Setting | Start here | Why |
|---|---|---|
| Scale | 100% | Bounding box is already 20 inches |
| Orientation | Equator on the bed, pole up | Self-supporting dome |
| Nozzle | 0.4 mm (0.6 mm if you want faster) | 0.55 mm vertex spacing |
| Layer height | 0.20 mm (0.16 mm for sharper ranges) | Terrain is 10+ mm; 0.08 mm is wasted time |
| Line width | 0.42–0.45 mm | Helps the 0.7 mm grid ribs |
| Walls | 4–5 | Shell strength after hollowing |
| Infill | 0% after hollow | The globe is a lamp-shade, not a shot put |
| Top / bottom | 5 / 5 | Equatorial rim and polar cap |
| Supports | None at 100% equator-down | Overhangs stay under ~45° until the last 20 mm of the pole |
| Brim | 8–12 mm | 500 mm circular first layer wants help |
| Bed | 60 °C PLA / 80 °C PETG | Big first layer |
| Hotend | 210 °C PLA / 245 °C PETG | PETG if the globe will live outdoors or in a sunny room |
| Cooling | 80–100% after layer 3 | Stops the polar cap from drooling |
| Speed | 40–80 mm/s outer wall | Large parts warp if you race the first 10 mm |

A 0.6 mm nozzle at 0.28 mm layers will still read every major range and
trench. Use 0.4 mm if you care about the 15° grid.

### Time and plastic (order of magnitude)

Hollow 3 mm PETG shell, 0.2 mm layers, 0.4 mm nozzle:

- ~1.4–1.8 kg per hemisphere
- ~2–4 days per half on a large-format machine, depending on speed
- Two halves + glue + primer ≈ 3–4 kg finished

Resin at this diameter is usually more expensive than FDM and needs a
vat most people do not own.

## Assembly

1. Dry-fit the equatorial rims. Sand high spots on the cut until the
   gap is even.
2. Degrease. PLA/PETG: isopropyl alcohol.
3. Glue with 2-part epoxy (slow, gap-filling) or CA + activator if the
   fit is already tight. Epoxy is more forgiving on a 1.6 m circumference.
4. Tape or strap the equator for a few hours. A ratchet strap around
   the 30° meridians works.
5. Fill the seam with more epoxy or filler primer. Sand to 320, then
   600.

Optional stand: a 80–100 mm ring or a three-point cradle printed
separately. Do not try to print a stand onto the South Pole — you will
ruin Antarctica.

## Paint (optional)

The mesh already has land, trenches, and a lat/long grid, so even raw
filament reads as a globe.

A simple scheme that matches the preview images:

- Prime the whole shell
- Oceans: muted teal or sap green
- Land: warm ochre / sand
- Ice sheets: off-white drybrush
- Grid: leave the raised ribs unpainted, or hit them with a dark wash

Masking the 15°/30° ribs is easier than painting them on later.

## Slicer warnings you can ignore — and ones you cannot

| Message | Action |
|---|---|
| "Open edges" / "not watertight" | Expected until you cap or thicken. Fix before printing. |
| "Non-manifold" after a sloppy cap | Recalculate normals, merge vertices by 0.05 mm. |
| "Part exceeds build volume" | You are not at 100% on a 500 mm bed, or the slicer assumed inches. |
| Import looks 25× too small | Slicer treated mm as inches, or vice versa. Re-import as mm. |
| Import looks 25× too big | Same problem the other way. |

## Verify the download

```bash
shasum -a 256 -c stl/SHA256SUMS
```

```
eda9fbda7aa0ea657eb777b782c9aa8c9561041d147cd055b5e5dad057f95a3d  globe_grid_20in_NORTH_hemisphere_mm.stl
efe4e4aa8868f5f0466705ae2205e69afff93ecf9379ce6699430d493287d2a9  globe_grid_20in_SOUTH_hemisphere_mm.stl
```
