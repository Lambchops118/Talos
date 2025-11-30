import pygame

def render_textrect(text, font, rect, text_color, bg_color=None):

    lines = []
    words = text.split(" ")

    # Build lines one by one
    current_line = ""
    for word in words:
        test_line = current_line + word + " "
        # Check width if we add this word
        if font.size(test_line)[0] <= rect.width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word + " "
    lines.append(current_line)  # Add last line

    # Make surface
    surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    if bg_color:
        surface.fill(bg_color)

    # Render each line
    y = 0
    line_height = font.get_linesize()
    for line in lines:
        if y + line_height > rect.height:
            break  # Stop if no space left
        text_surf = font.render(line, True, text_color)
        surface.blit(text_surf, (0, y))
        y += line_height

    return surface


pygame.init()
screen = pygame.display.set_mode((640, 480))
font = pygame.font.SysFont(None, 24)

text = " words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words words  "

textbox_rect = pygame.Rect(50, 50, 300, 150)

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    screen.fill((30, 30, 30))

    text_surface = render_textrect(
        text, font, textbox_rect,
        (255, 255, 255),      # text color
        (50, 50, 50)          # background
    )
    screen.blit(text_surface, textbox_rect.topleft)

    pygame.display.update()