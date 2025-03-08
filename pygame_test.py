import pygame

# Initialize pygame
pygame.init()

# Set up display
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pygame Test Window")

# Define colors
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

# Set up font
font = pygame.font.Font(None, 36)
text = font.render("Pygame is working!", True, BLUE)
text_rect = text.get_rect(center=(WIDTH//2, HEIGHT//2))

# Main loop
running = True
while running:
    screen.fill(WHITE)  # Clear screen
    
    # Draw shapes
    pygame.draw.rect(screen, RED, (50, 50, 200, 100))  # Red rectangle
    pygame.draw.circle(screen, GREEN, (400, 300), 50)  # Green circle
    pygame.draw.line(screen, BLUE, (100, 500), (700, 500), 5)  # Blue line
    
    # Render text
    screen.blit(text, text_rect)
    
    # Event handling
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
    
    pygame.display.flip()  # Update display

pygame.quit()
