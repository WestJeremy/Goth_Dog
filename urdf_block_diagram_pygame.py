#!/usr/bin/env python3
"""
URDF Block Diagram Generator - Pygame Version
Converts URDF files into visual block diagrams showing the robot's joint/link structure.
"""

import sys
import os
import argparse
import xml.etree.ElementTree as ET
import math
import pygame
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import tkinter as tk
from tkinter import filedialog, simpledialog


@dataclass
class Link:
    """Represents a robot link from the URDF."""
    name: str
    visual: bool = False  # Whether the link has visual elements
    collision: bool = False  # Whether the link has collision elements
    inertial: bool = False  # Whether the link has inertial properties
    
    def __str__(self) -> str:
        properties = []
        if self.visual:
            properties.append("visual")
        if self.collision:
            properties.append("collision")
        if self.inertial:
            properties.append("inertial")
        
        if properties:
            return f"{self.name} ({', '.join(properties)})"
        return self.name


@dataclass
class Joint:
    """Represents a robot joint from the URDF."""
    name: str
    joint_type: str
    parent: str
    child: str
    axis: Optional[Tuple[float, float, float]] = None
    limit: Optional[Dict[str, float]] = None
    # New fields for interfaces
    state_interfaces: List[str] = None
    command_interfaces: List[str] = None
    # Hardware interfaces (added manually by the user)
    hardware_interfaces: List[str] = None
    
    def __post_init__(self):
        # Initialize lists if they were None
        if self.state_interfaces is None:
            self.state_interfaces = []
        if self.command_interfaces is None:
            self.command_interfaces = []
        if self.hardware_interfaces is None:
            self.hardware_interfaces = []
        
        # Add default interfaces based on joint type if none specified
        if not self.state_interfaces:
            if self.joint_type in ["revolute", "prismatic", "continuous"]:
                self.state_interfaces = ["position", "velocity"]
            elif self.joint_type == "fixed":
                self.state_interfaces = []
        
        if not self.command_interfaces:
            if self.joint_type in ["revolute", "prismatic", "continuous"]:
                self.command_interfaces = ["position"]
            elif self.joint_type == "fixed":
                self.command_interfaces = []
    
    def __str__(self) -> str:
        joint_info = f"{self.name} ({self.joint_type})"
        
        # Add interface information if present
        interface_info = []
        if self.state_interfaces:
            interface_info.append(f"state: {', '.join(self.state_interfaces)}")
        if self.command_interfaces:
            interface_info.append(f"cmd: {', '.join(self.command_interfaces)}")
        
        if interface_info:
            joint_info += f"\n{'; '.join(interface_info)}"
        
        return joint_info


class URDFParser:
    """Parse URDF XML files and extract link and joint information."""
    
    def __init__(self, urdf_file: str):
        """Initialize with URDF file path."""
        self.urdf_file = urdf_file
        self.links: Dict[str, Link] = {}
        self.joints: List[Joint] = []
        self.parse()
    
    def parse(self):
        """Parse the URDF file."""
        try:
            tree = ET.parse(self.urdf_file)
            root = tree.getroot()
            
            # Parse links
            for link_elem in root.findall('link'):
                name = link_elem.get('name')
                visual = len(link_elem.findall('visual')) > 0
                collision = len(link_elem.findall('collision')) > 0
                inertial = link_elem.find('inertial') is not None
                
                self.links[name] = Link(name, visual, collision, inertial)
            
            # Parse joints
            for joint_elem in root.findall('joint'):
                name = joint_elem.get('name')
                joint_type = joint_elem.get('type')
                
                parent_elem = joint_elem.find('parent')
                child_elem = joint_elem.find('child')
                
                if parent_elem is not None and child_elem is not None:
                    parent = parent_elem.get('link')
                    child = child_elem.get('link')
                    
                    # Parse axis if present
                    axis = None
                    axis_elem = joint_elem.find('axis')
                    if axis_elem is not None:
                        xyz = axis_elem.get('xyz')
                        if xyz:
                            axis = tuple(map(float, xyz.split()))
                    
                    # Parse limits if present
                    limit = None
                    limit_elem = joint_elem.find('limit')
                    if limit_elem is not None:
                        limit = {}
                        for attr in ['lower', 'upper', 'effort', 'velocity']:
                            val = limit_elem.get(attr)
                            if val:
                                limit[attr] = float(val)
                    
                    # Look for state and command interfaces (custom extension)
                    state_interfaces = []
                    command_interfaces = []
                    
                    # Check for ros2_control tag first (common in ROS 2 URDF files)
                    ros2_control = joint_elem.find('./ros2_control')
                    if ros2_control is not None:
                        state_interfaces_elem = ros2_control.find('./state_interfaces')
                        if state_interfaces_elem is not None:
                            for interface in state_interfaces_elem.findall('./interface'):
                                state_interfaces.append(interface.get('name'))
                        
                        command_interfaces_elem = ros2_control.find('./command_interfaces')
                        if command_interfaces_elem is not None:
                            for interface in command_interfaces_elem.findall('./interface'):
                                command_interfaces.append(interface.get('name'))
                    
                    # Also check for gazebo ros_control plugin tags
                    gazebo = joint_elem.find('./gazebo')
                    if gazebo is not None:
                        plugin = gazebo.find('./plugin[@name="gazebo_ros_control"]')
                        if plugin is not None:
                            state_ifaces = plugin.find('./state_interface')
                            if state_ifaces is not None and state_ifaces.text:
                                state_interfaces = state_ifaces.text.split()
                            
                            command_ifaces = plugin.find('./command_interface')
                            if command_ifaces is not None and command_ifaces.text:
                                command_interfaces = command_interfaces.text.split()
                                
                    self.joints.append(Joint(
                        name, joint_type, parent, child, 
                        axis, limit, state_interfaces, command_interfaces
                    ))
            
        except ET.ParseError as e:
            print(f"Error parsing URDF file: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}")
            sys.exit(1)


class DrawableBlock:
    """Represents a drawable block (link or hardware interface) on the canvas."""
    
    def __init__(self, x, y, width, height, text, block_type="link", link_name=None):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.block_type = block_type
        self.link_name = link_name
        self.selected = False
        self.dragging = False
        
    def get_rect(self):
        """Get pygame Rect for this block."""
        return pygame.Rect(self.x - self.width//2, self.y - self.height//2, 
                          self.width, self.height)
    
    def contains_point(self, x, y):
        """Check if point is inside this block."""
        return self.get_rect().collidepoint(x, y)
    
    def move(self, dx, dy):
        """Move the block by the given offset."""
        self.x += dx
        self.y += dy


class DrawableArrow:
    """Represents a drawable arrow (joint connection) on the canvas."""
    
    def __init__(self, start_x, start_y, end_x, end_y, joint_obj):
        self.start_x = start_x
        self.start_y = start_y
        self.end_x = end_x
        self.end_y = end_y
        self.joint_obj = joint_obj
        
    def get_midpoint(self):
        """Get the midpoint of the arrow."""
        return ((self.start_x + self.end_x) // 2, (self.start_y + self.end_y) // 2)
    
    def contains_point(self, x, y, threshold=10):
        """Check if point is near the arrow line."""
        # Simple distance from point to line segment
        A = self.end_x - self.start_x
        B = self.end_y - self.start_y
        C = x - self.start_x
        D = y - self.start_y
        
        dot = A * C + B * D
        len_sq = A * A + B * B
        
        if len_sq == 0:
            return False
            
        param = dot / len_sq
        
        if param < 0:
            xx, yy = self.start_x, self.start_y
        elif param > 1:
            xx, yy = self.end_x, self.end_y
        else:
            xx = self.start_x + param * A
            yy = self.start_y + param * B
        
        dx = x - xx
        dy = y - yy
        distance = math.sqrt(dx * dx + dy * dy)
        
        return distance <= threshold


class URDFBlockDiagramApp:
    """Main pygame application for displaying URDF block diagrams."""
    
    def __init__(self):
        pygame.init()
        
        # Screen settings
        self.SCREEN_WIDTH = 1200
        self.SCREEN_HEIGHT = 800
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
        pygame.display.set_caption("URDF Block Diagram Generator - Pygame")
        
        # Colors (dark theme)
        self.COLORS = {
            'background': (45, 45, 45),
            'link_fill': (142, 209, 252),
            'link_outline': (6, 147, 227),
            'joint_fill': (171, 184, 195),
            'joint_outline': (85, 93, 102),
            'revolute': (255, 105, 0),
            'prismatic': (252, 185, 0),
            'fixed': (123, 220, 181),
            'default_joint': (142, 209, 252),
            'hw_fill': (255, 240, 240),
            'hw_outline': (207, 46, 46),
            'hw_text': (207, 46, 46),
            'text': (255, 255, 255),
            'button': (70, 70, 70),
            'button_hover': (90, 90, 90),
            'button_text': (255, 255, 255)
        }
        
        # Layout settings
        self.block_width = 120
        self.block_height = 60
        self.spacing_x = 180
        self.spacing_y = 100
        self.margin = 50
        
        # Camera/viewport
        self.camera_x = 0
        self.camera_y = 0
        
        # Data
        self.links = {}
        self.joints = []
        self.urdf_file = None
        
        # Drawable objects
        self.drawable_blocks = []  # List of DrawableBlock objects
        self.drawable_arrows = []  # List of DrawableArrow objects
        self.layout = {}  # Maps link name to (x, y) position
        
        # Interaction state
        self.dragging_block = None
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        
        # UI elements
        self.buttons = []
        self.setup_ui()
        
        # Fonts
        self.font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 18)
        self.button_font = pygame.font.Font(None, 20)
        
        # Status
        self.status_text = "Ready - Right-click on joints to add hardware interfaces"
        
        # Clock for FPS control
        self.clock = pygame.time.Clock()
        
    def setup_ui(self):
        """Setup UI buttons."""
        button_y = 10
        button_height = 30
        button_spacing = 10
        
        self.buttons = [
            {
                'rect': pygame.Rect(10, button_y, 100, button_height),
                'text': 'Open URDF',
                'action': 'open_urdf'
            },
            {
                'rect': pygame.Rect(120, button_y, 120, button_height),
                'text': 'Export Diagram',
                'action': 'export_diagram'
            },
            {
                'rect': pygame.Rect(250, button_y, 100, button_height),
                'text': 'Reset Layout',
                'action': 'reset_layout'
            }
        ]
    
    def open_urdf_from_path(self, path):
        """Open a URDF file from the given path."""
        if not os.path.exists(path):
            self.status_text = f"Error: File not found: {path}"
            return
            
        try:
            self.status_text = f"Loading {os.path.basename(path)}..."
            
            # Parse URDF
            parser = URDFParser(path)
            self.links = parser.links
            self.joints = parser.joints
            self.urdf_file = path
            
            # Generate and display diagram
            self.generate_diagram()
            
            self.status_text = f"Loaded {os.path.basename(path)}: {len(self.links)} links, {len(self.joints)} joints"
            
        except Exception as e:
            self.status_text = f"Error: {str(e)}"
    
    def open_urdf(self):
        """Open and parse a URDF file using file dialog."""
        # Create a temporary tkinter root for file dialog
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        filename = filedialog.askopenfilename(
            filetypes=[("URDF files", "*.urdf"), ("XML files", "*.xml"), ("All files", "*.*")]
        )
        
        root.destroy()  # Clean up
        
        if filename:
            self.open_urdf_from_path(filename)
    
    def generate_diagram(self):
        """Generate and display the block diagram based on the loaded URDF."""
        if not self.links or not self.joints:
            return
            
        # Clear previous diagram
        self.drawable_blocks = []
        self.drawable_arrows = []
        
        # Calculate layout
        self._calculate_layout()
        
        # Create drawable blocks for links
        for link_name, link in self.links.items():
            if link_name in self.layout:
                x, y = self.layout[link_name]
                block = DrawableBlock(x, y, self.block_width, self.block_height, 
                                    str(link), "link", link_name)
                self.drawable_blocks.append(block)
        
        # Create drawable arrows for joints
        self._create_arrows()
        
        self.status_text = "Tip: Drag blocks to rearrange layout. Right-click on joints to add hardware interfaces."
    
    def _create_arrows(self):
        """Create drawable arrows for all joints."""
        self.drawable_arrows = []
        
        for joint in self.joints:
            if joint.parent in self.layout and joint.child in self.layout:
                parent_pos = self.layout[joint.parent]
                child_pos = self.layout[joint.child]
                
                arrow = DrawableArrow(parent_pos[0], parent_pos[1], 
                                    child_pos[0], child_pos[1], joint)
                self.drawable_arrows.append(arrow)
                
                # Create hardware interface blocks if needed
                if joint.hardware_interfaces:
                    mid_x, mid_y = arrow.get_midpoint()
                    hw_block = DrawableBlock(mid_x, mid_y + 60, self.block_width, 
                                           self.block_height//2, 
                                           f"Hardware: {', '.join(joint.hardware_interfaces)}", 
                                           "hardware", f"hw_{joint.name}")
                    self.drawable_blocks.append(hw_block)
    
    def _calculate_layout(self):
        """Calculate the positions of links in the diagram."""
        # Find the root links (links that are not a child in any joint)
        child_links = set(joint.child for joint in self.joints)
        root_links = [link for link in self.links if link not in child_links]
        
        if not root_links and self.links:
            # If no root found, just use the first link
            root_links = [list(self.links.keys())[0]]
        
        # Use a tree layout algorithm (simple version)
        for i, root in enumerate(root_links):
            self._layout_subtree(root, 0, i * self.spacing_y * 2)
    
    def _layout_subtree(self, link_name, depth, y_offset):
        """Recursively layout a subtree starting at the given link."""
        # Skip if this link already has a position
        if link_name in self.layout:
            return
            
        # Position this link
        x = self.margin + depth * self.spacing_x
        y = self.margin + y_offset
        self.layout[link_name] = (x, y)
        
        # Find all children of this link
        children = []
        for joint in self.joints:
            if joint.parent == link_name:
                children.append((joint.child, joint))
        
        # Layout each child subtree
        for i, (child, _) in enumerate(children):
            child_y_offset = y_offset + i * self.spacing_y
            self._layout_subtree(child, depth + 1, child_y_offset)
    
    def reset_layout(self):
        """Reset the layout to the automatic tree layout."""
        if not self.links or not self.joints:
            return
        
        # Clear the layout
        self.layout = {}
        
        # Recalculate and redraw
        self.generate_diagram()
        
        self.status_text = "Layout reset to automatic tree layout"
    
    def export_diagram(self):
        """Export the diagram as a PNG file."""
        if not self.drawable_blocks:
            self.status_text = "No diagram to export"
            return
        
        # Create a temporary tkinter root for file dialog
        root = tk.Tk()
        root.withdraw()
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
        )
        
        root.destroy()
        
        if filename:
            # Create a surface with the diagram bounds
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            
            for block in self.drawable_blocks:
                min_x = min(min_x, block.x - block.width//2)
                max_x = max(max_x, block.x + block.width//2)
                min_y = min(min_y, block.y - block.height//2)
                max_y = max(max_y, block.y + block.height//2)
            
            # Add some padding
            padding = 50
            width = int(max_x - min_x + 2 * padding)
            height = int(max_y - min_y + 2 * padding)
            
            # Create export surface
            export_surface = pygame.Surface((width, height))
            export_surface.fill(self.COLORS['background'])
            
            # Draw everything to export surface with offset
            offset_x = -min_x + padding
            offset_y = -min_y + padding
            
            # Draw arrows first
            for arrow in self.drawable_arrows:
                self._draw_arrow_on_surface(export_surface, arrow, offset_x, offset_y)
            
            # Draw blocks
            for block in self.drawable_blocks:
                self._draw_block_on_surface(export_surface, block, offset_x, offset_y)
            
            # Save the surface
            pygame.image.save(export_surface, filename)
            self.status_text = f"Diagram exported to {os.path.basename(filename)}"
    
    def _draw_block_on_surface(self, surface, block, offset_x, offset_y):
        """Draw a block on the given surface with offset."""
        x = block.x + offset_x
        y = block.y + offset_y
        
        rect = pygame.Rect(x - block.width//2, y - block.height//2, 
                          block.width, block.height)
        
        if block.block_type == "link":
            color = self.COLORS['link_fill']
            outline_color = self.COLORS['link_outline']
        elif block.block_type == "hardware":
            color = self.COLORS['hw_fill']
            outline_color = self.COLORS['hw_outline']
        else:
            color = self.COLORS['joint_fill']
            outline_color = self.COLORS['joint_outline']
        
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, outline_color, rect, 2)
        
        # Draw text
        self._draw_text_on_surface(surface, block.text, x, y, block.width - 10)
    
    def _draw_arrow_on_surface(self, surface, arrow, offset_x, offset_y):
        """Draw an arrow on the given surface with offset."""
        start_x = arrow.start_x + offset_x
        start_y = arrow.start_y + offset_y
        end_x = arrow.end_x + offset_x
        end_y = arrow.end_y + offset_y
        
        joint = arrow.joint_obj
        
        # Get color based on joint type
        if joint.joint_type == "revolute":
            color = self.COLORS['revolute']
        elif joint.joint_type == "prismatic":
            color = self.COLORS['prismatic']
        elif joint.joint_type == "fixed":
            color = self.COLORS['fixed']
        else:
            color = self.COLORS['default_joint']
        
        # Calculate shortened line (to avoid overlapping with blocks)
        dx = end_x - start_x
        dy = end_y - start_y
        length = math.sqrt(dx*dx + dy*dy)
        
        if length > 0:
            dx, dy = dx/length, dy/length
            
            # Shorten the line
            start_x += dx * self.block_width//2
            start_y += dy * self.block_height//2
            end_x -= dx * self.block_width//2
            end_y -= dy * self.block_height//2
            
            # Draw line
            pygame.draw.line(surface, color, (start_x, start_y), (end_x, end_y), 3)
            
            # Draw arrowhead
            self._draw_arrowhead_on_surface(surface, end_x, end_y, dx, dy, color)
            
            # Draw joint info
            mid_x = (start_x + end_x) // 2
            mid_y = (start_y + end_y) // 2
            
            joint_text = f"{joint.name} ({joint.joint_type})"
            text_surface = self.small_font.render(joint_text, True, color)
            text_rect = text_surface.get_rect(center=(mid_x, mid_y - 15))
            surface.blit(text_surface, text_rect)
            
            # Draw interface info
            y_offset = 5
            if joint.state_interfaces:
                state_text = f"State: {', '.join(joint.state_interfaces)}"
                text_surface = self.small_font.render(state_text, True, color)
                text_rect = text_surface.get_rect(center=(mid_x, mid_y + y_offset))
                surface.blit(text_surface, text_rect)
                y_offset += 15
            
            if joint.command_interfaces:
                cmd_text = f"Cmd: {', '.join(joint.command_interfaces)}"
                text_surface = self.small_font.render(cmd_text, True, color)
                text_rect = text_surface.get_rect(center=(mid_x, mid_y + y_offset))
                surface.blit(text_surface, text_rect)
                y_offset += 15
            
            if joint.hardware_interfaces:
                hw_text = f"Hardware: {', '.join(joint.hardware_interfaces)}"
                text_surface = self.small_font.render(hw_text, True, self.COLORS['hw_text'])
                text_rect = text_surface.get_rect(center=(mid_x, mid_y + y_offset))
                surface.blit(text_surface, text_rect)
    
    def _draw_arrowhead_on_surface(self, surface, x, y, dx, dy, color):
        """Draw an arrowhead on the given surface."""
        # Calculate arrowhead points
        arrow_length = 15
        arrow_angle = 0.5
        
        # Calculate perpendicular vector
        perp_x = -dy
        perp_y = dx
        
        # Calculate arrowhead points
        p1_x = x - dx * arrow_length + perp_x * arrow_length * arrow_angle
        p1_y = y - dy * arrow_length + perp_y * arrow_length * arrow_angle
        p2_x = x - dx * arrow_length - perp_x * arrow_length * arrow_angle
        p2_y = y - dy * arrow_length - perp_y * arrow_length * arrow_angle
        
        # Draw arrowhead
        pygame.draw.polygon(surface, color, [(x, y), (p1_x, p1_y), (p2_x, p2_y)])
    
    def _draw_text_on_surface(self, surface, text, x, y, max_width):
        """Draw text on the given surface with word wrapping."""
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if self.small_font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # Draw lines
        line_height = self.small_font.get_height()
        total_height = len(lines) * line_height
        start_y = y - total_height // 2
        
        for i, line in enumerate(lines):
            text_surface = self.small_font.render(line, True, self.COLORS['text'])
            text_rect = text_surface.get_rect(center=(x, start_y + i * line_height + line_height // 2))
            surface.blit(text_surface, text_rect)
    
    def handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self._handle_left_click(event.pos)
                elif event.button == 3:  # Right click
                    self._handle_right_click(event.pos)
            
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:  # Left click release
                    self._handle_left_release()
            
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event.pos, event.rel)
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and pygame.key.get_pressed()[pygame.K_LCTRL]:
                    self.reset_layout()
                elif event.key == pygame.K_o and pygame.key.get_pressed()[pygame.K_LCTRL]:
                    self.open_urdf()
                elif event.key == pygame.K_s and pygame.key.get_pressed()[pygame.K_LCTRL]:
                    self.export_diagram()
        
        return True
    
    def _handle_left_click(self, pos):
        """Handle left mouse button click."""
        mouse_x, mouse_y = pos
        
        # Check button clicks first
        for button in self.buttons:
            if button['rect'].collidepoint(mouse_x, mouse_y):
                self._handle_button_click(button['action'])
                return
        
        # Adjust for camera
        world_x = mouse_x + self.camera_x
        world_y = mouse_y + self.camera_y
        
        # Check if clicking on a draggable block
        for block in self.drawable_blocks:
            if block.block_type == "link" and block.contains_point(world_x, world_y):
                self.dragging_block = block
                self.drag_offset_x = world_x - block.x
                self.drag_offset_y = world_y - block.y
                block.selected = True
                break
        else:
            # Clear selection if not clicking on a block
            for block in self.drawable_blocks:
                block.selected = False
    
    def _handle_left_release(self):
        """Handle left mouse button release."""
        if self.dragging_block:
            # Update layout with new position
            if self.dragging_block.link_name and self.dragging_block.link_name in self.layout:
                self.layout[self.dragging_block.link_name] = (self.dragging_block.x, self.dragging_block.y)
                # Regenerate arrows to match new positions
                self._create_arrows()
            
            self.dragging_block = None
    
    def _handle_right_click(self, pos):
        """Handle right mouse button click."""
        mouse_x, mouse_y = pos
        
        # Adjust for camera
        world_x = mouse_x + self.camera_x
        world_y = mouse_y + self.camera_y
        
        # Check if right-clicking on an arrow (joint)
        for arrow in self.drawable_arrows:
            if arrow.contains_point(world_x, world_y):
                self._add_hardware_interface(arrow.joint_obj)
                break
    
    def _handle_mouse_motion(self, pos, rel):
        """Handle mouse motion."""
        mouse_x, mouse_y = pos
        
        if self.dragging_block:
            # Adjust for camera
            world_x = mouse_x + self.camera_x
            world_y = mouse_y + self.camera_y
            
            # Move the block
            self.dragging_block.x = world_x - self.drag_offset_x
            self.dragging_block.y = world_y - self.drag_offset_y
        
        self.last_mouse_x, self.last_mouse_y = mouse_x, mouse_y
    
    def _handle_button_click(self, action):
        """Handle button click."""
        if action == 'open_urdf':
            self.open_urdf()
        elif action == 'export_diagram':
            self.export_diagram()
        elif action == 'reset_layout':
            self.reset_layout()
    
    def _add_hardware_interface(self, joint):
        """Add hardware interface to a joint."""
        # Create a temporary tkinter root for input dialog
        root = tk.Tk()
        root.withdraw()
        
        current_interfaces = ", ".join(joint.hardware_interfaces) if joint.hardware_interfaces else ""
        
        hw_interface = simpledialog.askstring(
            "Add Hardware Interface",
            f"Enter hardware interface for joint {joint.name}:",
            initialvalue=current_interfaces
        )
        
        root.destroy()
        
        if hw_interface:
            # Update the joint's hardware interfaces
            joint.hardware_interfaces = [iface.strip() for iface in hw_interface.split(",") if iface.strip()]
            
            # Regenerate the diagram
            self._create_arrows()
            
            self.status_text = f"Added hardware interface to {joint.name}: {hw_interface}"
    
    def draw(self):
        """Draw the entire application."""
        # Clear screen
        self.screen.fill(self.COLORS['background'])
        
        # Draw arrows first (so they appear behind blocks)
        for arrow in self.drawable_arrows:
            self._draw_arrow(arrow)
        
        # Draw blocks
        for block in self.drawable_blocks:
            self._draw_block(block)
        
        # Draw UI
        self._draw_ui()
        
        # Draw status
        self._draw_status()
        
        pygame.display.flip()
    
    def _draw_block(self, block):
        """Draw a single block."""
        # Apply camera transformation
        screen_x = block.x - self.camera_x
        screen_y = block.y - self.camera_y
        
        # Skip if outside screen
        if (screen_x < -block.width or screen_x > self.SCREEN_WIDTH + block.width or
            screen_y < -block.height or screen_y > self.SCREEN_HEIGHT + block.height):
            return
        
        rect = pygame.Rect(screen_x - block.width//2, screen_y - block.height//2, 
                          block.width, block.height)
        
        if block.block_type == "link":
            color = self.COLORS['link_fill']
            outline_color = self.COLORS['link_outline']
        elif block.block_type == "hardware":
            color = self.COLORS['hw_fill']
            outline_color = self.COLORS['hw_outline']
        else:
            color = self.COLORS['joint_fill']
            outline_color = self.COLORS['joint_outline']
        
        # Draw block
        pygame.draw.rect(self.screen, color, rect)
        
        # Draw outline (thicker if selected)
        outline_width = 3 if block.selected else 2
        pygame.draw.rect(self.screen, outline_color, rect, outline_width)
        
        # Draw text
        self._draw_wrapped_text(block.text, screen_x, screen_y, block.width - 10)
    
    def _draw_arrow(self, arrow):
        """Draw a single arrow."""
        # Apply camera transformation
        start_x = arrow.start_x - self.camera_x
        start_y = arrow.start_y - self.camera_y
        end_x = arrow.end_x - self.camera_x
        end_y = arrow.end_y - self.camera_y
        
        joint = arrow.joint_obj
        
        # Get color based on joint type
        if joint.joint_type == "revolute":
            color = self.COLORS['revolute']
        elif joint.joint_type == "prismatic":
            color = self.COLORS['prismatic']
        elif joint.joint_type == "fixed":
            color = self.COLORS['fixed']
        else:
            color = self.COLORS['default_joint']
        
        # Calculate shortened line (to avoid overlapping with blocks)
        dx = end_x - start_x
        dy = end_y - start_y
        length = math.sqrt(dx*dx + dy*dy)
        
        if length > 0:
            dx, dy = dx/length, dy/length
            
            # Shorten the line
            start_x += dx * self.block_width//2
            start_y += dy * self.block_height//2
            end_x -= dx * self.block_width//2
            end_y -= dy * self.block_height//2
            
            # Draw line
            pygame.draw.line(self.screen, color, (start_x, start_y), (end_x, end_y), 3)
            
            # Draw arrowhead
            self._draw_arrowhead(end_x, end_y, dx, dy, color)
            
            # Draw joint info
            mid_x = (start_x + end_x) // 2
            mid_y = (start_y + end_y) // 2
            
            joint_text = f"{joint.name} ({joint.joint_type})"
            text_surface = self.small_font.render(joint_text, True, color)
            text_rect = text_surface.get_rect(center=(mid_x, mid_y - 15))
            self.screen.blit(text_surface, text_rect)
            
            # Draw interface info
            y_offset = 5
            if joint.state_interfaces:
                state_text = f"State: {', '.join(joint.state_interfaces)}"
                text_surface = self.small_font.render(state_text, True, color)
                text_rect = text_surface.get_rect(center=(mid_x, mid_y + y_offset))
                self.screen.blit(text_surface, text_rect)
                y_offset += 15
            
            if joint.command_interfaces:
                cmd_text = f"Cmd: {', '.join(joint.command_interfaces)}"
                text_surface = self.small_font.render(cmd_text, True, color)
                text_rect = text_surface.get_rect(center=(mid_x, mid_y + y_offset))
                self.screen.blit(text_surface, text_rect)
                y_offset += 15
            
            if joint.hardware_interfaces:
                hw_text = f"Hardware: {', '.join(joint.hardware_interfaces)}"
                text_surface = self.small_font.render(hw_text, True, self.COLORS['hw_text'])
                text_rect = text_surface.get_rect(center=(mid_x, mid_y + y_offset))
                self.screen.blit(text_surface, text_rect)
    
    def _draw_arrowhead(self, x, y, dx, dy, color):
        """Draw an arrowhead."""
        # Calculate arrowhead points
        arrow_length = 15
        arrow_angle = 0.5
        
        # Calculate perpendicular vector
        perp_x = -dy
        perp_y = dx
        
        # Calculate arrowhead points
        p1_x = x - dx * arrow_length + perp_x * arrow_length * arrow_angle
        p1_y = y - dy * arrow_length + perp_y * arrow_length * arrow_angle
        p2_x = x - dx * arrow_length - perp_x * arrow_length * arrow_angle
        p2_y = y - dy * arrow_length - perp_y * arrow_length * arrow_angle
        
        # Draw arrowhead
        pygame.draw.polygon(self.screen, color, [(x, y), (p1_x, p1_y), (p2_x, p2_y)])
    
    def _draw_wrapped_text(self, text, x, y, max_width):
        """Draw text with word wrapping."""
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if self.small_font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        # Draw lines
        line_height = self.small_font.get_height()
        total_height = len(lines) * line_height
        start_y = y - total_height // 2
        
        for i, line in enumerate(lines):
            text_surface = self.small_font.render(line, True, self.COLORS['text'])
            text_rect = text_surface.get_rect(center=(x, start_y + i * line_height + line_height // 2))
            self.screen.blit(text_surface, text_rect)
    
    def _draw_ui(self):
        """Draw the UI elements."""
        # Draw buttons
        mouse_pos = pygame.mouse.get_pos()
        
        for button in self.buttons:
            # Check if mouse is over button
            is_hover = button['rect'].collidepoint(mouse_pos)
            color = self.COLORS['button_hover'] if is_hover else self.COLORS['button']
            
            pygame.draw.rect(self.screen, color, button['rect'])
            pygame.draw.rect(self.screen, self.COLORS['button_text'], button['rect'], 2)
            
            # Draw button text
            text_surface = self.button_font.render(button['text'], True, self.COLORS['button_text'])
            text_rect = text_surface.get_rect(center=button['rect'].center)
            self.screen.blit(text_surface, text_rect)
    
    def _draw_status(self):
        """Draw the status bar."""
        status_surface = self.font.render(self.status_text, True, self.COLORS['text'])
        self.screen.blit(status_surface, (10, self.SCREEN_HEIGHT - 30))
    
    def run(self):
        """Main game loop."""
        running = True
        
        while running:
            running = self.handle_events()
            self.draw()
            self.clock.tick(60)  # 60 FPS
        
        pygame.quit()


def main():
    """Main function to parse arguments and run the application."""
    parser = argparse.ArgumentParser(
        description="Generate block diagrams from URDF files using Pygame."
    )
    parser.add_argument(
        "urdf_file", 
        nargs="?",
        help="Path to the URDF file"
    )
    
    args = parser.parse_args()
    
    app = URDFBlockDiagramApp()
    
    # If a file was provided as an argument, load it
    if args.urdf_file:
        app.open_urdf_from_path(args.urdf_file)
    
    app.run()


if __name__ == "__main__":
    main()
