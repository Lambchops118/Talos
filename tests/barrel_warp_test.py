import pygame
import numpy as np

pygame.init()
W, H           = 2560, 1440 # window size
GAME_W, GAME_H = 2560, 1440 # internal render size (keeps warp fast)
screen         = pygame.display.set_mode((W, H))
clock          = pygame.time.Clock()



# --- precompute an inverse barrel-distortion map for the GAME_W x GAME_H grid
def precompute_map(w, h, kx=0.12, ky=0.12):
    """
    kx, ky > 0 bulge outward (CRT); smaller = flatter. ~0.08–0.18 looks good.
    We do inverse mapping: for each destination pixel (Xd,Yd), find source (Xs,Ys).
    """
    # normalized pixel centers in [-1, 1]
    xs = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    ys = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    Xd, Yd = np.meshgrid(xs, ys)         # shape (h, w)

    # elliptical radius so we can control x/y curvature separately
    r2 = -(Xd**2) + -(Yd**2)
    # inverse barrel: Xs = Xd / (1 + kx*r2), Ys = Yd / (1 + ky*r2)
    # (This approximates the true inverse; good for small k.)
    Xs = Xd / (1.0 + kx * r2* 0.25)  #the 0.25 controls how curvy the distortion is
    Ys = Yd / (1.0 + ky * r2* 0.25)  #same

    # map back to source pixel indices
    src_x = (Xs * 0.5 + 0.5) * (w - 1)
    src_y = (Ys * 0.5 + 0.5) * (h - 1)

    # integer indices for nearest-neighbor sampling
    ix = np.clip(np.rint(src_x), 0, w - 1).astype(np.int32)
    iy = np.clip(np.rint(src_y), 0, h - 1).astype(np.int32)
    return ix, iy, Xd, Yd



# --- precompute CRT “cosmetic” masks (scanlines + vignette) in GAME resolution
def make_crt_masks(w, h, strength_scan=0.18, strength_vignette=0.35): #0.18, 0.35
    # scanlines: darken every other row a bit
    scan = np.ones((h, w, 1), dtype=np.float32)
    scan[1::2, :, 0] = 1.0 - strength_scan

    # vignette: darken corners radially (smooth)
    xs   = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    ys   = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)           # (h, w)
    r    = np.sqrt(X*X + Y*Y)
    vign = 1.0 - strength_vignette * (r**2)  # gentle
    vign = np.clip(vign, 0.0, 1.0).reshape(h, w, 1)

    return scan, vign



# --- warp + cosmetic pass
def warp_crt(src_surf):
    """
    src_surf must be GAME_W x GAME_H.
    Returns a warped pygame.Surface at the same size (then we scale to window).
    """
    # Pygame’s array3d is (w, h, 3). We’ll transpose to (h, w, 3) for easy indexing.
    src = pygame.surfarray.array3d(src_surf).astype(np.uint8)          # (w, h, 3)
    src = np.transpose(src, (1, 0, 2))                                  # (h, w, 3)

    # nearest-neighbor sampling using the inverse map
    warped = src[IY, IX]                                                # (h, w, 3)

    # apply scanlines & vignette (broadcast multiply)
    warped_lin = warped.astype(np.float32) / 255.0
    warped_lin *= SCAN
    warped_lin *= VIGN

    # slight overall gamma to mimic phosphor response
    gamma = 2.0
    warped_lin = np.clip(warped_lin, 0.0, 1.0) ** (1.0 / gamma)

    # back to surface
    warped_u8 = (warped_lin * 255.0 + 0.5).astype(np.uint8)
    warped_u8 = np.transpose(warped_u8, (1, 0, 2))                      # (w, h, 3)
    return pygame.surfarray.make_surface(warped_u8)

# --- demo: draw something on a low-res "game" surface, then warp and scale to window


IX, IY, XNORM, YNORM = precompute_map(GAME_W, GAME_H, kx=0.12, ky=0.10)
SCAN, VIGN = make_crt_masks(GAME_W, GAME_H)
game_surf = pygame.Surface((GAME_W, GAME_H))

running = True
t = 0.0
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    # (Replace this with your actual game rendering)
    game_surf.fill((8, 12, 16))

    #moving grid to show curvature
    for x in range(0, GAME_W, 16):
        pygame.draw.line(game_surf, (40, 180, 220), (x, 0), (x, GAME_H-1))
    for y in range(0, GAME_H, 16):
        pygame.draw.line(game_surf, (40, 220, 120), (0, y), (GAME_W-1, y))
    # a bouncing rectangle
    cx = int((np.sin(pygame.time.get_ticks()*0.002) * 0.4 + 0.5) * (GAME_W-50))
    pygame.draw.rect(game_surf, (255, 200, 40), (cx, 90, 50, 30))

    # warp and scale up to the window
    warped = warp_crt(game_surf)
    scaled = pygame.transform.smoothscale(warped, (W, H))

    # optional: add a bezel/rounded mask by drawing a dark border
    screen.fill((5, 5, 8))
    screen.blit(scaled, (0, 0))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
