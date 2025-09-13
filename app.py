#!/usr/bin/env python3
"""
Visual Block Editor - A simple app for creating blocks with inputs/outputs and generating code.
"""

import sys
import os
import json
import uuid
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field, asdict

import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from tkinter import font as tkfont

# ======================= DATA MODELS =======================

@dataclass
class Port:
    """Represents an input or output port on a block."""
    id: str
    name: str
    data_type: str
    position: Tuple[int, int] = field(default_factory=lambda: (0, 0))
    is_input: bool = True
    connected_to: Optional[str] = None
    
    @classmethod
    def create_input(cls, name: str, data_type: str = "any"):
        """Factory method to create an input port."""
        return cls(id=str(uuid.uuid4()), name=name, data_type=data_type, is_input=True)
    
    @classmethod
    def create_output(cls, name: str, data_type: str = "any"):
        """Factory method to create an output port."""
        return cls(id=str(uuid.uuid4()), name=name, data_type=data_type, is_input=False)


@dataclass
class Block:
    """Represents a visual block with inputs and outputs."""
    id: str
    name: str
    block_type: str
    x: int
    y: int
    width: int = 150
    height: int = 100
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def add_input(self, name: str, data_type: str = "any") -> Port:
        """Add an input port to the block."""
        port = Port.create_input(name, data_type)
        self.inputs.append(port)
        self._update_port_positions()
        return port
    
    def add_output(self, name: str, data_type: str = "any") -> Port:
        """Add an output port to the block."""
        port = Port.create_output(name, data_type)
        self.outputs.append(port)
        self._update_port_positions()
        return port
    
    def _update_port_positions(self):
        """Update the positions of all ports based on the block's dimensions."""
        # Position input ports on the left side
        input_spacing = self.height / (len(self.inputs) + 1) if self.inputs else 0
        for i, port in enumerate(self.inputs):
            port.position = (0, (i + 1) * input_spacing)
        
        # Position output ports on the right side
        output_spacing = self.height / (len(self.outputs) + 1) if self.outputs else 0
        for i, port in enumerate(self.outputs):
            port.position = (self.width, (i + 1) * output_spacing)
    
    def get_port_by_id(self, port_id: str) -> Optional[Port]:
        """Find a port by its ID."""
        for port in self.inputs + self.outputs:
            if port.id == port_id:
                return port
        return None
    
    def to_code(self) -> str:
        """Generate code representation of this block."""
        if self.block_type == "input_value":
            return f"{self.name} = {self.properties.get('default_value', '0')}"
        elif self.block_type == "output_value":
            return f"# Output: {self.name}"
        elif self.block_type == "operation":
            op = self.properties.get("operation", "+")
            # This is simplified; in reality would need to handle connections
            return f"result = input1 {op} input2"
        elif self.block_type == "function":
            func_name = self.properties.get("function_name", "my_function")
            params = ", ".join([inp.name for inp in self.inputs])
            return f"def {func_name}({params}):\n    return {self.outputs[0].name if self.outputs else 'None'}"
        else:
            return f"# Block: {self.name}"


@dataclass
class Connection:
    """Represents a connection between an output port and an input port."""
    id: str
    source_block_id: str
    source_port_id: str
    target_block_id: str
    target_port_id: str
    
    @property
    def key(self) -> Tuple[str, str]:
        """Returns a unique key for this connection."""
        return (self.source_port_id, self.target_port_id)


@dataclass
class BlockCanvas:
    """Represents the canvas containing blocks and connections."""
    blocks: Dict[str, Block] = field(default_factory=dict)
    connections: Dict[str, Connection] = field(default_factory=dict)
    
    def add_block(self, block: Block) -> None:
        """Add a block to the canvas."""
        self.blocks[block.id] = block
    
    def remove_block(self, block_id: str) -> None:
        """Remove a block and its connections from the canvas."""
        if block_id in self.blocks:
            # Remove any connections involving this block
            conn_to_remove = []
            for conn_id, conn in self.connections.items():
                if conn.source_block_id == block_id or conn.target_block_id == block_id:
                    conn_to_remove.append(conn_id)
            
            for conn_id in conn_to_remove:
                del self.connections[conn_id]
            
            # Remove the block
            del self.blocks[block_id]
    
    def connect_ports(self, source_block_id: str, source_port_id: str, 
                      target_block_id: str, target_port_id: str) -> Optional[Connection]:
        """Connect an output port to an input port."""
        source_block = self.blocks.get(source_block_id)
        target_block = self.blocks.get(target_block_id)
        
        if not (source_block and target_block):
            return None
        
        source_port = source_block.get_port_by_id(source_port_id)
        target_port = target_block.get_port_by_id(target_port_id)
        
        if not (source_port and target_port):
            return None
        
        # Ensure we're connecting an output to an input
        if source_port.is_input or not target_port.is_input:
            return None
        
        # Ensure compatible data types (simplified check)
        if source_port.data_type != "any" and target_port.data_type != "any" and \
           source_port.data_type != target_port.data_type:
            return None
        
        # Create and store the connection
        conn = Connection(
            id=str(uuid.uuid4()),
            source_block_id=source_block_id,
            source_port_id=source_port_id,
            target_block_id=target_block_id,
            target_port_id=target_port_id
        )
        
        # Update the ports to reference this connection
        target_port.connected_to = source_port_id
        
        self.connections[conn.id] = conn
        return conn
    
    def disconnect_ports(self, conn_id: str) -> None:
        """Remove a connection between ports."""
        if conn_id in self.connections:
            conn = self.connections[conn_id]
            
            # Clear port references
            target_block = self.blocks.get(conn.target_block_id)
            if target_block:
                target_port = target_block.get_port_by_id(conn.target_port_id)
                if target_port:
                    target_port.connected_to = None
            
            # Remove the connection
            del self.connections[conn_id]
    
    def generate_code(self) -> str:
        """Generate code from the blocks and connections."""
        # This is a simplified implementation
        code_lines = ["# Generated Code", ""]
        
        # Sort blocks to handle dependencies (very simple approach)
        # In a real implementation, you'd want topological sorting
        blocks_list = list(self.blocks.values())
        blocks_list.sort(key=lambda b: 0 if b.block_type == "input_value" else 
                                      (1 if b.block_type == "operation" else 2))
        
        # Generate code for each block
        for block in blocks_list:
            code_lines.append(block.to_code())
        
        return "\n".join(code_lines)
    
    def save_to_json(self, filename: str) -> None:
        """Save the current canvas to a JSON file."""
        data = {
            "blocks": {bid: asdict(block) for bid, block in self.blocks.items()},
            "connections": {cid: asdict(conn) for cid, conn in self.connections.items()}
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load_from_json(cls, filename: str) -> 'BlockCanvas':
        """Load a canvas from a JSON file."""
        with open(filename, 'r') as f:
            data = json.load(f)
        
        canvas = cls()
        
        # Reconstruct blocks
        for bid, block_data in data["blocks"].items():
            inputs = [Port(**p) for p in block_data["inputs"]]
            outputs = [Port(**p) for p in block_data["outputs"]]
            
            block = Block(
                id=block_data["id"],
                name=block_data["name"],
                block_type=block_data["block_type"],
                x=block_data["x"],
                y=block_data["y"],
                width=block_data["width"],
                height=block_data["height"],
                inputs=inputs,
                outputs=outputs,
                properties=block_data["properties"]
            )
            canvas.blocks[bid] = block
        
        # Reconstruct connections
        for cid, conn_data in data["connections"].items():
            conn = Connection(
                id=conn_data["id"],
                source_block_id=conn_data["source_block_id"],
                source_port_id=conn_data["source_port_id"],
                target_block_id=conn_data["target_block_id"],
                target_port_id=conn_data["target_port_id"]
            )
            canvas.connections[cid] = conn
            
            # Update port connections
            target_block = canvas.blocks.get(conn.target_block_id)
            if target_block:
                target_port = target_block.get_port_by_id(conn.target_port_id)
                if target_port:
                    target_port.connected_to = conn.source_port_id
        
        return canvas


# ======================= UI COMPONENTS =======================

class VisualBlockEditor(tk.Tk):
    """Main application window for the Visual Block Editor."""
    
    def __init__(self):
        super().__init__()
        
        self.title("Visual Block Editor")
        self.geometry("1200x800")
        
        self.canvas_model = BlockCanvas()
        self.selected_block: Optional[str] = None
        self.dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        
        # For connection drawing
        self.connection_start = None
        self.temp_connection_line = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI components."""
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top toolbar
        self.toolbar = ttk.Frame(self.main_frame)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Button(self.toolbar, text="New", command=self.new_project).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(self.toolbar, text="Open", command=self.open_project).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(self.toolbar, text="Save", command=self.save_project).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(self.toolbar, text="Generate Code", command=self.show_generated_code).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Sidebar for block types
        self.sidebar = ttk.Frame(self.main_frame, width=200)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        ttk.Label(self.sidebar, text="Block Types").pack(pady=5)
        
        block_types = [
            ("Input Value", "input_value"),
            ("Output Value", "output_value"),
            ("Operation", "operation"),
            ("Function", "function")
        ]
        
        for name, block_type in block_types:
            btn = ttk.Button(self.sidebar, text=name,
                           command=lambda t=block_type, n=name: self.add_new_block(t, n))
            btn.pack(fill=tk.X, padx=5, pady=2)
        
        # Canvas area
        self.canvas_frame = ttk.Frame(self.main_frame)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Canvas bindings
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Delete>", self.delete_selected)
        
        # Right-click context menu
        self.context_menu = tk.Menu(self.canvas, tearoff=0)
        self.context_menu.add_command(label="Edit Block", command=self.edit_block)
        self.context_menu.add_command(label="Delete Block", command=self.delete_selected)
        
        self.canvas.bind("<ButtonPress-3>", self.show_context_menu)
    
    def add_new_block(self, block_type: str, name: str):
        """Add a new block to the canvas."""
        block_id = str(uuid.uuid4())
        
        # Default position in the center of the visible canvas
        x = self.canvas.winfo_width() // 2
        y = self.canvas.winfo_height() // 2
        
        block = Block(id=block_id, name=name, block_type=block_type, x=x, y=y)
        
        # Add default ports based on block type
        if block_type == "input_value":
            block.add_output("value", "number")
            block.properties["default_value"] = "0"
        elif block_type == "output_value":
            block.add_input("value", "any")
        elif block_type == "operation":
            block.add_input("input1", "number")
            block.add_input("input2", "number")
            block.add_output("result", "number")
            block.properties["operation"] = "+"
        elif block_type == "function":
            block.add_input("param1", "any")
            block.add_output("return_value", "any")
            block.properties["function_name"] = "my_function"
        
        # Add the block to the model
        self.canvas_model.add_block(block)
        
        # Draw the block
        self.draw_block(block)
    
    def draw_block(self, block: Block):
        """Draw a block on the canvas."""
        # Draw the block rectangle
        rect_id = self.canvas.create_rectangle(
            block.x, block.y,
            block.x + block.width, block.y + block.height,
            fill="lightblue", outline="black", tags=(f"block:{block.id}", "block")
        )
        
        # Draw the block title
        self.canvas.create_text(
            block.x + block.width//2, block.y + 15,
            text=block.name,
            fill="black",
            font=tkfont.Font(family="Arial", size=10, weight="bold"),
            tags=(f"block:{block.id}", "block")
        )
        
        # Draw input ports
        for port in block.inputs:
            port_x = block.x + port.position[0]
            port_y = block.y + port.position[1]
            self.canvas.create_oval(
                port_x - 5, port_y - 5,
                port_x + 5, port_y + 5,
                fill="red", tags=(f"port:{port.id}", f"block:{block.id}", "port", "input_port")
            )
            self.canvas.create_text(
                port_x + 20, port_y,
                text=port.name,
                fill="black",
                anchor=tk.W,
                tags=(f"block:{block.id}", "block")
            )
        
        # Draw output ports
        for port in block.outputs:
            port_x = block.x + port.position[0]
            port_y = block.y + port.position[1]
            self.canvas.create_oval(
                port_x - 5, port_y - 5,
                port_x + 5, port_y + 5,
                fill="green", tags=(f"port:{port.id}", f"block:{block.id}", "port", "output_port")
            )
            self.canvas.create_text(
                port_x - 20, port_y,
                text=port.name,
                fill="black",
                anchor=tk.E,
                tags=(f"block:{block.id}", "block")
            )
    
    def draw_connection(self, conn: Connection):
        """Draw a connection between ports."""
        source_block = self.canvas_model.blocks.get(conn.source_block_id)
        target_block = self.canvas_model.blocks.get(conn.target_block_id)
        
        if not (source_block and target_block):
            return
        
        source_port = source_block.get_port_by_id(conn.source_port_id)
        target_port = target_block.get_port_by_id(conn.target_port_id)
        
        if not (source_port and target_port):
            return
        
        # Calculate port positions
        source_x = source_block.x + source_port.position[0]
        source_y = source_block.y + source_port.position[1]
        target_x = target_block.x + target_port.position[0]
        target_y = target_block.y + target_port.position[1]
        
        # Draw the connection line
        self.canvas.create_line(
            source_x, source_y, target_x, target_y,
            fill="black", width=2, smooth=True,
            tags=(f"connection:{conn.id}", "connection")
        )
    
    def redraw_canvas(self):
        """Redraw all elements on the canvas."""
        self.canvas.delete("all")
        
        # Draw all blocks
        for block in self.canvas_model.blocks.values():
            self.draw_block(block)
        
        # Draw all connections
        for conn in self.canvas_model.connections.values():
            self.draw_connection(conn)
    
    def on_canvas_click(self, event):
        """Handle mouse click on the canvas."""
        # Check if we clicked on a block
        items = self.canvas.find_withtag("current")
        if items:
            tags = self.canvas.gettags(items[0])
            for tag in tags:
                if tag.startswith("block:"):
                    block_id = tag.split(":", 1)[1]
                    self.select_block(block_id)
                    self.dragging = True
                    self.drag_start_x = event.x
                    self.drag_start_y = event.y
                    return
                elif tag.startswith("port:"):
                    port_id = tag.split(":", 1)[1]
                    if "output_port" in tags:
                        self.start_connection(port_id)
                    return
        
        # If we clicked on empty space, clear selection
        self.selected_block = None
        self.redraw_canvas()
    
    def on_canvas_drag(self, event):
        """Handle mouse drag on the canvas."""
        if self.dragging and self.selected_block:
            # Move the selected block
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            
            block = self.canvas_model.blocks.get(self.selected_block)
            if block:
                block.x += dx
                block.y += dy
                
                # Update port positions
                block._update_port_positions()
                
                # Redraw everything
                self.redraw_canvas()
            
            self.drag_start_x = event.x
            self.drag_start_y = event.y
        elif self.connection_start:
            # Draw temporary connection line
            if self.temp_connection_line:
                self.canvas.delete(self.temp_connection_line)
            
            # Find the starting port position
            source_port_id = self.connection_start
            source_block_id = None
            for block_id, block in self.canvas_model.blocks.items():
                for port in block.outputs:
                    if port.id == source_port_id:
                        source_block_id = block_id
                        source_x = block.x + port.position[0]
                        source_y = block.y + port.position[1]
                        break
                if source_block_id:
                    break
            
            if source_block_id:
                self.temp_connection_line = self.canvas.create_line(
                    source_x, source_y, event.x, event.y,
                    fill="gray", width=2, dash=(4, 4),
                    tags=("temp_connection")
                )
    
    def on_canvas_release(self, event):
        """Handle mouse release on the canvas."""
        if self.dragging:
            self.dragging = False
        elif self.connection_start:
            # Check if we released on an input port
            items = self.canvas.find_overlapping(event.x-5, event.y-5, event.x+5, event.y+5)
            target_port_id = None
            target_block_id = None
            
            for item in items:
                tags = self.canvas.gettags(item)
                for tag in tags:
                    if tag.startswith("port:") and "input_port" in tags:
                        target_port_id = tag.split(":", 1)[1]
                    elif tag.startswith("block:"):
                        target_block_id = tag.split(":", 1)[1]
            
            if target_port_id and target_block_id:
                # Find the source block ID
                source_block_id = None
                for block_id, block in self.canvas_model.blocks.items():
                    for port in block.outputs:
                        if port.id == self.connection_start:
                            source_block_id = block_id
                            break
                    if source_block_id:
                        break
                
                if source_block_id:
                    # Create the connection
                    self.canvas_model.connect_ports(
                        source_block_id, self.connection_start,
                        target_block_id, target_port_id
                    )
                    self.redraw_canvas()
            
            # Clean up the temporary connection
            if self.temp_connection_line:
                self.canvas.delete(self.temp_connection_line)
                self.temp_connection_line = None
            self.connection_start = None
    
    def select_block(self, block_id: str):
        """Select a block and highlight it."""
        self.selected_block = block_id
        self.redraw_canvas()
        
        # Highlight the selected block
        if block_id in self.canvas_model.blocks:
            items = self.canvas.find_withtag(f"block:{block_id}")
            for item in items:
                if "oval" not in str(item):  # Don't change port colors
                    self.canvas.itemconfig(item, outline="red", width=2)
    
    def start_connection(self, port_id: str):
        """Start drawing a connection from an output port."""
        self.connection_start = port_id
    
    def delete_selected(self, event=None):
        """Delete the currently selected block."""
        if self.selected_block:
            self.canvas_model.remove_block(self.selected_block)
            self.selected_block = None
            self.redraw_canvas()
    
    def edit_block(self):
        """Edit the properties of the selected block."""
        if not self.selected_block:
            return
        
        block = self.canvas_model.blocks.get(self.selected_block)
        if not block:
            return
        
        # Create a dialog to edit the block
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Block: {block.name}")
        dialog.geometry("400x300")
        dialog.transient(self)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Block name
        ttk.Label(frame, text="Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        name_var = tk.StringVar(value=block.name)
        ttk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky=tk.W+tk.E, pady=5)
        
        # Block properties based on type
        row = 1
        property_vars = {}
        
        if block.block_type == "input_value":
            ttk.Label(frame, text="Default Value:").grid(row=row, column=0, sticky=tk.W, pady=5)
            default_var = tk.StringVar(value=block.properties.get("default_value", "0"))
            ttk.Entry(frame, textvariable=default_var).grid(row=row, column=1, sticky=tk.W+tk.E, pady=5)
            property_vars["default_value"] = default_var
            row += 1
            
        elif block.block_type == "operation":
            ttk.Label(frame, text="Operation:").grid(row=row, column=0, sticky=tk.W, pady=5)
            op_var = tk.StringVar(value=block.properties.get("operation", "+"))
            ttk.Combobox(frame, textvariable=op_var, values=["+", "-", "*", "/", "%"]).grid(
                row=row, column=1, sticky=tk.W+tk.E, pady=5)
            property_vars["operation"] = op_var
            row += 1
            
        elif block.block_type == "function":
            ttk.Label(frame, text="Function Name:").grid(row=row, column=0, sticky=tk.W, pady=5)
            func_name_var = tk.StringVar(value=block.properties.get("function_name", "my_function"))
            ttk.Entry(frame, textvariable=func_name_var).grid(row=row, column=1, sticky=tk.W+tk.E, pady=5)
            property_vars["function_name"] = func_name_var
            row += 1
        
        # Ports management
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=10)
        row += 1
        
        # Input ports
        ttk.Label(frame, text="Input Ports:").grid(row=row, column=0, sticky=tk.W, pady=5)
        row += 1
        
        for i, port in enumerate(block.inputs):
            ttk.Label(frame, text=f"{port.name} ({port.data_type})").grid(
                row=row+i, column=0, columnspan=2, sticky=tk.W, padx=20)
        
        row += len(block.inputs)
        ttk.Button(frame, text="Add Input Port", 
                   command=lambda: self.add_port_dialog(block, True)).grid(
            row=row, column=0, columnspan=2, pady=5)
        row += 1
        
        # Output ports
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=10)
        row += 1
        
        ttk.Label(frame, text="Output Ports:").grid(row=row, column=0, sticky=tk.W, pady=5)
        row += 1
        
        for i, port in enumerate(block.outputs):
            ttk.Label(frame, text=f"{port.name} ({port.data_type})").grid(
                row=row+i, column=0, columnspan=2, sticky=tk.W, padx=20)
        
        row += len(block.outputs)
        ttk.Button(frame, text="Add Output Port", 
                   command=lambda: self.add_port_dialog(block, False)).grid(
            row=row, column=0, columnspan=2, pady=5)
        row += 1
        
        # Save button
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=10)
        row += 1
        
        def save_changes():
            block.name = name_var.get()
            
            # Update properties
            for key, var in property_vars.items():
                block.properties[key] = var.get()
            
            dialog.destroy()
            self.redraw_canvas()
        
        ttk.Button(frame, text="Save Changes", command=save_changes).grid(
            row=row, column=0, columnspan=2, pady=10)
    
    def add_port_dialog(self, block: Block, is_input: bool):
        """Show a dialog to add a new port to a block."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Add {'Input' if is_input else 'Output'} Port")
        dialog.geometry("300x150")
        dialog.transient(self)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Port Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=name_var).grid(row=0, column=1, sticky=tk.W+tk.E, pady=5)
        
        ttk.Label(frame, text="Data Type:").grid(row=1, column=0, sticky=tk.W, pady=5)
        type_var = tk.StringVar(value="any")
        ttk.Combobox(frame, textvariable=type_var, 
                    values=["any", "number", "string", "boolean", "array", "object"]).grid(
            row=1, column=1, sticky=tk.W+tk.E, pady=5)
        
        def add_port():
            name = name_var.get()
            data_type = type_var.get()
            
            if not name:
                messagebox.showerror("Error", "Port name cannot be empty")
                return
            
            if is_input:
                block.add_input(name, data_type)
            else:
                block.add_output(name, data_type)
            
            dialog.destroy()
            self.redraw_canvas()
        
        ttk.Button(frame, text="Add Port", command=add_port).grid(
            row=2, column=0, columnspan=2, pady=10)
    
    def show_context_menu(self, event):
        """Show the context menu."""
        items = self.canvas.find_overlapping(event.x-1, event.y-1, event.x+1, event.y+1)
        for item in items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("block:"):
                    block_id = tag.split(":", 1)[1]
                    self.select_block(block_id)
                    self.context_menu.post(event.x_root, event.y_root)
                    return
    
    def new_project(self):
        """Create a new project."""
        if messagebox.askyesno("New Project", "Create a new project? Any unsaved changes will be lost."):
            self.canvas_model = BlockCanvas()
            self.selected_block = None
            self.redraw_canvas()
    
    def save_project(self):
        """Save the current project."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".vbe",
            filetypes=[("Visual Block Editor files", "*.vbe"), ("All files", "*.*")]
        )
        if filename:
            self.canvas_model.save_to_json(filename)
            messagebox.showinfo("Save Project", f"Project saved to {filename}")
    
    def open_project(self):
        """Open a saved project."""
        filename = filedialog.askopenfilename(
            defaultextension=".vbe",
            filetypes=[("Visual Block Editor files", "*.vbe"), ("All files", "*.*")]
        )
        if filename:
            try:
                self.canvas_model = BlockCanvas.load_from_json(filename)
                self.selected_block = None
                self.redraw_canvas()
                messagebox.showinfo("Open Project", f"Project loaded from {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open project: {e}")
    
    def show_generated_code(self):
        """Show the generated code in a dialog."""
        code = self.canvas_model.generate_code()
        
        dialog = tk.Toplevel(self)
        dialog.title("Generated Code")
        dialog.geometry("600x400")
        
        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a text widget with scrollbars
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar_y = ttk.Scrollbar(text_frame)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        scrollbar_x = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        text_widget = tk.Text(text_frame, wrap=tk.NONE, font=("Courier", 10))
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar_y.config(command=text_widget.yview)
        scrollbar_x.config(command=text_widget.xview)
        text_widget.config(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        # Insert the code
        text_widget.insert(tk.END, code)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        def copy_to_clipboard():
            self.clipboard_clear()
            self.clipboard_append(code)
            messagebox.showinfo("Copied", "Code copied to clipboard")
        
        def save_to_file():
            filename = filedialog.asksaveasfilename(
                defaultextension=".py",
                filetypes=[("Python files", "*.py"), ("All files", "*.*")]
            )
            if filename:
                with open(filename, 'w') as f:
                    f.write(code)
                messagebox.showinfo("Save Code", f"Code saved to {filename}")
        
        ttk.Button(button_frame, text="Copy to Clipboard", command=copy_to_clipboard).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Save to File", command=save_to_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)


if __name__ == "__main__":
    app = VisualBlockEditor()
    app.mainloop()