# Hypersonic vehicle display models (3D printable, PLA+)

| Model | Scale | Length | Notes |
|---|---|---|---|
| X-43A Hyper-X | 1:24 | 153 mm | flow-through scramjet duct, all-moving wings |
| X-51A Waverider (cruiser) | 1:24 | 178 mm | open inlet/nozzle, X-fins |
| HTV-2 Falcon | 1:24 | 163 mm | generic shape (real OML not public) |
| X-15 | 1:72 | 215 mm | standard-length aircraft, optional ventral fin |
| Caret waverider | - | 160 mm | exact inviscid design, M=6, theta=7 deg |

- `Hypersonic_Models_Assembly_Manual.pdf`: print settings, parts lists, step-by-step assembly
- `stl/`: files for the slicer (already oriented for printing, no supports needed)
- `step/`: editable solids for Fusion / SolidWorks
- `src/`: CadQuery source. `pip install cadquery trimesh reportlab`, then
  `python make_all.py` (models + previews) and `python make_manual.py` (PDF)

Shapes other than the caret waverider are approximations from public dimensions and
photographs, intended for display and teaching.
