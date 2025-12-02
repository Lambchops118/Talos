import math
import pygame

def draw_gear_tooth(screen, degrees, color, x, y, scale):
    radius_base = 75
    bump_base   = 15

    # Scale the radius based on the average of scale_x, scale_y
    # so it doesn't become an ellipse shape at non-square resolutions.
    radius    = radius_base * scale
    bump      = bump_base   * scale

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

def gear_place(screen, degrees, color, x, y, scale):
    # Radius of inner gear and tooth angles
    radius = 75 * scale
    tooth_angle_offsets = [0, 45, 90, 135, 180, 225, 270, 315]
    # Draw gear and teeth
    pygame.draw.circle(screen, color, (int(x), int(y)), radius, width=round(12*scale))
    for offset in tooth_angle_offsets:
         draw_gear_tooth(screen, degrees - offset, color, x, y, scale)
    return radius

def draw_dynamo(screen, degrees, center_x, center_y, scale, color): #Gear + Info Tab 
        #Draw Gear Part
        print("Drawing Dynamo at gear center:", center_x, center_y)
        radius = gear_place(screen, degrees, color, center_x, center_y, scale)
        width  = int(10 * scale)
        #Draw Info Tab Part
        line_y_dist  = radius - (width*0.5)
        line_length  = 500 * scale

        pygame.draw.line(screen, color, (center_x, center_y + line_y_dist), (center_x + line_length, center_y + line_y_dist), width)
        pygame.draw.line(screen, color, (center_x, center_y - line_y_dist), (center_x + line_length, center_y - line_y_dist), width)
        pygame.draw.line(screen, color, (center_x + line_length - (width/2), center_y + line_y_dist), (center_x + line_length-(width/2), center_y - line_y_dist), width)

        
        