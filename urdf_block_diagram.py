#!/usr/bin/env python3
"""
URDF Block Diagram Generator - Converts URDF files into visual block diagrams
showing the robot's joint/link structure.
"""

import sys
import os
import argparse
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

import sv_ttk


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


class BlockDiagramCanvas(tk.Canvas):
    """Canvas for drawing the block diagram."""
    
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.block_width = 120
        self.block_height = 60
        self.spacing_x = 180
        self.spacing_y = 100
        self.margin = 50
        
        # For dragging functionality
        self.drag_data = {"x": 0, "y": 0, "item": None}
        self.block_map = {}  # Maps canvas items to link names
        self.joint_items = {}  # Maps canvas items to joint objects
        self.hardware_blocks = {}  # Maps joint names to hardware interface blocks
        
        # Bind mouse events
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonPress-3>", self._on_right_click)  # Right-click event
        
    def draw_block(self, x, y, text, block_type="link", selected=False, link_name=None):
        """Draw a block representing a link or joint."""
        if block_type == "link":
            fill_color = "#8ED1FC"  # Light blue for links
            outline_color = "#0693E3"
        else:  # joint
            fill_color = "#ABB8C3"  # Gray for joints
            outline_color = "#555D66"
        
        if selected:
            outline_width = 3
        else:
            outline_width = 1
            
        # Draw the block
        block = self.create_rectangle(
            x - self.block_width/2, y - self.block_height/2,
            x + self.block_width/2, y + self.block_height/2,
            fill=fill_color, outline=outline_color,
            width=outline_width,
            tags="draggable" if link_name else ""
        )
        
        # Draw the text
        text_id = self.create_text(
            x, y, text=text, font=("Arial", 9), width=self.block_width - 10,
            tags="draggable" if link_name else ""
        )
        
        # Store link name to block mapping if provided
        if link_name:
            self.block_map[block] = link_name
            self.block_map[text_id] = link_name
            
        return block, text_id
    
    def draw_arrow(self, x1, y1, x2, y2, joint_type, joint_name=None, 
                  state_interfaces=None, command_interfaces=None, joint_obj=None):
        """Draw an arrow between blocks with color based on joint type."""
        # Set color based on joint type
        if joint_type == "revolute":
            color = "#FF6900"  # Orange
        elif joint_type == "prismatic":
            color = "#FCB900"  # Yellow
        elif joint_type == "fixed":
            color = "#7BDCB5"  # Green
        else:
            color = "#8ED1FC"  # Blue
            
        # Calculate arrow points
        dx = x2 - x1
        dy = y2 - y1
        length = math.sqrt(dx*dx + dy*dy)
        
        if length == 0:
            return
            
        # Normalized direction
        dx, dy = dx/length, dy/length
        
        # Shorten the line to leave space for blocks
        start_x = x1 + dx * self.block_width/2
        start_y = y1 + dy * self.block_height/2
        end_x = x2 - dx * self.block_width/2
        end_y = y2 - dy * self.block_height/2
        
        # Draw the line
        line = self.create_line(
            start_x, start_y, end_x, end_y,
            width=2, arrow=tk.LAST, fill=color,
            tags=f"connector joint_{joint_name}" if joint_name else "connector"
        )
        
        # Add joint type as text near the middle of the arrow
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        
        # Create the joint info text
        joint_info = joint_type
        if joint_name:
            joint_info = f"{joint_name} ({joint_type})"
        
        text_id = self.create_text(
            mid_x, mid_y - 15,
            text=joint_info,
            font=("Arial", 8),
            fill=color,
            tags=f"connector_text joint_{joint_name}" if joint_name else "connector_text"
        )
        
        # Display interfaces if available
        y_offset = 0
        if state_interfaces and len(state_interfaces) > 0:
            self.create_text(
                mid_x, mid_y + y_offset + 5,
                text=f"State: {', '.join(state_interfaces)}",
                font=("Arial", 7),
                fill=color,
                tags=f"connector_text joint_{joint_name}" if joint_name else "connector_text"
            )
            y_offset += 12
        
        if command_interfaces and len(command_interfaces) > 0:
            self.create_text(
                mid_x, mid_y + y_offset + 5,
                text=f"Cmd: {', '.join(command_interfaces)}",
                font=("Arial", 7),
                fill=color,
                tags=f"connector_text joint_{joint_name}" if joint_name else "connector_text"
            )
            y_offset += 12
        
        # Display hardware interfaces if available
        if joint_obj and joint_obj.hardware_interfaces:
            self.create_text(
                mid_x, mid_y + y_offset + 5,
                text=f"Hardware: {', '.join(joint_obj.hardware_interfaces)}",
                font=("Arial", 7, "bold"),  # Bold to highlight it's manually added
                fill="#CF2E2E",  # Red color to make it stand out
                tags=f"connector_text joint_{joint_name}" if joint_name else "connector_text"
            )
            
            # Draw hardware interface block if not yet present
            if joint_name and joint_name not in self.hardware_blocks:
                self.draw_hardware_interface_block(mid_x, mid_y + 60, joint_obj)
        
        # Store joint information for right-click handling
        if joint_name and joint_obj:
            self.joint_items[line] = joint_obj
            self.joint_items[text_id] = joint_obj
        
        return line, text_id
    
    def draw_hardware_interface_block(self, x, y, joint_obj):
        """Draw a hardware interface block associated with a joint."""
        if not joint_obj.hardware_interfaces:
            return
            
        # Draw a distinctive block for hardware interface
        block = self.create_rectangle(
            x - self.block_width/2, y - self.block_height/3,
            x + self.block_width/2, y + self.block_height/3,
            fill="#FFF0F0",  # Light red background
            outline="#CF2E2E",  # Red outline
            width=2,
            tags=f"hw_block joint_{joint_obj.name}"
        )
        
        # Draw the text
        text = f"Hardware Interface\n{', '.join(joint_obj.hardware_interfaces)}"
        text_id = self.create_text(
            x, y, text=text, font=("Arial", 8, "bold"),
            fill="#CF2E2E",
            width=self.block_width - 10,
            tags=f"hw_block joint_{joint_obj.name}"
        )
        
        # Store reference to the hardware block
        self.hardware_blocks[joint_obj.name] = (block, text_id)
        
        # Add connector from joint to hardware interface
        self.create_line(
            x, y - self.block_height/3,  # Top of hardware block
            x, y - 30,  # Below the joint arrow
            width=2, dash=(4, 2),  # Dashed line
            fill="#CF2E2E",
            tags=f"hw_connector joint_{joint_obj.name}"
        )
    
    def update_hardware_interface_block(self, joint_obj):
        """Update or create a hardware interface block for a joint."""
        if joint_obj.name in self.hardware_blocks:
            # Delete existing block
            block, text_id = self.hardware_blocks[joint_obj.name]
            self.delete(block)
            self.delete(text_id)
            self.delete(f"hw_connector joint_{joint_obj.name}")
            del self.hardware_blocks[joint_obj.name]
            
        # Find position of the joint
        items = self.find_withtag(f"joint_{joint_obj.name}")
        if items:
            bbox = self.bbox(items[0])
            if bbox:
                center_x = (bbox[0] + bbox[2]) / 2
                center_y = (bbox[1] + bbox[3]) / 2
                
                # Draw new hardware block if there are interfaces
                if joint_obj.hardware_interfaces:
                    self.draw_hardware_interface_block(center_x, center_y + 60, joint_obj)
        
    def _on_press(self, event):
        """Handle mouse button press event."""
        # Find the closest item that's tagged as draggable
        item = self.find_withtag("current")
        if item and "draggable" in self.gettags(item):
            # Store initial position and item
            self.drag_data["item"] = item
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y
            # Bring item to front
            self.tag_raise(item)
    
    def _on_release(self, event):
        """Handle mouse button release event."""
        # Reset the drag data
        if self.drag_data["item"]:
            # Signal that the layout was manually changed
            self.event_generate("<<LayoutChanged>>", when="tail")
            self.drag_data["item"] = None
    
    def _on_drag(self, event):
        """Handle mouse motion during drag."""
        if self.drag_data["item"]:
            # Calculate the movement delta
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            
            # Move the item and its text
            item = self.drag_data["item"]
            link_name = self.block_map.get(item[0])
            
            if link_name:
                # Move all items related to this link
                for canvas_item, name in self.block_map.items():
                    if name == link_name:
                        self.move(canvas_item, dx, dy)
                
                # Update arrows connected to this link
                self._update_connectors(link_name)
                
                # Update drag starting point
                self.drag_data["x"] = event.x
                self.drag_data["y"] = event.y
    
    def _on_right_click(self, event):
        """Handle right-click event to add hardware interfaces."""
        # Find what item was clicked
        item = self.find_withtag("current")
        if item:
            # Check if the item is associated with a joint
            joint_obj = self.joint_items.get(item[0])
            if joint_obj:
                # Emit event to show dialog for adding hardware interface
                self.event_generate("<<AddHardwareInterface>>", when="tail", 
                                   data=joint_obj.name)
    
    def _update_connectors(self, link_name):
        """Update arrow connectors when a block is moved."""
        # This will be called from the URDFBlockDiagramApp class
        # We need to remove all connectors and redraw them
        self.delete("connector")
        self.delete("connector_text")
        self.delete("hw_block")
        self.delete("hw_connector")
        self.hardware_blocks = {}  # Reset hardware blocks mapping
        
        # The app needs to redraw all connectors
        self.event_generate("<<UpdateConnectors>>", when="tail", data=link_name)
        
    def get_block_position(self, link_name):
        """Get the current position of a block by link name."""
        for item, name in self.block_map.items():
            if name == link_name:
                bbox = self.bbox(item)
                if bbox:
                    # Return center point of the block
                    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        return None


class URDFBlockDiagramApp(tk.Tk):
    """Main application for displaying URDF block diagrams."""
    
    def __init__(self):
        super().__init__()
        self.title("URDF Block Diagram Generator")
        self.geometry("1200x800")
        
        self.setup_ui()
        
        self.links = {}
        self.joints = []
        self.urdf_file = None
        
        # For layout calculation
        self.layout = {}  # Maps link name to (x, y) position
        
        # Bind custom events for draggable blocks
        self.canvas.bind("<<LayoutChanged>>", self._on_layout_changed)
        self.canvas.bind("<<UpdateConnectors>>", self._on_update_connectors)
        self.canvas.bind("<<AddHardwareInterface>>", self._on_add_hardware_interface)
    
    def open_urdf_from_path(self, path):
        """Open a URDF file from the given path."""
        if not os.path.exists(path):
            self.status_var.set(f"Error: File not found: {path}")
            return
            
        try:
            self.status_var.set(f"Loading {os.path.basename(path)}...")
            self.update_idletasks()
            
            # Parse URDF
            parser = URDFParser(path)
            self.links = parser.links
            self.joints = parser.joints
            self.urdf_file = path
            
            # Generate and display diagram
            self.generate_diagram()
            
            self.status_var.set(f"Loaded {os.path.basename(path)}: {len(self.links)} links, {len(self.joints)} joints")
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
        
    def setup_ui(self):
        """Set up the application UI."""
        # Main frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Button(toolbar, text="Open URDF", command=self.open_urdf).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(toolbar, text="Export Diagram", command=self.export_diagram).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(toolbar, text="Reset Layout", command=self.reset_layout).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Help text
        help_text = "Tip: Right-click on a joint to add hardware interfaces"
        ttk.Label(toolbar, text=help_text).pack(side=tk.RIGHT, padx=10)
        
        # Canvas with scrollbars
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        v_scrollbar = ttk.Scrollbar(canvas_frame)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas = BlockDiagramCanvas(
            canvas_frame, 
            bg="white",
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        h_scrollbar.config(command=self.canvas.xview)
        v_scrollbar.config(command=self.canvas.yview)
        
        # Enable canvas scrolling with mouse wheel
        self.canvas.bind("<MouseWheel>", self._on_mousewheel_y)
        self.canvas.bind("<Shift-MouseWheel>", self._on_mousewheel_x)
        
        # Status bar
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_var.set("Ready - Right-click on joints to add hardware interfaces")
    
    def _on_mousewheel_y(self, event):
        """Handle vertical scrolling with mouse wheel."""
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
    
    def _on_mousewheel_x(self, event):
        """Handle horizontal scrolling with mouse wheel."""
        self.canvas.xview_scroll(-1 * (event.delta // 120), "units")
    
    def open_urdf(self):
        """Open and parse a URDF file."""
        filename = filedialog.askopenfilename(
            filetypes=[("URDF files", "*.urdf"), ("XML files", "*.xml"), ("All files", "*.*")]
        )
        
        if not filename:
            return
            
        try:
            self.status_var.set(f"Loading {os.path.basename(filename)}...")
            self.update_idletasks()
            
            # Parse URDF
            parser = URDFParser(filename)
            self.links = parser.links
            self.joints = parser.joints
            self.urdf_file = filename
            
            # Generate and display diagram
            self.generate_diagram()
            
            self.status_var.set(f"Loaded {os.path.basename(filename)}: {len(self.links)} links, {len(self.joints)} joints")
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
    
    def generate_diagram(self):
        """Generate and display the block diagram based on the loaded URDF."""
        if not self.links or not self.joints:
            return
            
        # Clear canvas
        self.canvas.delete("all")
        self.canvas.block_map = {}  # Reset block mapping
        self.canvas.joint_items = {}  # Reset joint mapping
        self.canvas.hardware_blocks = {}  # Reset hardware blocks
        
        # Calculate layout
        self._calculate_layout()
        
        # Draw links
        for link_name, link in self.links.items():
            if link_name in self.layout:
                x, y = self.layout[link_name]
                self.canvas.draw_block(x, y, str(link), "link", link_name=link_name)
        
        # Draw joints (connections)
        self._draw_connections()
        
        # Configure canvas scrolling region
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
        
        # Add a tip about dragging and right-clicking
        self.status_var.set("Tip: Drag blocks to rearrange layout. Right-click on joints to add hardware interfaces.")
    
    def _draw_connections(self):
        """Draw all joint connections between links."""
        for joint in self.joints:
            if joint.parent in self.layout and joint.child in self.layout:
                parent_pos = self.canvas.get_block_position(joint.parent)
                child_pos = self.canvas.get_block_position(joint.child)
                
                if not parent_pos:
                    parent_pos = self.layout[joint.parent]
                
                if not child_pos:
                    child_pos = self.layout[joint.child]
                
                # Draw the connecting arrow with interface info
                self.canvas.draw_arrow(
                    parent_pos[0], parent_pos[1], 
                    child_pos[0], child_pos[1], 
                    joint.joint_type,
                    joint.name,
                    joint.state_interfaces,
                    joint.command_interfaces,
                    joint
                )
    
    def _on_layout_changed(self, event):
        """Handle layout changes from manual dragging."""
        # Update the layout dictionary with current positions
        for link_name in self.links:
            pos = self.canvas.get_block_position(link_name)
            if pos:
                self.layout[link_name] = pos
        
        self.status_var.set("Layout updated manually")
    
    def _on_update_connectors(self, event):
        """Update connectors after a block has been moved."""
        self._draw_connections()
    
    def _on_add_hardware_interface(self, event):
        """Handle adding a hardware interface to a joint."""
        joint_name = event.data
        
        # Find the joint object
        joint = None
        for j in self.joints:
            if j.name == joint_name:
                joint = j
                break
        
        if not joint:
            return
        
        # Show dialog to get hardware interface
        hw_interface = simpledialog.askstring(
            "Add Hardware Interface",
            f"Enter hardware interface for joint {joint_name}:",
            initialvalue=", ".join(joint.hardware_interfaces) if joint.hardware_interfaces else ""
        )
        
        if hw_interface:
            # Update the joint's hardware interfaces
            joint.hardware_interfaces = [iface.strip() for iface in hw_interface.split(",") if iface.strip()]
            
            # Update the diagram
            self.canvas.update_hardware_interface_block(joint)
            
            # Update status
            self.status_var.set(f"Added hardware interface to {joint_name}: {hw_interface}")
    
    def reset_layout(self):
        """Reset the layout to the automatic tree layout."""
        if not self.links or not self.joints:
            return
        
        # Clear the layout
        self.layout = {}
        
        # Recalculate and redraw
        self.generate_diagram()
        
        self.status_var.set("Layout reset to automatic tree layout")
    
    def _calculate_layout(self):
        """Calculate the positions of links in the diagram."""
        # Only calculate positions for links that don't have a position yet
        # This preserves manual positioning
        
        # Find the root links (links that are not a child in any joint)
        child_links = set(joint.child for joint in self.joints)
        root_links = [link for link in self.links if link not in child_links]
        
        if not root_links and self.links:
            # If no root found, just use the first link
            root_links = [list(self.links.keys())[0]]
        
        # Use a tree layout algorithm (simple version)
        for i, root in enumerate(root_links):
            self._layout_subtree(root, 0, i * self.canvas.spacing_y * 2)
    
    def _layout_subtree(self, link_name, depth, y_offset):
        """Recursively layout a subtree starting at the given link."""
        # Skip if this link already has a position
        if link_name in self.layout:
            return
            
        # Position this link
        x = self.canvas.margin + depth * self.canvas.spacing_x
        y = self.canvas.margin + y_offset
        self.layout[link_name] = (x, y)
        
        # Find all children of this link
        children = []
        for joint in self.joints:
            if joint.parent == link_name:
                children.append((joint.child, joint))
        
        # Layout each child subtree
        for i, (child, _) in enumerate(children):
            child_y_offset = y_offset + i * self.canvas.spacing_y
            self._layout_subtree(child, depth + 1, child_y_offset)
    
    def export_diagram(self):
        """Export the diagram as a PostScript file."""
        if not self.links or not self.joints:
            self.status_var.set("No diagram to export")
            return
            
        filename = filedialog.asksaveasfilename(
            defaultextension=".ps",
            filetypes=[("PostScript", "*.ps"), ("All files", "*.*")]
        )
        
        if filename:
            self.canvas.postscript(file=filename, colormode='color')
            self.status_var.set(f"Diagram exported to {os.path.basename(filename)}")


def main():
    """Main function to parse arguments and run the application."""
    parser = argparse.ArgumentParser(
        description="Generate block diagrams from URDF files."
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
        app.after(100, lambda: app.open_urdf_from_path(args.urdf_file))
    

    # This is where the magic happens
    sv_ttk.set_theme("dark")
    app.mainloop()


if __name__ == "__main__":
    main()