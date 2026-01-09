
import sys
import time
import queue
import pygame
from   dotenv import load_dotenv; load_dotenv()

import tasks
#import gears2 as gears
import screen_effects as fx
import butler_vector_art as MBVectorArt
from   screen_effects import GpuCRT
import obj_wireframe_loader as objl
import moving_vector_portrait as vec3d

import windows

font_path = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"

# =============== PYGAME INFO PANEL ===============
color         = (0, 255, 100)
color_offline = (5, 5, 5)
red           = (255, 0, 0)



RESOLUTIONS = {
    "QHD"   : (2560, 1440),
    "UHD"   : (3840, 2160),
    "1080P" : (1920, 1080),
}

scale = 0.75
FORCED_WINDOW_SIZE = RESOLUTIONS["1080P"]

def parse_base_resolution():
    if len(sys.argv) < 2:
        return RESOLUTIONS["QHD"]
    arg = sys.argv[1].upper()
    if arg in RESOLUTIONS:
        return RESOLUTIONS[arg]
    else:
        print(f"Unknown resolution '{arg}'. Falling back to QHD.")
        return RESOLUTIONS["QHD"]


def draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_):
    MBVectorArt.draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_)

def static_drawings(screen, base_w, base_h, scale_x, scale_y, circle_time, scale):
    # Example time & date
    time_readable = time.strftime("%A %#I:%M %p")
    date_readable = time.strftime("%B %#d, %Y")
    #weekday       = time.strftime("%A")

    is_auxpanel_online     = False
    is_mqtt_online         = True
    is_waterer_online      = True
    is_placeholder2_online = False
    is_placeholder3_online = False

    def draw_text_centered(text, bx, by, color_, size=30):
        font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
        surface     = font_scaled.render(str(text), True, color_)
        text_width  = surface.get_width()
        text_height = surface.get_height()
        draw_x      = int(bx*scale_x - text_width/2)
        draw_y      = int(by*scale_y - text_height/2)
        screen.blit(surface, (draw_x, draw_y))

    # Portrait Rectangle 
    rect_base_x = base_w / 2
    rect_base_y = base_h / 3.75
    rect_base_w = 415
    rect_base_h = 425

    scaled_rect_x = int(rect_base_x*scale_x - (rect_base_w*scale_x)/2)
    scaled_rect_y = int(rect_base_y*scale_y - (rect_base_h*scale_y)/2)
    scaled_rect_w = int(rect_base_w*scale_x)
    scaled_rect_h = int(rect_base_h*scale_y)

    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(scaled_rect_x, scaled_rect_y, scaled_rect_w, scaled_rect_h),
        width=5
    )

    # Text
    draw_text_centered(time_readable,   base_w/2, base_h/2.3, color, 56)
    draw_text_centered(date_readable,   base_w/2, base_h/2.1, color, 56)
    draw_text_centered("Monkey Butler", base_w/2, base_h/14,  color, 80)
    draw_text_centered("Information", base_w/4, base_h/14,  color, 50)
    draw_text_centered("Systems Status", base_w/1.25, base_h/14,  color, 50)
    draw_text_centered("Chopscorp. Ltd. c 1977", base_w-180, base_h-75,  color, 30)


def run_info_panel_gui(cmd_queue, scale): #The main Pygame loop. Polls 'cmd_queue' for new commands to display.
    print("Starting Pygame GUI for Info Panel...")

    pygame.init()
    info = pygame.display.Info()

    display_w, display_h = info.current_w, info.current_h
    screen_width, screen_height = FORCED_WINDOW_SIZE

    #w = screen_width
    #h = screen_height

    print("Detected screen resolution:", display_w, display_h)
    print("Forcing window size:", screen_width, screen_height)
    if display_w < screen_width or display_h < screen_height:
        print("Warning: forced window is larger than the current display.")

    base_w, base_h = parse_base_resolution()
    print(f"Using base design resolution: {base_w}x{base_h}")

    screen = pygame.display.set_mode((screen_width, screen_height))#, pygame.FULLSCREEN)
    pygame.display.set_caption("Scalable Pygame Port")

    mob_angle = 0

    crt = GpuCRT(window_size=(screen_width, screen_height),
           kx=0.18, ky=0.16, curv=0.3,
           scan=0.18, vign=0.45, gamma=2.0)

    scale_x = screen_width / base_w
    scale_y = screen_height / base_h

    clock = pygame.time.Clock()
    running = True
    circle_time = 0
    angle = 0

    # We'll keep track of the "last voice command" and "last GPT response"
    # so we can display them in the GUI.
    last_command  = "\"butler, water the monstera\""
    last_response = "of course, sir. i have activated the pump for the pot with the monstera."


    #========================================================================================
    # Off-screen render target
    framebuffer = pygame.Surface((screen_width, screen_height)).convert()
    framebuffer_alpha = pygame.Surface((screen_width, screen_height), pygame.SRCALPHA).convert_alpha()

    # Cached overlays (rebuild these if resolution changes)
    scanlines_surf = fx.build_scanlines(screen_width, screen_height, spacing=5, alpha=200)
    grille_surf    = fx.build_aperture_grille(screen_width, screen_height, pitch=3, alpha=18)
    vignette_surf  = fx.build_vignette(screen_width, screen_height, margin=24, edge_alpha=70, corner_radius=28)

    # Persistence buffer (previous post-processed frame)
    #last_frame = None
    #========================================================================================

    #Code for 3d wireframe panel
    panel_rect = (screen_width - 900 , 300, 340, 260) # x, y, w, h
    renderer = vec3d.WireframeRenderer(panel_rect, fov=55, near=0.1, far=50) 
    mesh = vec3d.cube_mesh(size=0.7) # Create a cube mesh
    angle = 180.0 # Rotation angle for animation

    dynamo_configs = [
        dict(x=1700, y=250, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "MQTT Broker", subtext="[status]", status=1),
        dict(x=1700, y=475, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Display Panels", subtext="[status]", status=1),
        dict(x=1700, y=700, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Auto Waterer", subtext="[status]", status=1),
        dict(x=1700, y=925,  base_deg=45,  surface=framebuffer, scale=scale, color=color, supertext= "Undefined Subystem", subtext="", status=0),
        dict(x=1700, y=1150, base_deg=45, surface=framebuffer, scale=scale, color=color, supertext= "Undefined Subystem", subtext="", status=0)
    ]

    dynamos = [
        windows.Dynamo(
            windows.WidgetConfig(
                surface=framebuffer,
                x=cfg["x"],
                y=cfg["y"],
                obj_width=0,
                obj_height=0,
                scale=scale,
                color=(255, 0, 0),
                text="test text",
                line_width=5,
                font_size=(60)
            ),
            cfg["supertext"],
            cfg["subtext"],
            cfg["status"],
            cfg["base_deg"],
        )
        for cfg in dynamo_configs
    ]

    widget_configs = [
        #Basic Information Box
        dict(x=145, y=170, obj_width=850, obj_height=500, surface=framebuffer, scale=scale, color=color,
             text="Crypto: 600 ", 
             fontsize = 45),
        
        #Voice Input Box
        dict(x=60, y=735, obj_width=1500, obj_height=150, surface=framebuffer, scale=scale, color=color,
             id="voice_cmd", 
             text="\"Butler, water the Monstera...\"", 
             fontsize = 60),

        #Voice Response Box
        dict(x=60, y=900, obj_width=1500, obj_height=450, surface=framebuffer, scale=scale, color=color, 
             id="voice_resp",
             text="Of course sir, the Monstera has been watered.", 
             fontsize = 60),
    ]

    widgets = [
        windows.Widget(
            windows.WidgetConfig(
                surface=framebuffer,
                x=cfg["x"],
                y=cfg["y"],
                obj_width=cfg["obj_width"],
                obj_height=cfg["obj_height"],
                scale=scale,
                color=cfg["color"],
                text=cfg["text"],
                line_width=5,
                font_size=cfg["fontsize"]
            )
        )
        for cfg in widget_configs
    ]


    #character = objl.load_obj_wire( "InfoPanel/butlerv3.obj", keep_edges="feature", # try "boundary" or "all" 
    #                                   feature_angle_deg=50.00, # larger -> fewer, sharper edges kept
    #                                     target_radius=0.8 )

    while running: # [][]][][][][][][][][][][][][][][][][]MAIN LOOP[][][][][][][][][][][][][][][][][]
        # --- EVENT HANDLING ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        # --- POLL THE QUEUE ---
        # Collect all commands currently in the queue
        while True:
            try:
                msg = cmd_queue.get_nowait()
            except queue.Empty:
                break
            else:
                if msg[0] == "VOICE_CMD":
                    # msg structure: ("VOICE_CMD", recognized_command, gpt_response_text)
                    last_command  = msg[1]
                    last_response = msg[2]

        # --- RENDER THE FRAME --- 
        framebuffer.fill((0, 1, 0)) 
        static_drawings(framebuffer, base_w, base_h, scale_x, scale_y, circle_time, scale)
        second = int(time.strftime("%S"))
        dy = 10 if second % 2 == 0 else 0
        mb_base_x = base_w / 3.2
        mb_base_y = base_h / 2 + dy

        debug = False
        if debug:
            draw_monkey_butler_head(framebuffer, mb_base_x+200, mb_base_y+150, scale_x, scale_y, color)
        else:
            draw_monkey_butler_head(framebuffer, mb_base_x, mb_base_y, scale_x, scale_y, color)

        #draw_text_topleft(f"Last command:  {last_command}",  75, 740, color, 36, target=framebuffer)
        #draw_text_topleft(f"Last response: {last_response}", 75, 900, color, 36, target=framebuffer)

        # Draw Widgets
        angle = (angle + 4) % 360
        for d, cfg in zip(dynamos, dynamo_configs):
            d.degrees = angle + cfg["base_deg"]
            d.draw_dynamo()

        for w, cfg in zip(widgets, widget_configs):
                w.drawCenteredRect()
                if cfg.get("id") == "voice_cmd":
                    w.createTextArea(last_command)
                elif cfg.get("id") == "voice_resp":
                    w.createTextArea(last_response)
                else:
                    w.createTextArea()


        #renderer.draw(
        #    framebuffer,
        #    character,
        #    model_pos     = (0.0, -0.1, 3.2),
        #    model_rot     = (0, mob_angle*0.9, 0),
        #    model_scale   = 3.5,
        #    camera_pos    = (0, 0, 0),
        #    camera_target = (0, 0, 1),
        #    zsort         = True
        #)
        # def draw_mouse_coordinates(surface):
        #     x, y = pygame.mouse.get_pos()
        #     text = font_scaled.render(f"({x}, {y})", True, (255, 255, 255))
        #     surface.blit(text, (10, 10))  # Display in top-left corner
        # draw_mouse_coordinates(framebuffer)

        # === POST FX on a copy (so we can reuse framebuffer if needed) ===
        post = framebuffer.copy()
        #last_frame = post
        fx.add_bloom(post, strength=1, down=0.45)
        #post = fx.apply_persistence(last_frame, post, alpha=80)
        post.blit(grille_surf,   (0, 0))
        post.blit(vignette_surf, (0, 0))
        screen.blit(post, (0, fx.random_vertical_jitter_y(100)))
        post.blit(scanlines_surf,(0, 0))
        crt.draw_surface(post)
        #last_frame = post

        clock.tick(60)
        circle_time += 1
        mob_angle += 0.01

    pygame.quit()
    sys.exit()
