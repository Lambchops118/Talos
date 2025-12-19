# The Info Panel consists of smaller GUIs. These include wrapped text boxes, character icons, and interface icons

import pygame
from dataclasses import dataclass
import math

FONT_PATH = r"C:\Users\aljac\Desktop\Talos\InfoPanel\VT323-Regular.ttf"

@dataclass
class WidgetConfig:
    surface: pygame.Surface
    x: int
    y: int
    obj_width: int
    obj_height: int
    scale: float
    color: tuple
    text: str
    line_width: int
    font_size: int

class Widget:
    def __init__(self, config: WidgetConfig):
        self.surface     = config.surface
        self.x           = int(config.x * config.scale)
        self.y           = int(config.y * config.scale)
        self.obj_width   = int(config.obj_width * config.scale)
        self.obj_height  = int(config.obj_height * config.scale)
        self.scale       = config.scale
        self.color       = config.color
        self.font_size   = int(config.font_size * config.scale)
        self.line_width  = int(config.line_width * config.scale)

        self.words = config.text.split()

        self.x_centered = self.x # - (0.5 * self.obj_width)
        self.y_centered = self.y # - (0.5 * self.obj_height)

    def drawCenteredRect(self):
        pygame.draw.rect(self.surface,
                         self.color,
                         (self.x_centered,
                         self.y_centered,
                         self.obj_width,
                         self.obj_height),
                         self.line_width)
        
    def render_text_area(self, text: str, x: int, y: int, w: int, h: int, *, font_size=None, color=None):
        font_size = font_size or self.font_size
        color = color or self.color
        font = pygame.font.Font(FONT_PATH, font_size)

        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = current + word + " "
            if font.size(test)[0] <= w:
                current = test
            else:
                lines.append(current)
                current = word + " "
        lines.append(current)

        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        line_height = font.get_linesize()
        ty = 0

        for line in lines:
            if ty + line_height > h:
                break
            text_surf = font.render(line, True, color)
            surf.blit(text_surf, (0, ty))
            ty += line_height

        self.surface.blit(surf, (x, y))
        return surf
        
    def createTextArea(self):
        # default behavior: render config.text inside the widget area
        return self.render_text_area(
            text=" ".join(self.words),
            x=self.x,
            y=self.y,
            w=self.obj_width,
            h=self.obj_height
        )


#class dynamo

class Dynamo(Widget):
    def __init__(self, config, supertext, subtext, system_status, degrees):
        super().__init__(config)
        self.supertext = supertext
        self.subtext = subtext
        self.system_status = system_status

        self.degrees = degrees
        self.radius = 75 * self.scale
        self.bump   = 15 * self.scale
        self.tooth_angle_offsets = [0, 45, 90, 135, 180, 225, 270, 315]

    def polar_point(self, center_x, center_y, theta, r):
        return (
            int(center_x + r * math.cos(theta)),
            int(center_y + r * math.sin(theta))
        )

    def compute_vertices(self, center_x, center_y, degrees):
        theta_base = math.radians(degrees)
        theta_15   = math.radians(15)
        theta_12   = math.radians(12)

        angles_and_radii = [
            (theta_base - theta_15, self.radius),
            (theta_base + theta_15, self.radius),
            (theta_base + theta_12, self.radius + self.bump),
            (theta_base - theta_12, self.radius + self.bump),
        ]

        return [self.polar_point(center_x, center_y, th, r) for th, r in angles_and_radii]

    def draw_dynamo(self):
        center_x = int(self.x_centered)
        center_y = int(self.y_centered)

        pygame.draw.circle(
            self.surface, self.color, (center_x, center_y),
            int(self.radius), width=int(12 * self.scale)
        )

        base = self.degrees
        for offset in self.tooth_angle_offsets:
            tooth_deg = base - offset 
            points = self.compute_vertices(center_x, center_y, tooth_deg)
            pygame.draw.polygon(self.surface, self.color, points)

        line_y_dist = self.radius - self.line_width
        line_length = 600 * self.scale
        height      = (center_y + line_y_dist) - (center_y - line_y_dist)

        pygame.draw.line(self.surface, self.color,
                         (center_x, center_y + line_y_dist),
                         (center_x + line_length, center_y + line_y_dist),
                         self.line_width)
        pygame.draw.line(self.surface, self.color,
                         (center_x, center_y - line_y_dist),
                         (center_x + line_length, center_y - line_y_dist),
                         self.line_width)
        pygame.draw.line(self.surface, self.color,
                         (center_x + line_length - (self.line_width/2),
                          center_y + line_y_dist),
                         (center_x + line_length - (self.line_width/2),
                          center_y - line_y_dist),
                         self.line_width)

        self.render_text_area(self.supertext, (center_x + 0.175*line_length), (center_y-line_y_dist           ), line_length, (height*0.5))
        self.render_text_area(self.subtext,   (center_x + 0.175*line_length), (center_y-line_y_dist+height*0.5), line_length, (height*0.5), font_size=30*self.scale)

        #self.render_text_area("test", 100, 100, 300, 300)
        #self.render_text_area("test2", 50, 50, 300, 300)



# def render_text_area(self, text: str, x: int, y: int, w: int, h: int, *, font_size=None, color=None):
#             def drawCenteredRect(self):
#         pygame.draw.rect(self.surface,
#                          self.color,
#                          (self.x_centered,
#                          self.y_centered,
#                          self.obj_width,
#                          self.obj_height),
#                          self.line_width)
            
            
            
