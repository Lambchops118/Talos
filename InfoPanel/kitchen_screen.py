# Secondary display panel code.
# This code will run on the raspberry pi for the kitchen recipe monitor.

import sys
import pygame
from   dotenv import load_dotenv; load_dotenv()

#import InfoPanel.gears as gears
import windows

font_path     = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"
#font          = pygame.font.SysFont(None, 24)
screen_width  = 1920
screen_height = 1080

color         = (0, 255, 100) # Green Phosphor Color
color_offline = (5, 5, 5)     # Dim Gray for offline
red           = (255, 0, 0)   # Error color



def screen_main():
    print("Starting Kitchen Screen App...")
    pygame.init()
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("Recipe Display")

    clock       = pygame.time.Clock()
    running     = True
    circle_time = 0

    # If you want to use your TTF font:
    # font = pygame.font.Font(font_path, 24)
    font        = pygame.font.SysFont(None, 24)

    angle = 0

    dynamo_configs = [
        dict(x=200, y=200, base_deg=0),
        dict(x=500, y=300, base_deg=45),
        dict(x=800, y=500, base_deg=90),
    ]
    dynamos = [
        windows.Dynamo(
            windows.WidgetConfig(
                surface=screen,
                x=cfg["x"],
                y=cfg["y"],
                obj_width=1,
                obj_height=1,
                scale=1,
                color=(255, 255, 255),
                text="",
                line_width=3,
                font_size=30,
            ),
            "super",
            "sub",
            1,
            cfg["base_deg"],
        )
        for cfg in dynamo_configs
    ]

    def draw_mouse_coordinates(surface):
        x, y = pygame.mouse.get_pos()
        text = font.render(f"({x}, {y})", True, (255, 255, 255))
        surface.blit(text, (10, 10))  # Display in top-left corner

    def render_textrect(text, x, y, width, height, color, target, font_path=font_path):
            #font    = pygame.font.Font(font_path, size) #This can probably be moved outside the function
            font_path = font
            words    = text.split(" ")
            lines    = []
            current  = ""

            pygame.draw.rect(target, color, (x-5, y-5, width+5, height+5), width=2)  # Clear background

            for word in words:
                test = current + word + " "
                if font.size(test)[0] <= width:
                    current = test
                else:
                    lines.append(current)
                    current = word + " "
            lines.append(current)

            surf        = pygame.Surface((width, height), pygame.SRCALPHA)
            line_height = font.get_linesize()
            ty          = 0

            for line in lines:
                if ty + line_height > height:
                    break
                text_surf = font.render(line, True, color)
                surf.blit(text_surf, (0, ty))
                ty += line_height
            target.blit(surf, (x, y))
            return surf



    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        screen.fill((0, 0, 0))  # or your background color
        draw_mouse_coordinates(screen)
        render_textrect(
                f"""PLACEHOLDER: 
                Line 1\n
                Line 2
                Line 3
                Line 4
                Line 5""",
                x      = 50,
                y      = 50,
                width  = 640,
                height = 480,
                color  = color,
                target = screen
            )
        
        angle = (angle + 1.5) % 360
        for d, cfg in zip(dynamos, dynamo_configs):
            d.degrees = angle + cfg["base_deg"]
            d.draw_dynamo()
        
        
        
        pygame.display.flip()
        clock.tick(60)
        circle_time += 1

    pygame.quit()
    sys.exit()


screen_main()