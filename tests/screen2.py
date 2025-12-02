import sys
import time
import queue
import pygame
from dotenv import load_dotenv; load_dotenv()

import gears2 as gears
import screen_effects as fx
import MBVectorArt2 as MBVectorArt
from screen_effects import GpuCRT
import obj_wireframe_loader as objl
import moving_vector_portrait as vec3d

# ================== CONFIG & CONSTANTS ==================

FONT_PATH = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"

COLOR_ONLINE      = (0, 255, 100)
COLOR_OFFLINE     = (5, 5, 5)
COLOR_RED         = (255, 0, 0)
COLOR_MOUSE       = (255, 255, 255)
BACKGROUND_COLOR  = (0, 1, 0)

RESOLUTIONS = {
    "QHD":   (2560, 1440),
    "UHD":   (3840, 2160),
    "1080P": (1920, 1080),
}

# Rect layout (in base coordinate space)
PORTRAIT_RECT = {
    "x": lambda w: w / 2,
    "y": lambda h: h / 3.75,
    "w": 415,
    "h": 425,
}

CHAT_RECT = {
    "x": lambda w: w / 3.15,
    "y": lambda h: h / 1.775,
    "w": 1500,
    "h": 150,
}

RESPONSE_RECT = {
    "x": lambda w: w / 3.15,
    "y": lambda h: h / 1.28,
    "w": 1500,
    "h": 450,
}

INFO_PANEL_RECT = {
    "x": lambda w: w / 4.5,
    "y": lambda h: h / 3.425,
    "w": 850,
    "h": 500,
}

STATUS_GEAR_ROWS = [
    # (online_flag_name, open_rect_y, gear_center_y, color_online, color_offline)
    ("server",       135,  250, COLOR_ONLINE,  COLOR_OFFLINE),
    ("discord",      305,  475, COLOR_ONLINE,  COLOR_OFFLINE),
    ("placeholder1", 472,  700, COLOR_OFFLINE, COLOR_OFFLINE),
    ("placeholder2", 640,  925, COLOR_ONLINE,  COLOR_OFFLINE),
    ("placeholder3", 810, 1150, COLOR_ONLINE,  COLOR_OFFLINE),
]


# ================== UTILITY FUNCTIONS ==================


def parse_base_resolution():
    """Parse resolution from command line or fall back to QHD."""
    if len(sys.argv) < 2:
        return RESOLUTIONS["QHD"]

    arg = sys.argv[1].upper()
    if arg in RESOLUTIONS:
        return RESOLUTIONS[arg]

    print(f"Unknown resolution '{arg}'. Falling back to QHD.")
    return RESOLUTIONS["QHD"]


def gear_place(screen, degrees, color_, center_x, center_y, scale_x, scale_y):
    """Wrapper around gears.gear_place with scaled coordinates."""
    scaled_x = int(center_x * scale_x)
    scaled_y = int(center_y * scale_y)
    gears.gear_place(screen, degrees, color_, scaled_x, scaled_y, scale_x, scale_y)


def draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_):
    MBVectorArt.draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_)


def draw_scanlines(screen, screen_width, screen_height):
    """Legacy manual scanline drawer (currently unused; fx.build_scanlines used)."""
    for y in range(0, screen_height, 2):
        pygame.draw.line(screen, (0, 0, 0), (0, y), (8000, y), 1)


def draw_open_rect(surface, color, x, y, width=500, height=105, line_thickness=3):
    """Draw three-sided 'open' rectangle."""
    pygame.draw.line(surface, color, (x, y), (x + width, y), line_thickness)
    pygame.draw.line(surface, color, (x, y + height), (x + width, y + height), line_thickness)
    pygame.draw.line(surface, color, (x + width, y), (x + width, y + height), line_thickness)


def create_scaled_font(base_size, scale_x, scale_y, font_path=FONT_PATH):
    """Create a font scaled based on the current resolution."""
    scale = (scale_x + scale_y) / 2
    return pygame.font.Font(font_path, int(base_size * scale))


def draw_text_centered(
    surface,
    text,
    base_x,
    base_y,
    color,
    size,
    scale_x,
    scale_y,
    font_path=FONT_PATH
):
    """Draw text centered at (base_x, base_y) in base coordinates."""
    font = create_scaled_font(size, scale_x, scale_y, font_path)
    text = str(text)
    text_surf = font.render(text, True, color)
    text_w = text_surf.get_width()
    text_h = text_surf.get_height()

    draw_x = int(base_x * scale_x - text_w / 2)
    draw_y = int(base_y * scale_y - text_h / 2)

    surface.blit(text_surf, (draw_x, draw_y))


def draw_text_topleft(
    surface,
    text,
    base_x,
    base_y,
    color=(255, 255, 255),
    size=30,
    scale_x=1.0,
    scale_y=1.0,
    font_path=FONT_PATH
):
    """Draw text with its top-left corner at (base_x, base_y) in base coordinates."""
    font = create_scaled_font(size, scale_x, scale_y, font_path)
    text = str(text)
    text_surf = font.render(text, True, color).convert_alpha()

    tx = int(base_x * scale_x)
    ty = int(base_y * scale_y)

    surface.blit(text_surf, (tx, ty))
    return text_surf


def render_textrect(
    text,
    x,
    y,
    width,
    height,
    size,
    color,
    target,
    font_path=FONT_PATH
):
    """
    Render word-wrapped text into a rectangular region on 'target'.

    x, y, width, height are in actual pixels (not scaled base coords),
    to preserve original behavior.
    """
    font = pygame.font.Font(font_path, size)

    words = text.split(" ")
    lines = []
    current = ""

    for word in words:
        test = current + word + " "
        if font.size(test)[0] <= width:
            current = test
        else:
            lines.append(current)
            current = word + " "
    lines.append(current)

    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    line_height = font.get_linesize()
    ty = 0

    for line in lines:
        if ty + line_height > height:
            break
        line_surf = font.render(line, True, color)
        surf.blit(line_surf, (0, ty))
        ty += line_height

    target.blit(surf, (x, y))
    return surf


def draw_mouse_coordinates(surface, font):
    """Draw current mouse coordinates at the top-left of 'surface'."""
    x, y = pygame.mouse.get_pos()
    text_surf = font.render(f"({x}, {y})", True, COLOR_MOUSE)
    surface.blit(text_surf, (10, 10))


def draw_rect_from_config(surface, rect_cfg, base_w, base_h, scale_x, scale_y, color, width):
    """Helper for drawing rectangles using base-coord configuration dicts."""
    base_x = rect_cfg["x"](base_w)
    base_y = rect_cfg["y"](base_h)
    base_w_rect = rect_cfg["w"]
    base_h_rect = rect_cfg["h"]

    scaled_x = int(base_x * scale_x - (base_w_rect * scale_x) / 2)
    scaled_y = int(base_y * scale_y - (base_h_rect * scale_y) / 2)
    scaled_w = int(base_w_rect * scale_x)
    scaled_h = int(base_h_rect * scale_y)

    pygame.draw.rect(
        surface,
        color,
        pygame.Rect(scaled_x, scaled_y, scaled_w, scaled_h),
        width=width
    )


def draw_status_gear_row(
    screen,
    online,
    open_rect_y,
    gear_center_y,
    circle_time,
    scale_x,
    scale_y,
    color_online=COLOR_ONLINE,
    color_offline=COLOR_OFFLINE,
    open_rect_x=1280,
    gear_center_x=1700
):
    """
    Draw a single gear + open-rect row based on 'online' status.
    Behavior is kept identical to original: rotation only if online,
    color switches as configured per row.
    """
    degrees = circle_time * 4 if online else 0
    rect_color = color_online if online else color_offline
    gear_color = color_online if online else color_offline

    draw_open_rect(screen, rect_color, open_rect_x, open_rect_y)
    gear_place(screen, degrees, gear_color, gear_center_x, gear_center_y, scale_x, scale_y)


# ================== STATIC DRAWINGS ==================


def static_drawings(screen, base_w, base_h, scale_x, scale_y, circle_time):
    # Example time & date
    time_readable = time.strftime("%A %#I:%M %p")
    date_readable = time.strftime("%B %#d, %Y")

    is_discord_online      = True
    is_server_online       = True
    is_placeholder1_online = False
    is_placeholder2_online = False
    is_placeholder3_online = False

    # --- Main panels & labels ---

    # Portrait Rectangle
    draw_rect_from_config(
        screen,
        PORTRAIT_RECT,
        base_w,
        base_h,
        scale_x,
        scale_y,
        COLOR_ONLINE,
        width=5
    )

    # Chat Box Rectangle
    draw_rect_from_config(
        screen,
        CHAT_RECT,
        base_w,
        base_h,
        scale_x,
        scale_y,
        COLOR_ONLINE,
        width=1
    )

    # Chat Response Rectangle
    draw_rect_from_config(
        screen,
        RESPONSE_RECT,
        base_w,
        base_h,
        scale_x,
        scale_y,
        COLOR_ONLINE,
        width=1
    )

    # Information Panel Rectangle
    draw_rect_from_config(
        screen,
        INFO_PANEL_RECT,
        base_w,
        base_h,
        scale_x,
        scale_y,
        COLOR_ONLINE,
        width=3
    )

    # Info panel headings
    draw_text_centered("[Weather Forecast]", base_w / 4.5, (base_h / 14) + 150, COLOR_ONLINE, 40, scale_x, scale_y)
    draw_text_centered("[Crypto Price]",     base_w / 4.5, (base_h / 14) + 200, COLOR_ONLINE, 40, scale_x, scale_y)
    draw_text_centered("[Fear Greed Index]", base_w / 4.5, (base_h / 14) + 250, COLOR_ONLINE, 40, scale_x, scale_y)
    draw_text_centered("[Something Else]",   base_w / 4.5, (base_h / 14) + 300, COLOR_ONLINE, 40, scale_x, scale_y)

    # Text labels
    draw_text_centered(time_readable,                base_w / 2,     base_h / 2.3, COLOR_ONLINE, 56, scale_x, scale_y)
    draw_text_centered(date_readable,                base_w / 2,     base_h / 2.1, COLOR_ONLINE, 56, scale_x, scale_y)
    draw_text_centered("Monkey Butler",              base_w / 2,     base_h / 14,  COLOR_ONLINE, 80, scale_x, scale_y)
    draw_text_centered("Information",                base_w / 4,     base_h / 14,  COLOR_ONLINE, 50, scale_x, scale_y)
    draw_text_centered("Systems Status",             base_w / 1.25,  base_h / 14,  COLOR_ONLINE, 50, scale_x, scale_y)
    draw_text_centered("Chopscorp. Ltd. c 1977",     base_w - 180,   base_h - 75,  COLOR_ONLINE, 30, scale_x, scale_y)

    # --- Gears / status rows ---

    row_state_map = {
        "server":       is_server_online,
        "discord":      is_discord_online,
        "placeholder1": is_placeholder1_online,
        "placeholder2": is_placeholder2_online,
        "placeholder3": is_placeholder3_online,
    }

    for name, open_rect_y, gear_center_y, color_online, color_offline in STATUS_GEAR_ROWS:
        online = row_state_map[name]

        # placeholder1 preserves original quirk: color_offline used in both cases
        if name == "placeholder1":
            draw_status_gear_row(
                screen,
                online,
                open_rect_y,
                gear_center_y,
                circle_time,
                scale_x,
                scale_y,
                color_online=color_offline,
                color_offline=color_offline,
            )
        else:
            draw_status_gear_row(
                screen,
                online,
                open_rect_y,
                gear_center_y,
                circle_time,
                scale_x,
                scale_y,
                color_online=color_online,
                color_offline=color_offline,
            )


# ================== MAIN LOOP ==================


def run_info_panel_gui(cmd_queue):
    """Main Pygame loop. Polls 'cmd_queue' for new commands to display."""
    print("Starting Pygame GUI for Info Panel...")

    pygame.init()
    info = pygame.display.Info()

    screen_width, screen_height = info.current_w, info.current_h
    print("Detected screen resolution:", screen_width, screen_height)

    base_w, base_h = parse_base_resolution()
    print(f"Using base design resolution: {base_w}x{base_h}")

    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    pygame.display.set_caption("Scalable Pygame Port")

    crt = GpuCRT(
        window_size=(screen_width, screen_height),
        kx=0.18, ky=0.16, curv=0.3,
        scan=0.18, vign=0.45, gamma=2.0
    )

    scale_x = screen_width / base_w
    scale_y = screen_height / base_h

    clock = pygame.time.Clock()
    running = True
    circle_time = 0

    last_command  = "butler, water the monstera"
    last_response = "of course, sir. i have activated the pump for the pot with the monstera."

    # Off-screen render targets
    framebuffer = pygame.Surface((screen_width, screen_height)).convert()
    framebuffer_alpha = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA).convert_alpha()

    # Cached overlays (rebuild these if resolution changes)
    scanlines_surf = fx.build_scanlines(screen_width, screen_height, spacing=5, alpha=200)
    grille_surf    = fx.build_aperture_grille(screen_width, screen_height, pitch=3, alpha=18)
    vignette_surf  = fx.build_vignette(screen_width, screen_height, margin=24, edge_alpha=70, corner_radius=28)

    # Precreate a small font for mouse coordinates
    mouse_font = create_scaled_font(30, scale_x, scale_y, FONT_PATH)

    # Main loop
    while running:
        # --- EVENT HANDLING ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # --- POLL THE QUEUE ---
        while True:
            try:
                msg = cmd_queue.get_nowait()
            except queue.Empty:
                break
            else:
                if msg[0] == "VOICE_CMD":
                    last_command  = msg[1]
                    last_response = msg[2]

        # --- RENDER THE FRAME ---
        framebuffer.fill(BACKGROUND_COLOR)

        # Static layout & labels
        static_drawings(framebuffer, base_w, base_h, scale_x, scale_y, circle_time)

        # Monkey Butler portrait (with subtle bob animation)
        second = int(time.strftime("%S"))
        dy = 10 if second % 2 == 0 else 0
        mb_base_x = base_w / 3.2
        mb_base_y = base_h / 2 + dy
        draw_monkey_butler_head(framebuffer, mb_base_x, mb_base_y, scale_x, scale_y, COLOR_ONLINE)

        # Response text boxes (word-wrapped)
        render_textrect(
            f"LAST COMMAND:  {last_command}",
            x=65,
            y=550,
            width=1125,
            height=200,
            size=30,
            color=COLOR_ONLINE,
            target=framebuffer
        )

        render_textrect(
            f"LAST RESPONSE:  {last_response}",
            x=65,
            y=675,
            width=1125,
            height=300,
            size=30,
            color=COLOR_ONLINE,
            target=framebuffer
        )

        # Mouse coordinates (debug)
        draw_mouse_coordinates(framebuffer, mouse_font)

        # --- POST FX ---
        post = framebuffer.copy()
        fx.add_bloom(post, strength=1, down=0.45)
        post.blit(grille_surf,   (0, 0))
        post.blit(vignette_surf, (0, 0))

        # CRT jitter & scanlines
        jitter_y = fx.random_vertical_jitter_y(100)
        screen.blit(post, (0, jitter_y))
        post.blit(scanlines_surf, (0, 0))
        crt.draw_surface(post)

        clock.tick(60)
        circle_time += 1

    pygame.quit()
    sys.exit()