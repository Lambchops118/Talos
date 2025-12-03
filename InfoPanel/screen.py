
import sys
import time
import queue
import pygame
from   dotenv import load_dotenv; load_dotenv()

import gears2 as gears
import screen_effects as fx
import MBVectorArt2 as MBVectorArt
from   screen_effects import GpuCRT
import obj_wireframe_loader as objl
import moving_vector_portrait as vec3d

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

def parse_base_resolution():
    if len(sys.argv) < 2:
        return RESOLUTIONS["QHD"]
    arg = sys.argv[1].upper()
    if arg in RESOLUTIONS:
        return RESOLUTIONS[arg]
    else:
        print(f"Unknown resolution '{arg}'. Falling back to QHD.")
        return RESOLUTIONS["QHD"]

#def gear_place(screen, degrees, color_, center_x, center_y, scale_x, scale_y):
#    scaled_x = int(center_x * scale_x)
#    scaled_y = int(center_y * scale_y)
#    gears.gear_place(screen, degrees, color_, scaled_x, scaled_y, scale_x, scale_y)

def draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_):
    MBVectorArt.draw_monkey_butler_head(screen, base_x, base_y, scale_x, scale_y, color_)

def draw_scanlines(screen, screen_width, screen_height):
    for y in range(0, screen_height, 2): # every 4 pixels
        pygame.draw.line(screen, (0, 0, 0), (0, y), (8000, y), 1) # black line, 2 pixels thick


def draw_open_rect(surface, color, x, y):
    width = 500
    height = 105
    line_thickness = 3
    pygame.draw.line(surface, color, (x, y), (x + width, y), line_thickness)
    pygame.draw.line(surface, color, (x, y + height), (x + width, y + height), line_thickness)
    pygame.draw.line(surface, color, (x + width, y), (x + width, y + height), line_thickness)


def static_drawings(screen, base_w, base_h, scale_x, scale_y, circle_time):
    # Example time & date
    time_readable = time.strftime("%A %#I:%M %p")
    date_readable = time.strftime("%B %#d, %Y")
    #weekday       = time.strftime("%A")

    is_auxpanel_online     = True
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

    # Chat Box Rectangle
    chat_rect_base_x, chat_rect_base_y = base_w/3.15, base_h/1.775
    chat_rect_base_w, chat_rect_base_h = 1500, 150
    chat_scaled_rect_x, chat_scaled_rect_y = int(chat_rect_base_x*scale_x - (chat_rect_base_w*scale_x)/2), int(chat_rect_base_y*scale_y - (chat_rect_base_h*scale_y)/2)
    chat_scaled_rect_w, chat_scaled_rect_h = int(chat_rect_base_w*scale_x), int(chat_rect_base_h*scale_y)

    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(chat_scaled_rect_x, chat_scaled_rect_y, chat_scaled_rect_w, chat_scaled_rect_h),
        width=1
    )

    #Chat Response Rectangle
    r_chat_rect_base_x, r_chat_rect_base_y = base_w/3.15, base_h/1.28
    r_chat_rect_base_w, r_chat_rect_base_h = 1500, 450
    r_chat_scaled_rect_x, r_chat_scaled_rect_y = int(r_chat_rect_base_x*scale_x - (r_chat_rect_base_w*scale_x)/2), int(r_chat_rect_base_y*scale_y - (r_chat_rect_base_h*scale_y)/2)
    r_chat_scaled_rect_w, r_chat_scaled_rect_h = int(r_chat_rect_base_w*scale_x), int(r_chat_rect_base_h*scale_y)

    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(r_chat_scaled_rect_x, r_chat_scaled_rect_y, r_chat_scaled_rect_w, r_chat_scaled_rect_h),
        width=1
    )

    #Information Panel
    r_chat_rect_base_x, r_chat_rect_base_y = base_w/4.5, base_h/3.425
    r_chat_rect_base_w, r_chat_rect_base_h = 850, 500
    r_chat_scaled_rect_x, r_chat_scaled_rect_y = int(r_chat_rect_base_x*scale_x - (r_chat_rect_base_w*scale_x)/2), int(r_chat_rect_base_y*scale_y - (r_chat_rect_base_h*scale_y)/2)
    r_chat_scaled_rect_w, r_chat_scaled_rect_h = int(r_chat_rect_base_w*scale_x), int(r_chat_rect_base_h*scale_y)

    pygame.draw.rect(
        screen,
        color,
        pygame.Rect(r_chat_scaled_rect_x, r_chat_scaled_rect_y, r_chat_scaled_rect_w, r_chat_scaled_rect_h),
        width=3
    )

    draw_text_centered("[Weather Forecast]", base_w/4.5, (base_h/14)+150,     color, 40)
    draw_text_centered("[Crypto Price]",     base_w/4.5, (base_h/14)+200,  color, 40)
    draw_text_centered("[Fear Greed Index]", base_w/4.5, (base_h/14)+250,  color, 40)
    draw_text_centered("[Something Else]",   base_w/4.5, (base_h/14)+300,  color, 40)



    # Text
    draw_text_centered(time_readable,   base_w/2, base_h/2.3, color, 56)
    draw_text_centered(date_readable,   base_w/2, base_h/2.1, color, 56)
    #draw_text_centered(weekday,         base_w/2, base_h/2+25, color, 56)
    draw_text_centered("Monkey Butler", base_w/2, base_h/14,  color, 80)
    draw_text_centered("Information", base_w/4, base_h/14,  color, 50)
    draw_text_centered("Systems Status", base_w/1.25, base_h/14,  color, 50)
    draw_text_centered("Chopscorp. Ltd. c 1977", base_w-180, base_h-75,  color, 30)

    scale = 1 

    

    #Gears
    if is_mqtt_online:
       degrees = circle_time * 4
       textbox = "MQTT Broker"
       subtext = "ONLINE"
       gears.draw_dynamo(screen, degrees, color, 1700, 250, scale, textbox, subtext)
    else:
       degrees = 0
       textbox = "MQTT Broker"
       subtext = "OFFLINE"
       gears.draw_dynamo(screen, 0, color_offline, 1700, 250, scale, textbox, subtext)
       
    if is_auxpanel_online:
       degrees = circle_time * 4
       textbox = "Display Panels"
       subtext = "ONLINE"
       gears.draw_dynamo(screen, degrees, color, 1700, 475, scale, textbox, subtext)
    else:
       degrees = 0
       textbox = "Display Panels"
       subtext = "OFFLINE"
       gears.draw_dynamo(screen, degrees, color, 1700, 475, scale, textbox, subtext)

    #Unused Gears
    if is_waterer_online:
        degrees = circle_time * 4
        textbox = "Auto Waterer"
        subtext = "ONLINE"
        gears.draw_dynamo(screen, degrees, color, 1700, 700, scale, textbox, subtext)
    else:
        degrees = 0
        textbox = "Auto Waterer"
        subtext = "OFFLINE"
        gears.draw_dynamo(screen, degrees, color_offline, 1700, 700, scale, textbox, subtext)

    if is_placeholder2_online:
        degrees = circle_time * 4
        textbox = "--"
        subtext = "ONLINE"
        gears.draw_dynamo(screen, degrees, color, 1700, 925, scale, textbox, subtext)
    else:
        degrees = 0
        textbox = "--"
        subtext = "OFFLINE"
        gears.draw_dynamo(screen, degrees, color_offline, 1700, 925, scale, textbox, subtext)
    
    if is_placeholder3_online:
        degrees = circle_time * 4
        textbox = "--"
        subtext = "ONLINE"
        gears.draw_dynamo(screen, degrees, color, 1700, 1150, scale, textbox, subtext)
    else:
        degrees = 0
        textbox = "--"
        subtext = "OFFLINE"
        gears.draw_dynamo(screen, degrees, color_offline, 1700, 1150, scale, textbox, subtext)

def run_info_panel_gui(cmd_queue): #The main Pygame loop. Polls 'cmd_queue' for new commands to display.
    print("Starting Pygame GUI for Info Panel...")

    pygame.init()
    info = pygame.display.Info()

    screen_width, screen_height = info.current_w, info.current_h

    w = screen_width
    h = screen_height

    print("Detected screen resolution:", screen_width, screen_height)

    base_w, base_h = parse_base_resolution()
    print(f"Using base design resolution: {base_w}x{base_h}")

    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    pygame.display.set_caption("Scalable Pygame Port")

    crt = GpuCRT(window_size=(screen_width, screen_height),
           kx=0.18, ky=0.16, curv=0.3,
           scan=0.18, vign=0.45, gamma=2.0)

    scale_x = screen_width / base_w
    scale_y = screen_height / base_h

    clock = pygame.time.Clock()
    running = True
    circle_time = 0

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
    #panel_rect = (screen_width - 900 , 300, 340, 260) # x, y, w, h
    #renderer = vec3d.WireframeRenderer(panel_rect, fov=55, near=0.1, far=50) 
    #mesh = vec3d.cube_mesh(size=0.7) # Create a cube mesh
    #angle = 180.0 # Rotation angle for animation

    # A small helper to draw text on screen (top-left)
    # This can be improved. Why do we need a function specifically for top left?
    # def draw_text_topleft(txt, x, y, color_=(255,255,255), size=30):
    #     font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
    #     surface     = font_scaled.render(txt, True, color_)
    #     screen.blit(surface, (int(x*scale_x), int(y*scale_y)))

    

    def draw_text_topleft(txt, x, y, color_=(255,255,255), size=30, target=None):
        font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))
        surface     = font_scaled.render(str(txt), True, color_).convert_alpha()
        tx = int(x*scale_x)
        ty = int(y*scale_y)
        if target is None:
            screen.blit(surface, (tx, ty))
        else:
            target.blit(surface, (tx, ty))
        return surface
    
    def render_textrect(
        text,
        x, y,
        width, height,
        size,
        color,
        target,
        font_path=font_path
    ):
        # Create font
        font = pygame.font.Font(font_path, size)

        # Word wrap text into a list of lines
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

        # Create the text block surface
        surf = pygame.Surface((width, height), pygame.SRCALPHA)

        line_height = font.get_linesize()
        ty = 0

        for line in lines:
            if ty + line_height > height:
                break
            text_surf = font.render(line, True, color)
            surf.blit(text_surf, (0, ty))
            ty += line_height

        # Blit to target surface at (x, y)
        target.blit(surf, (x, y))

        return surf


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
        framebuffer.fill((0, 1, 0))  # draw to off-screen
        # replace every 'screen' draw call with 'framebuffer' for your content:
        static_drawings(framebuffer, base_w, base_h, scale_x, scale_y, circle_time)

        # ... monkey head, text, 3D render, etc ...
        second = int(time.strftime("%S"))
        dy = 10 if second % 2 == 0 else 0
        mb_base_x = base_w / 3.2
        mb_base_y = base_h / 2 + dy

        debug = True
        if debug:
            draw_monkey_butler_head(framebuffer, mb_base_x+200, mb_base_y+150, scale_x, scale_y, color)
        else:
            draw_monkey_butler_head(framebuffer, mb_base_x, mb_base_y, scale_x, scale_y, color)

        #draw_text_topleft(f"Last command:  {last_command}",  75, 740, color, 36, target=framebuffer)
        #draw_text_topleft(f"Last response: {last_response}", 75, 900, color, 36, target=framebuffer)

        #def render_textrect(text, font, rect, x, y, color_=(255,255,255), size=30, target=None):
        #font_scaled = pygame.font.Font(font_path, int(size*((scale_x+scale_y)/2)))

        #Chat Response Rectangle

        #font_scaled = pygame.font.Sys(font_path, int(30*((scale_x+scale_y)/2)))
        font_scaled = pygame.font.Font(font_path, int(30 * ((scale_x + scale_y) / 2)))

        r_chat_rect_base_x, r_chat_rect_base_y = base_w/3.15, base_h/1.28
        r_chat_rect_base_w, r_chat_rect_base_h = 1500, 450
        r_chat_scaled_rect_x, r_chat_scaled_rect_y = int(r_chat_rect_base_x*scale_x - (r_chat_rect_base_w*scale_x)/2), int(r_chat_rect_base_y*scale_y - (r_chat_rect_base_h*scale_y)/2)
        r_chat_scaled_rect_w, r_chat_scaled_rect_h = int(r_chat_rect_base_w*scale_x), int(r_chat_rect_base_h*scale_y)
        wrap_rect = pygame.Rect(r_chat_scaled_rect_x, r_chat_scaled_rect_y, r_chat_scaled_rect_w, r_chat_scaled_rect_h)

        #render_textrect(f"Last command:  {last_command}",  font_scaled, wrap_rect, 75, 740, color, 36, target=framebuffer)
        #render_textrect(f"Last response: {last_response}", font_scaled, wrap_rect, 75, 900, color, 36, target=framebuffer)
       
        #scale_x = screen_width / base_w
        #scale_y = screen_height / base_h
        render_textrect(
            f"{last_command}",
            #x = 65  * (scale_x),
            #y = 550 * (scale_y*2),
            x = int(screen_width / 29.5384615),
            y = int(screen_height / 1.96363636)+10,
            width  = 1125,
            height = 200,
            size   = 50,
            color  = color,
            target = framebuffer
        )

        render_textrect(
            f"{last_response}",
            #x = 65  * (scale_x),
            #y = 675 * (scale_y*2),
            x = int(screen_width / 29.5384615),
            y = int(screen_height / 1.6)+10,
            width  = 1125,
            height = 300,
            size   = 50,
            color  = color,
            target = framebuffer
        )
        # renderer.draw(
        #     framebuffer,
        #     character,
        #     model_pos     = (0.0, -0.1, 3.2),
        #     model_rot     = (0, angle*0.9, 0),
        #     model_scale   = 3.5,
        #     camera_pos    = (0, 0, 0),
        #     camera_target = (0, 0, 1),
        #     zsort         = True
        # )
        # def draw_mouse_coordinates(surface):
        #     x, y = pygame.mouse.get_pos()
        #     text = font_scaled.render(f"({x}, {y})", True, (255, 255, 255))
        #     surface.blit(text, (10, 10))  # Display in top-left corner
        # draw_mouse_coordinates(framebuffer)

        # === POST FX on a copy (so we can reuse framebuffer if needed) ===
        post = framebuffer.copy()
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
        #angle += 0.01

        

    pygame.quit()
    sys.exit()