#This is the code that gets called from the main window to draw a 3d wireframe object within a panel in an already existing pygame window.
#written by chatgpt 10/5/25

import math
import numpy as np
import pygame

# ------------ Mesh definition helpers ------------
class WireMesh:
    """
    vertices: (N, 3) float32 array
    edges:    list of (i, j) index pairs
    """
    def __init__(self, vertices, edges):
        self.vertices = np.asarray(vertices, dtype=np.float32)
        self.edges = edges

def cube_mesh(size=1.0):
    s = size
    verts = np.array([
        [-s,-s,-s],[ s,-s,-s],[ s, s,-s],[-s, s,-s],
        [-s,-s, s],[ s,-s, s],[ s, s, s],[-s, s, s],
    ], dtype=np.float32)
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    return WireMesh(verts, edges)

# ------------ Math utilities ------------
def rotation_xyz(rx, ry, rz):
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = np.array([[1,0,0,0],[0,cx,-sx,0],[0,sx,cx,0],[0,0,0,1]], dtype=np.float32)
    Ry = np.array([[cy,0,sy,0],[0,1,0,0],[-sy,0,cy,0],[0,0,0,1]], dtype=np.float32)
    Rz = np.array([[cz,-sz,0,0],[sz,cz,0,0],[0,0,1,0],[0,0,0,1]], dtype=np.float32)
    return Rz @ Ry @ Rx  # Z * Y * X (change order to taste)

def translate(tx, ty, tz):
    T = np.eye(4, dtype=np.float32)
    T[:3,3] = [tx, ty, tz]
    return T

def perspective(fov_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    nf = 1.0 / (near - far)
    return np.array([
        [f/aspect, 0, 0,                     0],
        [0,        f, 0,                     0],
        [0,        0, (far+near)*nf, 2*far*near*nf],
        [0,        0, -1,                    0]
    ], dtype=np.float32)

def look_at(eye, target, up=(0,1,0)):
    eye = np.array(eye, dtype=np.float32)
    target = np.array(target, dtype=np.float32)
    up = np.array(up, dtype=np.float32)
    z = eye - target
    z /= np.linalg.norm(z)
    x = np.cross(up, z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    M = np.eye(4, dtype=np.float32)
    M[0,:3] = x; M[1,:3] = y; M[2,:3] = z
    T = np.eye(4, dtype=np.float32)
    T[:3,3] = -eye
    return M @ T

# ------------ Renderer ------------
class WireframeRenderer:
    """
    Draws a wireframe mesh into a given pygame Surface rect.
    """
    def __init__(self, panel_rect, fov=60, near=0.1, far=100.0):
        self.panel_rect = pygame.Rect(panel_rect)
        self.fov = fov
        self.near = near
        self.far = far
        self.bg = (0, 15, 0) #background color
        self.fg = (0, 255, 0)  #foreground (object) color
        self.line_width = 2

    def _viewport(self, w, h):
        # NDC [-1,1] -> pixel coords inside panel
        hw, hh = w * 0.5, h * 0.5
        return hw, hh

    def draw(self, surface, mesh: WireMesh, model_pos=(0,0,3.5),
             model_rot=(0,0,0), model_scale=1.0,
             camera_pos=(0,0,0), camera_target=(0,0,1),
             zsort=False):
        # Panel setup
        px, py, pw, ph = self.panel_rect
        panel = surface.subsurface(self.panel_rect) # get subsurface for panel
        panel.fill(self.bg)

        aspect = pw / ph
        P = perspective(self.fov, aspect, self.near, self.far)
        V = look_at(camera_pos, camera_target)
        S = np.diag([model_scale, model_scale, model_scale, 1]).astype(np.float32)
        R = rotation_xyz(*model_rot)
        T = translate(*model_pos)
        M = T @ R @ S
        MVP = P @ V @ M

        # Transform vertices to clip space
        N = mesh.vertices.shape[0]
        verts4 = np.ones((N, 4), dtype=np.float32)
        verts4[:,:3] = mesh.vertices
        clip = (MVP @ verts4.T).T   # (N,4)

        # Precompute NDC + screen coords where valid
        # Perspective divide
        w = clip[:,3:4]
        # Mark vertices behind the near plane in clip-space:
        # In standard clip space, valid if -w <= z <= w and -w<=x<=w, -w<=y<=w; but for segment clipping we just keep values.
        ndc = clip[:,:3] / np.clip(w, 1e-6, None)  # (N,3)

        # Screen mapping
        hw, hh = self._viewport(pw, ph)
        screen_xy = np.empty((N, 2), dtype=np.int32)
        screen_xy[:,0] = (ndc[:,0] * hw + hw).astype(np.int32)
        screen_xy[:,1] = ((-ndc[:,1]) * hh + hh).astype(np.int32)  # flip Y

        # Helper: near-plane in clip space is z = -w. Test endpoints; clip if needed.
        # We'll linearly interpolate in clip space and do perspective divide after.
        def clip_and_project(i, j):
            a = clip[i].copy()
            b = clip[j].copy()

            def inside(v):
                return v[2] >= -v[3] and v[2] <= v[3] and abs(v[0]) <= v[3] and abs(v[1]) <= v[3]

            # Liang–Barsky-ish clip against all 6 planes of clip cube
            # We’ll parametrize the segment as a(t) = a + t*(b-a), t in [0,1]
            t0, t1 = 0.0, 1.0
            d = b - a

            planes = [
                (+1, 0, 0, +1),  #  x <=  w :  x - w <= 0  -> (x - w) <= 0
                (-1, 0, 0, +1),  # -x <=  w : -x - w <= 0  -> (-x - w) <= 0
                (0, +1, 0, +1),  #  y <=  w
                (0, -1, 0, +1),  # -y <=  w
                (0, 0, +1, +1),  #  z <=  w
                (0, 0, -1, +1),  # -z <=  w  -> z >= -w
            ]
            # Each plane is p·v + q*w <= 0, applied to a + t*d
            for px_, py_, pz_, q in planes:
                def evalP(v):
                    return px_*v[0] + py_*v[1] + pz_*v[2] + q*(-v[3])
                Pa = evalP(a)
                Pb = evalP(b)
                if Pa <= 0 and Pb <= 0:
                    continue  # both inside w.r.t this plane
                if Pa > 0 and Pb > 0:
                    return None  # completely outside
                # compute intersection t
                denom = Pa - Pb
                if abs(denom) < 1e-8:
                    return None
                t = Pa / (Pa - Pb)
                if Pa > 0:   # a outside, move start
                    t0 = max(t0, t)
                else:        # b outside, move end
                    t1 = min(t1, t)
                if t0 > t1:
                    return None

            a2 = a + d * t0
            b2 = a + d * t1

            # perspective divide to NDC then map to panel pixels
            def to_screen(v):
                vw = max(1e-6, v[3])
                x = v[0] / vw; y = v[1] / vw
                sx = int(x * hw + hw)
                sy = int((-y) * hh + hh)
                return sx, sy

            return to_screen(a2), to_screen(b2)

        # Edge ordering for optional z-sort
        if zsort:
            # average view-space z for each edge (use V*M to get view-space)
            VM = V @ M
            view = (VM @ verts4.T).T  # (N,4)
            avgz = [(i, j, (view[i,2] + view[j,2]) * 0.5) for (i, j) in mesh.edges]
            edges_iter = [e[:2] for e in sorted(avgz, key=lambda t: t[2], reverse=True)]
        else:
            edges_iter = mesh.edges

        draw_line = pygame.draw.line
        col = self.fg
        lw = self.line_width

        # Draw edges with clipping
        for (i, j) in edges_iter:
            seg = clip_and_project(i, j)
            if seg is None:
                continue
            a2, b2 = seg
            draw_line(panel, col, a2, b2, lw)

        # Optional: draw panel border to fit UI
        #pygame.draw.rect(surface, (40, 40, 60), self.panel_rect, 1)
        pygame.draw.rect(surface, (0, 255, 0), self.panel_rect, 1) #green border