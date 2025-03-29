import pygame

def draw_monkey_butler_head(screen, dx, dy, scale_x, scale_y, color):
    """
    Draws the Monkey Butler vector art portrait, originally defined with
    a bottom-left origin (Arcade style). We flip vertically and scale
    so it appears upright in PyGame’s top-left coordinate system.
    
    :param screen:   Pygame surface on which to draw
    :param dx:       Where to draw (x, already scaled or unscaled depending on your usage)
    :param dy:       Where to draw (y, same comment as above)
    :param scale_x:  Horizontal scale factor for the shape’s internal coords
    :param scale_y:  Vertical scale factor for the shape’s internal coords
    :param color:    Base color for the outline
    """

    # We'll keep the vertical flip so the shape stays the same orientation it had in Arcade.
    screen_height = screen.get_height()

    # Helper: transform old shape coords (ax, ay) to the new system
    def t(ax, ay):
        """
        1) Scales the local shape coordinate (ax, ay)
        2) Offsets by (dx, dy)
        3) Flips vertically to keep the original orientation
        """
        scaled_x = int(ax * scale_x)
        scaled_y = int(ay * scale_y)
        real_x   = dx + scaled_x
        real_y   = screen_height - (dy + scaled_y)
        return (real_x, real_y)

    # We'll use the given 'color' for outlines,
    # and keep black for “fill” inside the glasses.
    c = color
    color_black = (0, 0, 0)

    #
    # NOSE
    #
    pygame.draw.line(screen, c, t(465, 325), t(470, 310), width=1)
    pygame.draw.line(screen, c, t(470, 310), t(465, 270), width=1)
    pygame.draw.line(screen, c, t(490, 310), t(495, 325), width=1)
    pygame.draw.line(screen, c, t(475, 280), t(480, 270), width=1)
    pygame.draw.line(screen, c, t(485, 280), t(495, 270), width=1)
    pygame.draw.line(screen, c, t(465, 270), t(475, 280), width=1)
    pygame.draw.line(screen, c, t(480, 270), t(485, 280), width=1)
    pygame.draw.line(screen, c, t(495, 270), t(490, 310), width=1)

    #
    # HEAD Outline
    #
    pygame.draw.line(screen, c, t(365, 340), t(365, 305), width=1)
    pygame.draw.line(screen, c, t(595, 305), t(595, 340), width=1)
    pygame.draw.line(screen, c, t(365, 305), t(380, 300), width=1)
    pygame.draw.line(screen, c, t(595, 305), t(595, 340), width=1)
    pygame.draw.line(screen, c, t(380, 300), t(380, 240), width=1)
    pygame.draw.line(screen, c, t(580, 300), t(595, 305), width=1)
    pygame.draw.line(screen, c, t(380, 240), t(430, 215), width=1)
    pygame.draw.line(screen, c, t(580, 240), t(580, 300), width=1)
    pygame.draw.line(screen, c, t(430, 215), t(430, 200), width=1)
    pygame.draw.line(screen, c, t(530, 215), t(580, 240), width=1)
    pygame.draw.line(screen, c, t(430, 200), t(480, 190), width=1)
    pygame.draw.line(screen, c, t(530, 200), t(530, 215), width=1)
    pygame.draw.line(screen, c, t(480, 190), t(530, 200), width=1)

    #
    # SNOUT / brow
    #
    pygame.draw.line(screen, c, t(440, 385), t(460, 380), width=1)
    pygame.draw.line(screen, c, t(460, 380), t(480, 375), width=1)
    pygame.draw.line(screen, c, t(480, 375), t(500, 380), width=1)
    pygame.draw.line(screen, c, t(500, 380), t(520, 385), width=1)

    # muzzle and mouth
    pygame.draw.line(screen, c, t(455, 310), t(435, 265), width=1)
    pygame.draw.line(screen, c, t(435, 265), t(435, 250), width=1)
    pygame.draw.line(screen, c, t(525, 265), t(505, 310), width=1)
    pygame.draw.line(screen, c, t(435, 250), t(455, 225), width=1)
    pygame.draw.line(screen, c, t(525, 250), t(525, 265), width=1)
    pygame.draw.line(screen, c, t(525, 250), t(495, 255), width=1)
    pygame.draw.line(screen, c, t(455, 225), t(480, 220), width=1)
    pygame.draw.line(screen, c, t(505, 225), t(480, 220), width=1)
    pygame.draw.line(screen, c, t(505, 225), t(525, 250), width=1)
    pygame.draw.line(screen, c, t(465, 255), t(435, 250), width=1)
    pygame.draw.line(screen, c, t(465, 255), t(495, 255), width=1)

    #
    # HAIR
    #
    pygame.draw.line(screen, c, t(480, 425), t(460, 435), width=1)
    pygame.draw.line(screen, c, t(460, 435), t(400, 415), width=1)
    pygame.draw.line(screen, c, t(400, 415), t(365, 370), width=1)
    pygame.draw.line(screen, c, t(365, 370), t(345, 370), width=1)
    pygame.draw.line(screen, c, t(345, 370), t(365, 340), width=1)
    pygame.draw.line(screen, c, t(365, 340), t(400, 350), width=1)
    pygame.draw.line(screen, c, t(400, 350), t(440, 385), width=1)
    pygame.draw.line(screen, c, t(440, 385), t(480, 400), width=1)
    pygame.draw.line(screen, c, t(480, 400), t(520, 385), width=1)
    pygame.draw.line(screen, c, t(520, 385), t(575, 350), width=1)
    pygame.draw.line(screen, c, t(575, 350), t(595, 340), width=1)
    pygame.draw.line(screen, c, t(595, 340), t(640, 370), width=1)
    pygame.draw.line(screen, c, t(640, 370), t(610, 385), width=1)
    pygame.draw.line(screen, c, t(610, 385), t(560, 430), width=1)
    pygame.draw.line(screen, c, t(560, 430), t(535, 430), width=1)
    pygame.draw.line(screen, c, t(535, 430), t(480, 425), width=1)

    #
    # GLASSES
    #
    pygame.draw.circle(screen, c, t(430, 335), 36, width=1)
    pygame.draw.circle(screen, c, t(530, 335), 36, width=1)
    pygame.draw.line(screen, c, t(430, 335), t(530, 335), width=1)
    pygame.draw.line(screen, c, t(430, 325), t(365, 340), width=1)
    pygame.draw.line(screen, c, t(530, 325), t(595, 340), width=1)

    # Fill with black circles
    pygame.draw.circle(screen, color_black, t(430, 335), 35)
    pygame.draw.circle(screen, color_black, t(530, 335), 35)

    # Left lens lines
    pygame.draw.line(screen, c, t(405, 350), t(430, 350), width=1)
    pygame.draw.line(screen, c, t(405, 342), t(445, 342), width=1)
    pygame.draw.line(screen, c, t(405, 334), t(425, 334), width=1)
    pygame.draw.line(screen, c, t(405, 326), t(450, 326), width=1)
    pygame.draw.line(screen, c, t(405, 318), t(415, 318), width=1)
    pygame.draw.line(screen, c, t(430, 318), t(445, 318), width=1)

    # Right lens lines
    pygame.draw.line(screen, c, t(515, 360), t(530, 360), width=1)
    pygame.draw.line(screen, c, t(515, 352), t(525, 352), width=1)
    pygame.draw.line(screen, c, t(515, 344), t(535, 344), width=1)
    pygame.draw.line(screen, c, t(515, 336), t(530, 336), width=1)
    pygame.draw.line(screen, c, t(540, 336), t(550, 336), width=1)
    pygame.draw.line(screen, c, t(515, 328), t(530, 328), width=1)
    pygame.draw.line(screen, c, t(515, 320), t(535, 320), width=1)
    pygame.draw.line(screen, c, t(515, 312), t(530, 312), width=1)

    #
    # DRIP
    #
    pygame.draw.line(screen, c, t(580, 260), t(675, 240), width=1)
    pygame.draw.line(screen, c, t(380, 260), t(290, 240), width=1)