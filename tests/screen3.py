import sys
import time
import queue
import pygame
import os
from dotenv import load_dotenv

# --- CUSTOM MODULES ---
# Assuming these exist in your project folder
import gears2 as gears
import screen_effects as fx
import MBVectorArt2 as MBVectorArt
from screen_effects import GpuCRT

# Load environment variables
load_dotenv()

# ================= CONFIGURATION =================
class Config:
    # Try to find the font locally, fallback to system font if missing
    FONT_PATH = r"InfoPanel/VT323-Regular.ttf" 
    if not os.path.exists(FONT_PATH):
        # Fallback for dev environment or if path differs
        FONT_PATH = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"
    
    base_res = (2560, 1440)
    
    resolutions = {
        "QHD": (2560, 1440),
        "UHD": (3840, 2160),
        "1080P": (1920, 1080),
    }

class Colors:
    PRIMARY = (0, 255, 100)
    OFFLINE = (5, 5, 5)
    RED     = (255, 0, 0)
    BLACK   = (0, 0, 0)
    WHITE   = (255, 255, 255)

# ================= UTILS =================
def get_resolution_from_args():
    if len(sys.argv) < 2:
        return Config.resolutions["QHD"]
    arg = sys.argv[1].upper()
    return Config.resolutions.get(arg, Config.resolutions["QHD"])

# ================= MAIN INTERFACE CLASS =================
class MonkeyButlerInterface:
    def __init__(self, cmd_queue):
        self.cmd_queue = cmd_queue
        self.running = True
        
        # Init Pygame
        print("Starting Monkey Butler Interface...")
        pygame.init()
        
        # Display Setup
        info = pygame.display.Info()
        self.screen_w, self.screen_h = info.current_w, info.current_h
        self.base_w, self.base_h = get_resolution_from_args()
        
        print(f"Detected: {self.screen_w}x{self.screen_h}")
        print(f"Base Design: {self.base_w}x{self.base_h}")

        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.FULLSCREEN)
        pygame.display.set_caption("Monkey Butler Terminal")
        self.clock = pygame.time.Clock()

        # Scaling Factors
        self.scale_x = self.screen_w / self.base_w
        self.scale_y = self.screen_h / self.base_h
        self.avg_scale = (self.scale_x + self.scale_y) / 2

        # Graphics Setup
        self._init_graphics_buffers()
        self._init_fonts()
        
        # State Data
        self.circle_time = 0
        self.last_command = "butler, water the monstera"
        self.last_response = "of course, sir. i have activated the pump."
        
        # Status Flags
        self.status = {
            "discord": True,
            "server": True,
            "aux_1": False,
            "aux_2": False,
            "aux_3": False
        }

    def _init_fonts(self):
        """Pre-load fonts to avoid lag during render loop."""
        def load_font(size):
            try:
                return pygame.font.Font(Config.FONT_PATH, int(size * self.avg_scale))
            except FileNotFoundError:
                return pygame.font.SysFont("consolas", int(size * self.avg_scale))

        self.fonts = {
            "small": load_font(30),
            "medium": load_font(40),
            "large": load_font(50),
            "xlarge": load_font(56),
            "title": load_font(80),
        }

    def _init_graphics_buffers(self):
        """Initialize shaders, CRTs, and offscreen buffers."""
        self.crt = GpuCRT(
            window_size=(self.screen_w, self.screen_h),
            kx=0.18, ky=0.16, curv=0.3,
            scan=0.18, vign=0.45, gamma=2.0
        )
        
        # Off-screen render targets
        self.framebuffer = pygame.Surface((self.screen_w, self.screen_h)).convert()
        
        # Pre-build overlays
        self.scanlines = fx.build_scanlines(self.screen_w, self.screen_h, spacing=5, alpha=200)
        self.grille = fx.build_aperture_grille(self.screen_w, self.screen_h, pitch=3, alpha=18)
        self.vignette = fx.build_vignette(self.screen_w, self.screen_h, margin=24, edge_alpha=70, corner_radius=28)

    # ================= DRAWING HELPERS =================
    def draw_text_centered(self, text, bx, by, font_key="medium", color=Colors.PRIMARY):
        font = self.fonts.get(font_key, self.fonts["medium"])
        surface = font.render(str(text), True, color)
        draw_x = int(bx * self.scale_x - surface.get_width() / 2)
        draw_y = int(by * self.scale_y - surface.get_height() / 2)
        self.framebuffer.blit(surface, (draw_x, draw_y))

    def draw_wrapped_text(self, text, x_base, y_base, w_base, h_base, font_key="small"):
        """Draws text wrapped inside a defined rectangle."""
        font = self.fonts[font_key]
        x = int(x_base * self.scale_x)
        y = int(y_base * self.scale_y)
        width = int(w_base * self.scale_x)
        
        words = text.split(" ")
        lines = []
        current_line = ""

        for word in words:
            test_line = current_line + word + " "
            if font.size(test_line)[0] <= width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
        lines.append(current_line)

        line_height = font.get_linesize()
        for i, line in enumerate(lines):
            surface = font.render(line, True, Colors.PRIMARY)
            self.framebuffer.blit(surface, (x, y + (i * line_height)))

    def draw_open_rect(self, bx, by, color):
        """Draws the bracket-style open rectangle."""
        x = bx
        y = by
        width = 500
        height = 105
        thick = 3
        
        # Convert to screen space if these inputs are base-res relative? 
        # The original code treated them somewhat ambiguously, assuming pixel inputs.
        # Ideally, these should be scaled.
        
        pygame.draw.line(self.framebuffer, color, (x, y), (x + width, y), thick)
        pygame.draw.line(self.framebuffer, color, (x, y + height), (x + width, y + height), thick)
        pygame.draw.line(self.framebuffer, color, (x + width, y), (x + width, y + height), thick)

    def draw_gear_assembly(self, is_active, y_pos, rect_y):
        """Helper to draw a standardized gear/rect combo."""
        color = Colors.PRIMARY if is_active else Colors.OFFLINE
        degrees = (self.circle_time * 4) if is_active else 0
        
        self.draw_open_rect(1280, rect_y, color)
        
        # Call external library
        sx = int(1700 * self.scale_x)
        sy = int(y_pos * self.scale_y) # Original code mixed absolute and scaled. Standardizing here.
        gears.gear_place(self.framebuffer, degrees, color, sx, sy, self.scale_x, self.scale_y)

    def draw_rect_frame(self, bx, by, bw, bh, thick=1):
        """Draws a scaled rectangle frame."""
        rect = pygame.Rect(
            int((bx * self.scale_x) - (bw * self.scale_x) / 2),
            int((by * self.scale_y) - (bh * self.scale_y) / 2),
            int(bw * self.scale_x),
            int(bh * self.scale_y)
        )
        pygame.draw.rect(self.framebuffer, Colors.PRIMARY, rect, width=thick)

    # ================= UI SECTIONS =================
    def _draw_header_info(self):
        time_str = time.strftime("%A %#I:%M %p")
        date_str = time.strftime("%B %#d, %Y")
        
        self.draw_text_centered(time_str, self.base_w/2, self.base_h/2.3, "xlarge")
        self.draw_text_centered(date_str, self.base_w/2, self.base_h/2.1, "xlarge")
        self.draw_text_centered("Monkey Butler", self.base_w/2, self.base_h/14, "title")
        self.draw_text_centered("Information", self.base_w/4, self.base_h/14, "large")
        self.draw_text_centered("Systems Status", self.base_w/1.25, self.base_h/14, "large")
        self.draw_text_centered("Chopscorp. Ltd. c 1977", self.base_w-180, self.base_h-75, "small")

    def _draw_status_panel(self):
        # Draw frame
        self.draw_rect_frame(self.base_w/4.5, self.base_h/3.425, 850, 500, thick=3)
        
        # Draw items
        base_x = self.base_w / 4.5
        start_y = (self.base_h / 14) + 150
        gap = 50
        
        items = ["[Weather Forecast]", "[Crypto Price]", "[Fear Greed Index]", "[System Load]"]
        for i, item in enumerate(items):
            self.draw_text_centered(item, base_x, start_y + (i * gap), "medium")

    def _draw_chat_interface(self):
        # 1. Portrait Frame
        self.draw_rect_frame(self.base_w / 2, self.base_h / 3.75, 415, 425, thick=5)
        
        # 2. Command Box Frame
        self.draw_rect_frame(self.base_w/3.15, self.base_h/1.775, 1500, 150)
        
        # 3. Response Box Frame
        self.draw_rect_frame(self.base_w/3.15, self.base_h/1.28, 1500, 450)

        # 4. Text Content
        # We manually position these based on the box locations calculated above
        cmd_y = 550 # Approx y
        resp_y = 675 # Approx y
        
        # Label and Content
        self.draw_wrapped_text(f"LAST COMMAND: {self.last_command}", 65, cmd_y, 1125, 200, "small")
        self.draw_wrapped_text(f"LAST RESPONSE: {self.last_response}", 65, resp_y, 1125, 300, "small")

    def _draw_monkey(self):
        # Slight bobbing animation
        second = int(time.strftime("%S"))
        dy = 10 if second % 2 == 0 else 0
        
        mb_x = self.base_w / 3.2
        mb_y = self.base_h / 2 + dy
        
        MBVectorArt.draw_monkey_butler_head(
            self.framebuffer, mb_x, mb_y, self.scale_x, self.scale_y, Colors.PRIMARY
        )

    def _draw_all_gears(self):
        # (Status, Y-Coord for Gear, Y-Coord for Rect)
        gear_configs = [
            (self.status["server"], 250, 135),
            (self.status["discord"], 475, 305),
            (self.status["aux_1"], 700, 472),
            (self.status["aux_2"], 925, 640),
            (self.status["aux_3"], 1150, 810),
        ]
        
        for is_online, gy, ry in gear_configs:
            self.draw_gear_assembly(is_online, gy, ry)

    # ================= CORE LOOP =================
    def process_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False

    def update_data(self):
        """Poll the queue for new voice commands."""
        while True:
            try:
                msg = self.cmd_queue.get_nowait()
                if msg[0] == "VOICE_CMD":
                    self.last_command = msg[1]
                    self.last_response = msg[2]
            except queue.Empty:
                break

    def render(self):
        # 1. Clear Framebuffer
        self.framebuffer.fill(Colors.BLACK) # or very dark green?
        
        # 2. Draw Components
        self._draw_header_info()
        self._draw_status_panel()
        self._draw_chat_interface()
        self._draw_monkey()
        self._draw_all_gears()
        
        # 3. Debug / Mouse Info (Optional)
        # mx, my = pygame.mouse.get_pos()
        # self.framebuffer.blit(self.fonts["small"].render(f"({mx}, {my})", True, Colors.WHITE), (10, 10))

        # 4. Post-Processing (Bloom, CRT, Scanlines)
        post_surface = self.framebuffer.copy()
        fx.add_bloom(post_surface, strength=1, down=0.45)
        
        post_surface.blit(self.grille, (0, 0))
        post_surface.blit(self.vignette, (0, 0))
        post_surface.blit(self.scanlines, (0, 0))
        
        # Apply Vertical Jitter to the final blit
        jitter_y = fx.random_vertical_jitter_y(100)
        self.screen.blit(post_surface, (0, jitter_y))
        
        # Draw curved CRT overlay on top
        self.crt.draw_surface(post_surface)

        pygame.display.flip()
        self.circle_time += 1
        self.clock.tick(60)

    def run(self):
        while self.running:
            self.process_events()
            self.update_data()
            self.render()
            
        pygame.quit()
        sys.exit()

# ================= ENTRY POINT =================
def run_info_panel_gui(cmd_queue):
    app = MonkeyButlerInterface(cmd_queue)
    app.run()