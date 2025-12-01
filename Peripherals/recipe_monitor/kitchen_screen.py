# Secondary display panel code.
# This code will run on the raspberry pi for the kitchen recipe monitor.

import sys
import time
import queue
import pygame
from   dotenv import load_dotenv; load_dotenv()

font_path     = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"
screen_width  = 640
screen_height = 480

color         = (0, 255, 100) # Green Phosphor Color
color_offline = (5, 5, 5)     # Dim Gray for offline
red           = (255, 0, 0)   # Error color

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


def draw_mouse_coordinates(surface):
    x, y = pygame.mouse.get_pos()
    text = font.render(f"({x}, {y})", True, (255, 255, 255))
    surface.blit(text, (10, 10))  # Display in top-left corner

def render_textrect(text, x, y, width, height, size, color, target, font_path=font):
        #font    = pygame.font.Font(font_path, size) #This can probably be moved outside the function
        font_path = font
        words   = text.split(" ")
        lines   = []
        current = ""

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

    # 1. Clear the screen each frame
    screen.fill((0, 0, 0))  # or your background color

    # 2. Draw stuff
    draw_mouse_coordinates(screen)

    render_textrect(
            f"PLACEHOLDER: . . . . . . .  . .  . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . . . . . . . . .  . .",
            x      = 0,
            y      = 00,
            width  = 640,
            height = 480,
            size   = 30,
            color  = color,
            target = screen
        )

    # 3. Flip/update the display
    pygame.display.flip()

    # 4. Cap the frame rate
    clock.tick(60)

pygame.quit()
sys.exit()