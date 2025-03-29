import math
import pygame

def gear_draw(screen, degrees, color, x, y, scale_x, scale_y):
    """
    Draws one 'gear wedge' polygon at (x, y) with a given rotation (degrees).
    Allows for scaling the gear radius if you want the gear to scale
    with the screen resolution.

    :param screen:   Pygame surface
    :param degrees:  Rotation in degrees
    :param color:    Wedge color
    :param x, y:     Center coords (already scaled from the main code, or unscaled if you prefer)
    :param scale_x:  Horizontal scale factor for the gear radius
    :param scale_y:  Vertical scale factor for the gear radius
    """
    # Base sizes for the gear wedge
    radius_base = 75
    bump_base   = 15

    # Scale the radius based on the average of scale_x, scale_y
    # so it doesn't become an ellipse shape at non-square resolutions.
    avg_scale = (scale_x + scale_y) / 2.0
    radius    = radius_base * avg_scale
    bump      = bump_base   * avg_scale

    def get_theta(d):
        return d * (math.pi / 180)

    def get_x(theta, r):
        return x + r * math.cos(theta)

    def get_y(theta, r):
        return y + r * math.sin(theta)

    # Compute the corners of the polygon wedge
    xOne = get_x(get_theta(degrees - 15), radius)
    yOne = get_y(get_theta(degrees - 15), radius)

    xTwo = get_x(get_theta(degrees + 15), radius)
    yTwo = get_y(get_theta(degrees + 15), radius)

    xThree = get_x(get_theta(degrees - 12), radius + bump)
    yThree = get_y(get_theta(degrees - 12), radius + bump)

    xFour = get_x(get_theta(degrees + 12), radius + bump)
    yFour = get_y(get_theta(degrees + 12), radius + bump)

    point_list = [
        (int(xOne),   int(yOne)),
        (int(xTwo),   int(yTwo)),
        (int(xFour),  int(yFour)),
        (int(xThree), int(yThree))
    ]

    # Draw the filled wedge polygon
    pygame.draw.polygon(screen, color, point_list)

def gear_place(screen, degrees, color, x, y, scale_x, scale_y):
    """
    Draws multiple 'gear wedge' polygons around a central point
    at angles offset by 45 degrees from each other, then an outer ring.

    :param screen:   Pygame surface
    :param degrees:  Rotation in degrees
    :param color:    Gear color
    :param x, y:     Gear center (scaled or unscaled as you like)
    :param scale_x:  Horizontal scale factor for radius
    :param scale_y:  Vertical scale factor for radius
    """
    # Draw each wedge at a 45-degree offset
    gear_draw(screen, degrees,     color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 45,  color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 90,  color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 135, color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 180, color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 225, color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 270, color, x, y, scale_x, scale_y)
    gear_draw(screen, degrees - 315, color, x, y, scale_x, scale_y)

    # Also draw a ring around the center, scaled as well
    avg_scale = (scale_x + scale_y) / 2.0
    radius    = int(75 * avg_scale)

    pygame.draw.circle(screen, color, (int(x), int(y)), radius, width=6)