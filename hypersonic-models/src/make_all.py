"""Build all models, then render previews for the manual (../previews)."""

import glob
import os

import numpy as np
import trimesh

import build_models as bm
from render import render, tess

PREV = os.path.join(bm.OUT, "previews")
os.makedirs(PREV, exist_ok=True)

BODY = (0.62, 0.64, 0.70)
LOWER = (0.45, 0.48, 0.56)
SURF = (0.85, 0.45, 0.25)

VIEWS = {  # vehicle: (slug, (elev, azim), explode distance mm)
    "X-43A": ("x43a", (24, -60), 14),
    "X-51A": ("x51a", (22, -60), 12),
    "HTV-2": ("htv2", (24, -60), 0),
    "X-15": ("x15", (24, -58), 16),
    "Caret waverider": ("caret", (18, -55), 0),
}


def colour(name):
    if "lower" in name and "body" in name:
        return LOWER
    if "body" in name or "caret" in name:
        return BODY
    return SURF


def explode_vec(shape_wp, name, d):
    if "upper" in name and "body" in name:
        return np.array([0, 0, d])
    if "lower" in name and "body" in name:
        return np.array([0, 0, -d])
    c = shape_wp.val().Center()
    v = np.array([0, c.y, c.z])
    n = np.linalg.norm(v)
    return v / n * d * 1.4 if n > 1e-6 else np.zeros(3)


def main():
    for fn in (bm.build_x43a, bm.build_x51a, bm.build_htv2, bm.build_x15,
               bm.build_caret):
        print(fn.__name__)
        fn()

    for veh, parts in bm.ASSEMBLIES.items():
        slug, (el, az), d = VIEWS[veh]
        assembled, exploded = [], []
        for name, wp in parts:
            v, f = tess(wp.val())
            assembled.append((v, f, colour(name)))
            exploded.append((v + explode_vec(wp, name, d), f, colour(name)))
        render(assembled, os.path.join(PREV, f"{slug}_assembled.png"), el, az)
        if d:
            render(exploded, os.path.join(PREV, f"{slug}_exploded.png"), el, az)

    # print-orientation previews straight from the exported STL files
    for stl in sorted(glob.glob(os.path.join(bm.STL_DIR, "*.stl"))):
        name = os.path.splitext(os.path.basename(stl))[0]
        m = trimesh.load(stl)
        render([(np.asarray(m.vertices), np.asarray(m.faces), colour(name))],
               os.path.join(PREV, f"print_{name}.png"), 30, -60, size=(3.2, 2.4))
        print(f"  {name:28s} watertight={m.is_watertight}")


if __name__ == "__main__":
    main()
