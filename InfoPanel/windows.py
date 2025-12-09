# The Info Panel consists of smaller GUIs. These include wrapped text boxes, character icons, and interface icons

import pygame

FONT_PATH = ""

class WindowFrame:
    def __init__(self, surface, x, y, width, height, scale, color, text, line_width, font_size):
        self.surface = surface
        self.x       = x
        self.y       = y
        self.height  = height
        self.width   = width
        self.scale   = scale #size and scale are different. Size is size, scale is a multiplier based on screen resolution
        self.color   = color
        self.line_width = line_width
        self.words = text.split
        self.font_size = font_size

    def defineCenter(self):
        self.x_centered = self.x + (0.5*self.width)
        self.y_centered = self.y + (0.5*self.height)

    def drawCenteredRect(self):
        pygame.draw.rect(self.surface,
                         self.color,
                         self.x_centered,
                         self.y_centered,
                         self.width,
                         self.height,
                         self.line_width)
        
    def createTextArea(self):
        font = pygame.font.Font(FONT_PATH, self.font_size)
        self.lines = []
        self.current = ""

        for word in self.words:
            test = self.current + word + " "
            if font.size(test)[0] <= self.width:
                self.current = test
            else:
                self.lines.append(self.current)
                self.current = word + " "
        self.lines.append(self.current)

        #Create text block pygame surface

        self.surf = pygame.Surface((self.width, self.height), pygame.SCRALPHA)
        self.line_height = font.get_linesize()
        self.ty = 0

        for line in self.lines:
            if self.ty + self.line_height > self.height:
                break
            self.text_surf = font.render(line, True, self.color)
            self.surf.blit(self.text_surf, (0, self.ty))
            self.ty += self.line_height

        self.target.blit(self.surf, (self.x, self.x))

        return self.surf


#class dynamo