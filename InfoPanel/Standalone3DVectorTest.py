import moving_vector_portrait as vec3d
import pygame

screen_width = 800

 #Code for 3d wireframe panel
panel_rect = (screen_width - 900 , 300, 340, 260) # x, y, w, h
renderer = vec3d.WireframeRenderer(panel_rect, fov=55, near=0.1, far=50) 
mesh = vec3d.cube_mesh(size=0.7) # Create a cube mesh
angle = 180.0 # Rotation angle for animation

print("Complete")