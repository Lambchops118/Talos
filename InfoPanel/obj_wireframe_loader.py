import os
import math
import numpy as np

# Reuse your existing class
class WireMesh:
    def __init__(self, vertices, edges):
        self.vertices = np.asarray(vertices, dtype=np.float32)
        self.edges = edges  # list of (i, j)

def _normalize_vertices(verts, target_radius=1.0):
    """Center at origin and scale to target_radius (sphere)."""
    v = np.asarray(verts, dtype=np.float32)
    center = v.mean(axis=0)
    v -= center
    max_r = np.linalg.norm(v, axis=1).max()
    scale = (target_radius / max_r) if max_r > 1e-8 else 1.0
    v *= scale
    return v

def _face_normals(v, faces):
    """Per-face normals for dihedral feature edge selection."""
    # faces: list of (i, j, k)
    p0 = v[[f[0] for f in faces]]
    p1 = v[[f[1] for f in faces]]
    p2 = v[[f[2] for f in faces]]
    n = np.cross(p1 - p0, p2 - p0)
    # normalize
    lens = np.linalg.norm(n, axis=1, keepdims=True)
    n = np.divide(n, np.clip(lens, 1e-8, None))
    return n

def _edge_key(a, b):
    """Undirected edge key (sorted) for hashing."""
    return (a, b) if a < b else (b, a)

def _extract_edges(faces, mode="all", verts=None, feature_angle_deg=45.0):
    """
    faces: list[(i,j,k)] (triangulated)
    mode: "all" | "boundary" | "feature"
    verts: (N,3) required for feature mode
    """
    if mode not in ("all", "boundary", "feature"):
        mode = "all"

    # Count edge usage and keep adjacency
    edge_counts = {}
    edge_adj_faces = {}
    for fi, (a, b, c) in enumerate(faces):
        for (u, v) in ((a,b), (b,c), (c,a)):
            k = _edge_key(u, v)
            edge_counts[k] = edge_counts.get(k, 0) + 1
            edge_adj_faces.setdefault(k, []).append(fi)

    if mode == "all":
        edges = list(edge_counts.keys())

    elif mode == "boundary":
        # Boundary edges are used by only one face
        edges = [e for e, cnt in edge_counts.items() if cnt == 1]

    else:  # "feature"
        assert verts is not None, "verts required for feature edge mode"
        normals = _face_normals(verts, faces)
        cos_thresh = math.cos(math.radians(feature_angle_deg))
        edges = []
        for e, face_ids in edge_adj_faces.items():
            if len(face_ids) == 1:
                # Always include boundaries; they’re visually important
                edges.append(e)
                continue
            if len(face_ids) >= 2:
                n0 = normals[face_ids[0]]
                n1 = normals[face_ids[1]]
                # angle between normals
                cosang = float(np.clip(np.dot(n0, n1), -1.0, 1.0))
                # sharp if angle >= threshold
                if cosang <= cos_thresh:
                    edges.append(e)

    # Convert to list of pairs
    return [(i, j) for (i, j) in edges]

def load_obj_wire(
    path,
    *,
    keep_edges="feature",          # "all" | "boundary" | "feature"
    feature_angle_deg=45.0,        # used when keep_edges == "feature"
    target_radius=1.0,             # normalize size
    cache_npz=True                  # save/load .npz next to OBJ
):
    """
    Minimal OBJ loader for wireframe:
    - reads v / f (triangles or n-gons; n-gons will be fan-triangulated)
    - builds edge list according to selection mode
    - normalizes to target radius
    Returns: WireMesh
    """
    base, ext = os.path.splitext(path)
    npz_path = f"{base}_wirecache.npz"

    if cache_npz and os.path.exists(npz_path):
        data = np.load(npz_path, allow_pickle=True)
        verts = data["verts"]
        edges = [tuple(e) for e in data["edges"]]
        return WireMesh(verts, edges)

    verts = []
    faces = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == "v" and len(parts) >= 4:
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == "f" and len(parts) >= 4:
                # face entries may be like "i", "i/j", "i//k", "i/j/k"
                idx = []
                for tok in parts[1:]:
                    i = tok.split("/")[0]
                    if not i:
                        continue
                    # OBJ indices are 1-based; negative allowed
                    vi = int(i)
                    if vi < 0:
                        vi = len(verts) + vi + 1
                    idx.append(vi - 1)  # zero-based
                # triangulate fan if needed
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k+1]))

    if not verts or not faces:
        raise ValueError(f"OBJ had no verts/faces: {path}")

    verts = np.asarray(verts, dtype=np.float32)
    verts = _normalize_vertices(verts, target_radius=target_radius)

    edges = _extract_edges(faces, mode=keep_edges, verts=verts, feature_angle_deg=feature_angle_deg)

    mesh = WireMesh(verts, edges)

    if cache_npz:
        np.savez_compressed(npz_path, verts=mesh.vertices, edges=np.asarray(mesh.edges, dtype=np.int32))

    return mesh



#CODE TO USE IT IN PANEL:
#########################

#Once, when loading assets:
# character = load_obj_wire(
#     "assets/robot_lowpoly.obj",
#     keep_edges="feature",       # try "boundary" or "all"
#     feature_angle_deg=50.0,     # larger -> fewer, sharper edges kept
#     target_radius=0.8
# )

# # Each frame inside your UI draw:
# renderer.draw(
#     screen,
#     character,
#     model_pos=(0.0, -0.1, 3.2),
#     model_rot=(0, t*0.9, 0),   # animate however you like
#     model_scale=1.0,
#     camera_pos=(0, 0, 0),
#     camera_target=(0, 0, 1),
#     zsort=True
# )