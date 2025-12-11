# The Info Panel consists of smaller GUIs. These include wrapped text boxes, character icons, and interface icons

import pygame
from dataclasses import dataclass
import math

FONT_PATH = ""

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

        self.x_centered = self.x + (0.5 * self.obj_width)
        self.y_centered = self.y + (0.5 * self.obj_height)

    def drawCenteredRect(self):
        pygame.draw.rect(self.surface,
                         self.color,
                         (self.x_centered,
                         self.y_centered,
                         self.obj_width,
                         self.obj_height),
                         self.line_width)
        
    def createTextArea(self):
        font = pygame.font.Font(FONT_PATH, self.font_size)
        self.lines = []
        self.current = ""

        for word in self.words:
            test = self.current + word + " "
            if font.size(test)[0] <= self.obj_width:
                self.current = test
            else:
                self.lines.append(self.current)
                self.current = word + " "
        self.lines.append(self.current)

        #Create text block pygame surface

        self.surf = pygame.Surface((self.obj_width, self.obj_height), pygame.SRCALPHA)
        self.line_height = font.get_linesize()
        self.ty = 0

        for line in self.lines:
            if self.ty + self.line_height > self.obj_height:
                break
            self.text_surf = font.render(line, True, self.color)
            self.surf.blit(self.text_surf, (0, self.ty))
            self.ty += self.line_height

        self.surface.blit(self.surf, (self.x, self.y))

        return self.surf


#class dynamo

class Dynamo(Widget):
    def __init__(self, config, supertext, subtext, system_status):
        super().__init__(**vars(config))
        self.supertext     = supertext
        self.subtext       = subtext
        self.system_status = system_status
        self.angle = 0
        self.radius = 75
        self.bump = 15
        self.degrees = 0
    
    def polar_point(self, theta, r):
        return (
            int(self.x + r * math.cos(theta)),
            int(self.y + r * math.sin(theta))
        )
    
    def compute_vertices(self):
        theta_base = math.radians(self.degrees)
        theta_15   = math.radians(15)
        theta_12   = math.radians(12)

        angles_and_radii = [
            (theta_base - theta_15, self.radius),
            (theta_base + theta_15, self.radius),
            (theta_base + theta_12, self.radius + self.bump),
            (theta_base - theta_12, self.radius + self.bump),
        ]

        point_list = [self.polar_point(theta, r) for theta, r in angles_and_radii]
        return point_list
    
    def draw_dynamo(self):
        None

    def draw_gear_tooth(self):
        None