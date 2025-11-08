import pygame, numpy as np, math, random

# === CONFIG ===
WIDTH, HEIGHT = 800, 600
FPS = 60
PHOSPHOR = (120, 255, 110)   # old P1-like green
DECAY = 0.90                  # phosphor persistence
SCAN_MIN_MUL = 0.55
VIGNETTE_STRENGTH = 0.45
GRAIN_AMT = 18
BLOOM_FACTOR = 0.4
BLOOM_PASSES = 2

# === INIT ===
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

scene = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
persist = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

# === HELPERS ===
def decay_surface(surf, decay):
    """Fade the phosphor layer slightly each frame."""
    arr = pygame.surfarray.pixels3d(surf)
    alpha = pygame.surfarray.pixels_alpha(surf)
    arr[:] = (arr * decay).astype(np.uint8)
    alpha[:] = (alpha * decay).astype(np.uint8)
    del arr, alpha

def bloom_pass(src, factor=0.5, passes=2):
    """Soft blur and return glow surface."""
    w, h = src.get_size()
    glow = src.copy()
    for _ in range(passes):
        down = pygame.transform.smoothscale(glow, (max(1,int(w*factor)), max(1,int(h*factor))))
        glow = pygame.transform.smoothscale(down, (w,h))
    arr = pygame.surfarray.pixels3d(glow)
    a = pygame.surfarray.pixels_alpha(glow)
    keep = (arr[:,:,1] > 20)
    arr[:,:,0] = arr[:,:,0] * keep
    arr[:,:,2] = arr[:,:,2] * keep
    a[:] = (a * keep).astype(np.uint8)
    del arr, a
    return glow

def make_scanline_mask(w, h, period=2, min_mul=0.5):
    mask = pygame.Surface((w,h), pygame.SRCALPHA)
    for y in range(h):
        t = (y % period) / (period-1 if period>1 else 1)
        mul = min_mul + (1-min_mul)*(1 - abs(t-0.5)*2)**1.5
        g = int(255*mul)
        mask.fill((g,g,g,255), (0,y,w,1))
    return mask

def vignette(w, h, strength=0.35):
    vg = pygame.Surface((w,h), pygame.SRCALPHA)
    arr = pygame.surfarray.pixels3d(vg)   # (w, h, 3)
    a   = pygame.surfarray.pixels_alpha(vg)

    xs = np.linspace(0, w-1, w)[:, None]  # (w,1)
    ys = np.linspace(0, h-1, h)[None, :]  # (1,h)
    cx, cy = (w-1)/2, (h-1)/2
    r = np.sqrt((xs - cx)**2 + (ys - cy)**2) / (0.5 * min(w, h))  # (w,h)
    fade = np.clip(1 - strength * (r**1.8), 0, 1)
    levels = (fade * 255).astype(np.uint8)

    arr[:, :, 0] = levels
    arr[:, :, 1] = levels
    arr[:, :, 2] = levels
    a[:] = 255

    del arr, a
    return vg

def make_grain(w,h, amt=20):
    g = pygame.Surface((w,h), pygame.SRCALPHA)
    arr = pygame.surfarray.pixels3d(g)
    noise = np.random.randint(255-amt, 255, size=(w,h), dtype=np.uint8).T
    arr[:,:,0] = noise; arr[:,:,1] = noise; arr[:,:,2] = noise
    del arr
    return g

scan_mask = make_scanline_mask(WIDTH, HEIGHT, period=2, min_mul=SCAN_MIN_MUL)
vign = vignette(WIDTH, HEIGHT, strength=VIGNETTE_STRENGTH)
grain = make_grain(WIDTH, HEIGHT, amt=GRAIN_AMT)

# === DEMO VECTOR SCENE ===
def draw_demo(scene, t):
    """Draw animated green vector lines."""
    cx, cy = WIDTH//2, HEIGHT//2
    radius = 200
    n = 12
    for i in range(n):
        a1 = i * (2*math.pi/n) + t*0.3
        a2 = a1 + math.sin(t*0.5+i)*0.5
        x1, y1 = cx + math.cos(a1)*radius, cy + math.sin(a1)*radius
        x2, y2 = cx + math.cos(a2)*radius*0.8, cy + math.sin(a2)*radius*0.8
        pygame.draw.line(scene, PHOSPHOR, (x1,y1), (x2,y2), 2)
        pygame.draw.circle(scene, PHOSPHOR, (int(x1), int(y1)), 2)
        pygame.draw.circle(scene, PHOSPHOR, (int(x2), int(y2)), 2)

# === MAIN LOOP ===
running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    t = pygame.time.get_ticks() / 1000.0
    scene.fill((0,0,0,0))
    draw_demo(scene, t)

    # decay old phosphor and add new lines
    decay_surface(persist, DECAY)
    persist.blit(scene, (0,0), special_flags=pygame.BLEND_ADD)

    # glow pass
    glow = bloom_pass(persist, factor=BLOOM_FACTOR, passes=BLOOM_PASSES)

    # compose
    screen.fill((0,0,0))
    screen.blit(persist, (0,0))
    screen.blit(glow, (0,0), special_flags=pygame.BLEND_ADD)

    # scanlines
    screen.blit(scan_mask, (0,0), special_flags=pygame.BLEND_MULT)
    # vignette
    screen.blit(vign, (0,0), special_flags=pygame.BLEND_MULT)

    # flicker
    flicker = 0.04 * math.sin(2*math.pi*60*t)
    g = int(255*(1.0 + flicker))
    fmask = pygame.Surface((WIDTH,HEIGHT), pygame.SRCALPHA)
    fmask.fill((g,g,g,255))
    screen.blit(fmask, (0,0), special_flags=pygame.BLEND_MULT)

    # grain jitter
    if int(t*30) % 2 == 0:
        screen.blit(grain, (1,0), special_flags=pygame.BLEND_MULT)
    else:
        screen.blit(grain, (-1,0), special_flags=pygame.BLEND_MULT)

    # slight horizontal jitter
    jx = ((pygame.time.get_ticks()//120) % 3) - 1
    if jx:
        jittered = screen.copy()
        screen.fill((0,0,0))
        screen.blit(jittered, (jx,0))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()