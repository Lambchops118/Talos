import pygame

pygame.init()
screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("CRT Text Effect")

# Load font
font = pygame.font.Font("VT323-Regular.ttf", 40)  # Change font path as needed

# Colors for CRT glow
TEXT_COLOR = (0, 255, 0)  # Classic green CRT
GLOW_COLOR = (0, 100, 0)  # Darker green for glow effect

# Render glow effect by layering slightly offset copies of the text
def render_crt_text(text, x, y):
    text_surface = font.render(text, True, TEXT_COLOR)
    glow_surface = font.render(text, True, GLOW_COLOR)

    # Blit multiple layers for a glow effect
    for dx in [-2, 2]:
        for dy in [-2, 2]:
            screen.blit(glow_surface, (x + dx, y + dy))
    
    # Blit main text on top
    screen.blit(text_surface, (x, y))

def draw_scanlines():
    for y in range(0, 600, 4):  # Adjust spacing for effect
        pygame.draw.line(screen, (0, 50, 0), (0, y), (800, y), 1)

running = True
while running:
    screen.fill((0, 0, 0))  # Black background
    render_crt_text("I, Monkey", 200, 250)

    draw_scanlines()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    pygame.display.flip()

pygame.quit()
