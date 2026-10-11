"""Shaded preview renders (matplotlib) of shapes / STL files for the manual."""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

LIGHT = np.array([0.4, -0.5, 0.8])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def tess(shape, tol=0.15):
    v, f = shape.tessellate(tol, 0.3)
    return np.array([[p.x, p.y, p.z] for p in v]), np.array(f)


def shade(tris, base):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    i = 0.35 + 0.65 * np.clip(np.abs(n @ LIGHT), 0, 1)
    return np.clip(np.outer(i, base), 0, 1)


def render(meshes, path, elev=22, azim=-58, size=(7, 4.2), title=None):
    """meshes: list of (verts, faces, rgb)."""
    fig = plt.figure(figsize=size, dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    allv = []
    for v, f, rgb in meshes:
        tris = v[f]
        pc = Poly3DCollection(tris, facecolors=shade(tris, np.array(rgb)),
                              edgecolor="none", linewidth=0)
        ax.add_collection3d(pc)
        allv.append(v)
    allv = np.vstack(allv)
    lo, hi = allv.min(0), allv.max(0)
    rng = np.maximum(hi - lo, 1e-3)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(tuple(rng), zoom=0.95)
    ax.set_proj_type("ortho")
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=11)
    plt.subplots_adjust(0, 0, 1, 1)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05,
                facecolor="white")
    plt.close(fig)
    trim(path)


def trim(path, pad=12):
    """Crop the white margins matplotlib leaves around 3-D plots."""
    from PIL import Image, ImageChops
    im = Image.open(path).convert("RGB")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    box = ImageChops.difference(im, bg).getbbox()
    if box:
        l, t, r, b = box
        im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad),
                 min(im.height, b + pad))).save(path)
