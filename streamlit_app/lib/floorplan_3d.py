"""
3D Interactive Floorplan Component
Creates an isometric 3D visualization of the data center similar to architectural floorplans.
"""

import plotly.graph_objects as go
import pandas as pd
import numpy as np
import re
from typing import Optional, Dict, List, Tuple


def create_3d_floorplan(
    tickets_df: Optional[pd.DataFrame] = None,
    inventory_df: Optional[pd.DataFrame] = None,
    show_racks: bool = True,
    show_tickets: bool = True,
    show_equipment: bool = True,
) -> go.Figure:
    """
    Create a 3D interactive floorplan of the data center.
    
    Args:
        tickets_df: DataFrame with ticket data (x, y coordinates)
        inventory_df: DataFrame with asset/inventory data
        show_racks: Whether to show server racks
        show_tickets: Whether to show ticket locations
        show_equipment: Whether to show equipment (AC, UPS, generators)
        
    Returns:
        Plotly 3D figure
    """
    fig = go.Figure()
    
    # Data center dimensions (based on typical layout)
    # X: 0-1600 (width), Y: 0-900 (depth), Z: 0-300 (height)
    # Scaled down 20x: X: 0-80, Y: 0-55 (45 + 10 for 200ft increase), Z: 0-15
    width, depth, height = 80, 55, 15
    
    # Define room boundaries (based on typical data center layout)
    # All dimensions scaled down 20x
    # Depth increased by 200ft (10 in scaled coordinates) towards +depth axis
    rooms = {
        "High-Heat Server Room (Top)": {
            "bounds": [(0, 30), (0, 55)],  # Top-left (was 0-600, 0-900, now +10 depth)
            "z": 0,
            "height": height,
            "color": "rgba(200, 200, 200, 0.3)",
        },
        "High-Heat Server Room (Bottom)": {
            "bounds": [(0, 20), (0, 40)],  # Bottom-left (was 0-400, 0-600, now +10 depth)
            "z": 0,
            "height": height,
            "color": "rgba(200, 200, 200, 0.3)",
        },
        "Colocation Room": {
            "bounds": [(50, 80), (0, 55)],  # Right side (was 1000-1600, 0-900, now +10 depth)
            "z": 0,
            "height": height,
            "color": "rgba(180, 180, 200, 0.3)",
        },
        "NOC Room": {
            "bounds": [(20, 40), (0, 25)],  # Bottom-center (was 400-800, 0-300, now +10 depth)
            "z": 0,
            "height": 10,  # Lower ceiling (was 200)
            "color": "rgba(150, 200, 150, 0.3)",
        },
        "Staging Room": {
            "bounds": [(40, 50), (0, 25)],  # Bottom-right (was 800-1000, 0-300, now +10 depth)
            "z": 0,
            "height": 10,  # (was 200)
            "color": "rgba(200, 200, 150, 0.3)",
        },
    }
    
    # Calculate aligned rack positions and adjust room boundaries
    # Initialize these outside the conditional so they're accessible later
    aligned_rack_positions = []
    row_y_centers = {}
    rack_width = 57.0  # Will be calculated
    padding = 0
    
    if inventory_df is not None and show_racks:
        # Group racks by row to calculate spacing and average Y position
        rack_groups = {}
        rack_y_positions = {}
        for _, row in inventory_df.iterrows():
            row_letter = row.get("row", "")
            x = row.get("x", None)
            y = row.get("y", None)
            if pd.notna(x) and pd.notna(y) and row_letter:
                if row_letter not in rack_groups:
                    rack_groups[row_letter] = []
                    rack_y_positions[row_letter] = []
                rack_groups[row_letter].append(float(x))
                rack_y_positions[row_letter].append(float(y))
        
        # Calculate average Y position for each row (for depth alignment)
        for row_letter, y_positions in rack_y_positions.items():
            row_y_centers[row_letter] = sum(y_positions) / len(y_positions)
        
        # Calculate average spacing between racks in each row (scaled down 20x)
        avg_spacing = 57.0 / 20.0  # Default spacing
        if rack_groups:
            all_spacings = []
            for row_letter, x_positions in rack_groups.items():
                if len(x_positions) > 1:
                    x_positions = sorted(x_positions)
                    spacings = [(x_positions[i+1] - x_positions[i]) / 20.0 for i in range(len(x_positions)-1)]
                    all_spacings.extend(spacings)
            if all_spacings:
                avg_spacing = sum(all_spacings) / len(all_spacings)
        
        rack_width = avg_spacing
        padding = rack_width * 0.5  # Half rack width on each side
        
        # Calculate aligned positions (scaled down 20x)
        for _, row in inventory_df.iterrows():
            x = row.get("x", None)
            y = row.get("y", None)
            row_letter = row.get("row", "")
            if pd.notna(x) and pd.notna(y) and row_letter:
                x_center = float(x) / 20.0  # Scale down 20x
                y_center = (row_y_centers.get(row_letter, float(y))) / 20.0  # Scale down 20x
                aligned_rack_positions.append((x_center, y_center))
        
        # Adjust room boundaries to encompass all racks with padding (only expand, never shrink)
        if aligned_rack_positions:
            # For each room, find racks that are within or near it and expand boundaries
            for room_name, room_data in rooms.items():
                x_min, x_max = room_data["bounds"][0]
                y_min, y_max = room_data["bounds"][1]
                
                # Find racks that are within this room's current boundaries or close to them
                room_racks = []
                for x, y in aligned_rack_positions:
                    # Check if rack is within room or within padding distance
                    in_x_range = x_min - padding <= x <= x_max + padding
                    in_y_range = y_min - padding <= y <= y_max + padding
                    if in_x_range and in_y_range:
                        room_racks.append((x, y))
                
                # If there are racks in/near this room, expand boundaries to include them
                if room_racks:
                    rack_x_coords = [pos[0] for pos in room_racks]
                    rack_y_coords = [pos[1] for pos in room_racks]
                    rack_min_x = min(rack_x_coords)
                    rack_max_x = max(rack_x_coords)
                    rack_min_y = min(rack_y_coords)
                    rack_max_y = max(rack_y_coords)
                    
                    # Expand with padding
                    expanded_min_x = max(0, rack_min_x - padding)
                    expanded_max_x = min(width, rack_max_x + padding)
                    expanded_min_y = max(0, rack_min_y - padding)
                    expanded_max_y = min(depth, rack_max_y + padding)
                    
                    # Only expand boundaries, never shrink
                    new_x_min = min(x_min, expanded_min_x)
                    new_x_max = max(x_max, expanded_max_x)
                    new_y_min = min(y_min, expanded_min_y)
                    new_y_max = max(y_max, expanded_max_y)
                    
                    room_data["bounds"] = [
                        (new_x_min, new_x_max),
                        (new_y_min, new_y_max)
                    ]
    
    # Draw room floors and walls
    for room_name, room_data in rooms.items():
        x_min, x_max = room_data["bounds"][0]
        y_min, y_max = room_data["bounds"][1]
        z = room_data["z"]
        room_height = room_data["height"]
        
        # Room floor outline (white on black background for visibility - increased opacity and thickness)
        fig.add_trace(go.Scatter3d(
            x=[x_min, x_max, x_max, x_min, x_min],
            y=[y_min, y_min, y_max, y_max, y_min],
            z=[z, z, z, z, z],
            mode='lines',
            line=dict(color='rgba(255, 255, 255, 1.0)', width=6),  # Increased opacity and thickness
            name=room_name,
            showlegend=True,
            hovertemplate=f"<b style='color:white'>{room_name}</b><br>Size: {x_max-x_min:.0f} x {y_max-y_min:.0f} ft<extra></extra>",
        ))
        
        # Room walls (vertical lines at corners - white, increased opacity and thickness)
        wall_height = room_height
        corners = [
            (x_min, y_min), (x_max, y_min),
            (x_max, y_max), (x_min, y_max)
        ]
        for x, y in corners:
            fig.add_trace(go.Scatter3d(
                x=[x, x],
                y=[y, y],
                z=[z, z + wall_height],
                mode='lines',
                line=dict(color='rgba(255, 255, 255, 0.95)', width=4),  # Increased opacity and thickness
                showlegend=False,
                hoverinfo='skip',
            ))
        
        # Top edge of walls (white, increased opacity and thickness)
        fig.add_trace(go.Scatter3d(
            x=[x_min, x_max, x_max, x_min, x_min],
            y=[y_min, y_min, y_max, y_max, y_min],
            z=[z + wall_height, z + wall_height, z + wall_height, z + wall_height, z + wall_height],
            mode='lines',
            line=dict(color='rgba(255, 255, 255, 0.95)', width=4),  # Increased opacity and thickness
            showlegend=False,
            hoverinfo='skip',
        ))
    
    # Draw server racks as 3D cuboids (if inventory data available)
    if show_racks and inventory_df is not None:
        # Helper function to determine which room a rack is in and get its height
        def get_room_height(x, y):
            """Determine which room a point is in and return its height."""
            for room_name, room_data in rooms.items():
                x_min, x_max = room_data["bounds"][0]
                y_min, y_max = room_data["bounds"][1]
                if x_min <= x <= x_max and y_min <= y <= y_max:
                    return room_data["height"]
            return height  # Default to full height if not in any room
        
        # Use pre-calculated rack_width from room boundary adjustment
        # Rack dimensions: width = spacing so racks touch, depth = spacing/2 for proportional look
        rack_depth = rack_width * 0.4  # Proportional depth
        
        rack_data = []
        for _, row in inventory_df.iterrows():
            x = row.get("x", None)
            y = row.get("y", None)
            row_letter = row.get("row", "")
            rack_num = row.get("rack", "")
            asset_id = row.get("asset_id", "")
            
            if pd.notna(x) and pd.notna(y):
                x_center = float(x) / 20.0  # Scale down 20x
                # Align Y to the average Y position for this row (depth alignment)
                y_center = (row_y_centers.get(row_letter, float(y))) / 20.0  # Scale down 20x
                # Rack height is 70% of the room it's in
                room_height = get_room_height(x_center, y_center)
                rack_height = room_height * 0.7
                
                z_bottom = 0
                z_top = rack_height
                
                # Create box vertices (8 corners of a cuboid)
                vertices = [
                    [x_center - rack_width/2, y_center - rack_depth/2, z_bottom],  # 0: bottom-front-left
                    [x_center + rack_width/2, y_center - rack_depth/2, z_bottom],  # 1: bottom-front-right
                    [x_center + rack_width/2, y_center + rack_depth/2, z_bottom],  # 2: bottom-back-right
                    [x_center - rack_width/2, y_center + rack_depth/2, z_bottom],  # 3: bottom-back-left
                    [x_center - rack_width/2, y_center - rack_depth/2, z_top],     # 4: top-front-left
                    [x_center + rack_width/2, y_center - rack_depth/2, z_top],     # 5: top-front-right
                    [x_center + rack_width/2, y_center + rack_depth/2, z_top],     # 6: top-back-right
                    [x_center - rack_width/2, y_center + rack_depth/2, z_top],     # 7: top-back-left
                ]
                
                # Define faces (6 faces of a box: bottom, top, front, back, left, right)
                # Each face is defined by 4 vertices forming a rectangle
                faces = [
                    [0, 1, 2, 3],  # bottom face
                    [4, 7, 6, 5],  # top face
                    [0, 4, 5, 1],  # front face
                    [2, 6, 7, 3],  # back face
                    [0, 3, 7, 4],  # left face
                    [1, 5, 6, 2],  # right face
                ]
                
                # Flatten vertices for Mesh3d
                x_verts = [v[0] for v in vertices]
                y_verts = [v[1] for v in vertices]
                z_verts = [v[2] for v in vertices]
                
                # Flatten faces (each quad face needs 2 triangles: 0-1-2, 0-2-3)
                i_vals = []
                j_vals = []
                k_vals = []
                for face in faces:
                    # First triangle: 0-1-2
                    i_vals.append(face[0])
                    j_vals.append(face[1])
                    k_vals.append(face[2])
                    # Second triangle: 0-2-3
                    i_vals.append(face[0])
                    j_vals.append(face[2])
                    k_vals.append(face[3])
                
                label = f"{row_letter}-{rack_num}" if row_letter and rack_num else asset_id
                
                # Add 3D cuboid using Mesh3d (filled)
                fig.add_trace(go.Mesh3d(
                    x=x_verts,
                    y=y_verts,
                    z=z_verts,
                    i=i_vals,
                    j=j_vals,
                    k=k_vals,
                    color='rgba(0, 255, 255, 0.7)',  # Light blue/cyan for server racks
                    flatshading=True,
                    name="Server Racks",
                    showlegend=(len(rack_data) == 0),  # Only show in legend once
                    hovertemplate=f"<b style='color:white'>Rack {label}</b><br>X: {x_center:.0f}<br>Y: {y_center:.0f}<br>Height: {rack_height:.0f}ft<extra></extra>",
                ))
                
                # Add wireframe edges for the cuboid (thick, visible edges - all 12 edges)
                # Create all edges as a single connected wireframe
                # Bottom face: 4 edges
                bottom_edges_x = [vertices[0][0], vertices[1][0], vertices[2][0], vertices[3][0], vertices[0][0]]
                bottom_edges_y = [vertices[0][1], vertices[1][1], vertices[2][1], vertices[3][1], vertices[0][1]]
                bottom_edges_z = [vertices[0][2], vertices[1][2], vertices[2][2], vertices[3][2], vertices[0][2]]
                fig.add_trace(go.Scatter3d(
                    x=bottom_edges_x,
                    y=bottom_edges_y,
                    z=bottom_edges_z,
                    mode='lines',
                    line=dict(color='rgba(0, 255, 255, 1.0)', width=5),  # Thicker, more visible
                    showlegend=False,
                    hoverinfo='skip',
                ))
                # Top face: 4 edges
                top_edges_x = [vertices[4][0], vertices[5][0], vertices[6][0], vertices[7][0], vertices[4][0]]
                top_edges_y = [vertices[4][1], vertices[5][1], vertices[6][1], vertices[7][1], vertices[4][1]]
                top_edges_z = [vertices[4][2], vertices[5][2], vertices[6][2], vertices[7][2], vertices[4][2]]
                fig.add_trace(go.Scatter3d(
                    x=top_edges_x,
                    y=top_edges_y,
                    z=top_edges_z,
                    mode='lines',
                    line=dict(color='rgba(0, 255, 255, 1.0)', width=5),  # Thicker, more visible
                    showlegend=False,
                    hoverinfo='skip',
                ))
                # Vertical edges: 4 edges connecting bottom corners to top corners
                for i in range(4):
                    fig.add_trace(go.Scatter3d(
                        x=[vertices[i][0], vertices[i+4][0]],
                        y=[vertices[i][1], vertices[i+4][1]],
                        z=[vertices[i][2], vertices[i+4][2]],
                        mode='lines',
                        line=dict(color='rgba(0, 255, 255, 1.0)', width=5),  # Thicker, more visible
                        showlegend=False,
                        hoverinfo='skip',
                    ))
                
                rack_data.append({
                    "x": x_center,
                    "y": y_center,
                    "label": label,
                })
    
    # Draw tickets (if available)
    if show_tickets and tickets_df is not None:
        # Filter tickets with valid coordinates AND within room boundaries
        valid_tickets = tickets_df[
            tickets_df["x"].notna() & tickets_df["y"].notna()
        ].copy()
        
        # Filter to only show tickets within data hall rooms
        def is_in_room(x, y):
            """Check if a point is within any defined room."""
            for room_name, room_data in rooms.items():
                x_min, x_max = room_data["bounds"][0]
                y_min, y_max = room_data["bounds"][1]
                if x_min <= x <= x_max and y_min <= y <= y_max:
                    return True
            return False
        
        if not valid_tickets.empty:
            # Scale ticket positions down 20x
            valid_tickets = valid_tickets.copy()
            valid_tickets["x"] = valid_tickets["x"] / 20.0
            valid_tickets["y"] = valid_tickets["y"] / 20.0
            # Filter tickets to only those within rooms
            valid_tickets = valid_tickets[
                valid_tickets.apply(lambda row: is_in_room(float(row["x"]), float(row["y"])), axis=1)
            ]
        
        if not valid_tickets.empty:
            # Group by priority for color coding
            priority_colors = {
                "Critical": "rgba(255, 0, 0, 0.9)",
                "High": "rgba(255, 165, 0, 0.9)",
                "Medium": "rgba(255, 255, 0, 0.9)",
                "Low": "rgba(0, 255, 0, 0.9)",
            }
            
            for priority, color in priority_colors.items():
                priority_tickets = valid_tickets[valid_tickets["priority"] == priority]
                if not priority_tickets.empty:
                    fig.add_trace(go.Scatter3d(
                        x=priority_tickets["x"],
                        y=priority_tickets["y"],
                        z=[2.5] * len(priority_tickets),  # Float above floor (50/20 = 2.5)
                        mode='markers',
                        marker=dict(
                            size=10,
                            color=color,
                            symbol='circle',
                            line=dict(width=2, color='white'),
                        ),
                        name=f"Tickets ({priority})",
                        text=priority_tickets["ticket_id"],
                        hovertemplate="<b>%{text}</b><br>Priority: " + priority + "<extra></extra>",
                    ))
    
    # Draw equipment (AC units, UPS, generators)
    if show_equipment:
        # AC units along walls (raw positions, scaled down 20x)
        ac_positions_raw = [
            (2.5, 35, 5), (7.5, 35, 5), (12.5, 35, 5),  # (was 50, 700, 100), (150, 700, 100), (250, 700, 100)
            (2.5, 25, 5), (7.5, 25, 5), (12.5, 25, 5),  # (was 50, 500, 100), (150, 500, 100), (250, 500, 100)
            (67.5, 22.5, 5), (72.5, 22.5, 5),  # (was 1350, 450, 100), (1450, 450, 100)
        ]
        
        # Group AC units by approximate Y position (rows) for depth alignment
        ac_rows = {}
        for x, y, z_base in ac_positions_raw:
            # Round Y to nearest 2.5 to group into rows (was 50, now 50/20 = 2.5)
            y_row = round(y / 2.5) * 2.5
            if y_row not in ac_rows:
                ac_rows[y_row] = []
            ac_rows[y_row].append((x, y, z_base))
        
        # Calculate average Y for each AC row and align them
        ac_positions = []
        for y_row, positions in ac_rows.items():
            avg_y = sum([pos[1] for pos in positions]) / len(positions)
            for x, _, z_base in positions:
                ac_positions.append((x, avg_y, z_base))
        
        # Calculate AC unit spacing to make them touch
        # AC units are positioned along walls, calculate spacing from positions
        ac_x_positions = sorted([pos[0] for pos in ac_positions])
        ac_spacing = 5.0  # Default spacing (was 100, now 100/20 = 5)
        if len(ac_x_positions) > 1:
            ac_spacings = [ac_x_positions[i+1] - ac_x_positions[i] for i in range(len(ac_x_positions)-1)]
            # Filter out very large gaps (different walls) - scaled down 20x (was 200, now 10)
            ac_spacings = [s for s in ac_spacings if s < 10]  # Only consider nearby AC units
            if ac_spacings:
                ac_spacing = sum(ac_spacings) / len(ac_spacings)
        
        for x, y, z_base in ac_positions:
            # Determine which room the AC unit is in to get height
            ac_room_height = height  # Default
            for room_name, room_data in rooms.items():
                x_min, x_max = room_data["bounds"][0]
                y_min, y_max = room_data["bounds"][1]
                if x_min <= x <= x_max and y_min <= y <= y_max:
                    ac_room_height = room_data["height"]
                    break
            
            # AC unit dimensions: width = spacing so they touch, depth proportional
            ac_width = ac_spacing
            ac_depth = ac_spacing * 0.4
            ac_height = ac_room_height * 0.7
            ac_z_bottom = 0  # Start from floor
            ac_z_top = ac_z_bottom + ac_height
            
            ac_vertices = [
                [x - ac_width/2, y - ac_depth/2, ac_z_bottom],  # 0: bottom-front-left
                [x + ac_width/2, y - ac_depth/2, ac_z_bottom],  # 1: bottom-front-right
                [x + ac_width/2, y + ac_depth/2, ac_z_bottom],  # 2: bottom-back-right
                [x - ac_width/2, y + ac_depth/2, ac_z_bottom],  # 3: bottom-back-left
                [x - ac_width/2, y - ac_depth/2, ac_z_top],  # 4: top-front-left
                [x + ac_width/2, y - ac_depth/2, ac_z_top],  # 5: top-front-right
                [x + ac_width/2, y + ac_depth/2, ac_z_top],  # 6: top-back-right
                [x - ac_width/2, y + ac_depth/2, ac_z_top],  # 7: top-back-left
            ]
            
            x_ac_verts = [v[0] for v in ac_vertices]
            y_ac_verts = [v[1] for v in ac_vertices]
            z_ac_verts = [v[2] for v in ac_vertices]
            
            # Faces for AC unit box
            ac_faces = [
                [0, 1, 2, 3],  # bottom
                [4, 7, 6, 5],  # top
                [0, 4, 5, 1],  # front
                [2, 6, 7, 3],  # back
                [0, 3, 7, 4],  # left
                [1, 5, 6, 2],  # right
            ]
            
            # Flatten faces for Mesh3d (each quad face needs 2 triangles)
            ac_i = []
            ac_j = []
            ac_k = []
            for face in ac_faces:
                # First triangle: 0-1-2
                ac_i.append(face[0])
                ac_j.append(face[1])
                ac_k.append(face[2])
                # Second triangle: 0-2-3
                ac_i.append(face[0])
                ac_j.append(face[2])
                ac_k.append(face[3])
            
            # Add filled AC unit cuboid
            fig.add_trace(go.Mesh3d(
                x=x_ac_verts,
                y=y_ac_verts,
                z=z_ac_verts,
                i=ac_i,
                j=ac_j,
                k=ac_k,
                color='rgba(57, 255, 20, 0.7)',  # Neon green for AC units
                flatshading=True,
                name="AC Units",
                showlegend=(ac_positions.index((x, y, z_base)) == 0),  # Only show in legend once
                hovertemplate=f"<b style='color:white'>AC Unit</b><br>X: {x:.0f}<br>Y: {y:.0f}<br>Height: {ac_height:.0f}ft<extra></extra>",
            ))
            
            # Add wireframe edges for AC unit (thick, visible edges - all 12 edges)
            # Bottom face: 4 edges
            ac_bottom_x = [ac_vertices[0][0], ac_vertices[1][0], ac_vertices[2][0], ac_vertices[3][0], ac_vertices[0][0]]
            ac_bottom_y = [ac_vertices[0][1], ac_vertices[1][1], ac_vertices[2][1], ac_vertices[3][1], ac_vertices[0][1]]
            ac_bottom_z = [ac_vertices[0][2], ac_vertices[1][2], ac_vertices[2][2], ac_vertices[3][2], ac_vertices[0][2]]
            fig.add_trace(go.Scatter3d(
                x=ac_bottom_x,
                y=ac_bottom_y,
                z=ac_bottom_z,
                mode='lines',
                line=dict(color='rgba(57, 255, 20, 1.0)', width=5),  # Thicker, more visible neon green
                showlegend=False,
                hoverinfo='skip',
            ))
            # Top face: 4 edges
            ac_top_x = [ac_vertices[4][0], ac_vertices[5][0], ac_vertices[6][0], ac_vertices[7][0], ac_vertices[4][0]]
            ac_top_y = [ac_vertices[4][1], ac_vertices[5][1], ac_vertices[6][1], ac_vertices[7][1], ac_vertices[4][1]]
            ac_top_z = [ac_vertices[4][2], ac_vertices[5][2], ac_vertices[6][2], ac_vertices[7][2], ac_vertices[4][2]]
            fig.add_trace(go.Scatter3d(
                x=ac_top_x,
                y=ac_top_y,
                z=ac_top_z,
                mode='lines',
                line=dict(color='rgba(57, 255, 20, 1.0)', width=5),  # Thicker, more visible neon green
                showlegend=False,
                hoverinfo='skip',
            ))
            # Vertical edges: 4 edges connecting bottom to top
            for i in range(4):
                fig.add_trace(go.Scatter3d(
                    x=[ac_vertices[i][0], ac_vertices[i+4][0]],
                    y=[ac_vertices[i][1], ac_vertices[i+4][1]],
                    z=[ac_vertices[i][2], ac_vertices[i+4][2]],
                    mode='lines',
                    line=dict(color='rgba(57, 255, 20, 1.0)', width=5),  # Thicker, more visible neon green
                    showlegend=False,
                    hoverinfo='skip',
                ))
        
        # Helper function to create a cuboid with wireframe
        def create_cuboid(x, y, z_bottom, width, depth, height, color, name, show_legend=True):
            """Create a 3D cuboid with wireframe edges."""
            # Create box vertices (8 corners of a cuboid)
            vertices = [
                [x - width/2, y - depth/2, z_bottom],  # 0: bottom-front-left
                [x + width/2, y - depth/2, z_bottom],  # 1: bottom-front-right
                [x + width/2, y + depth/2, z_bottom],  # 2: bottom-back-right
                [x - width/2, y + depth/2, z_bottom],  # 3: bottom-back-left
                [x - width/2, y - depth/2, z_bottom + height],  # 4: top-front-left
                [x + width/2, y - depth/2, z_bottom + height],  # 5: top-front-right
                [x + width/2, y + depth/2, z_bottom + height],  # 6: top-back-right
                [x - width/2, y + depth/2, z_bottom + height],  # 7: top-back-left
            ]
            
            x_verts = [v[0] for v in vertices]
            y_verts = [v[1] for v in vertices]
            z_verts = [v[2] for v in vertices]
            
            # Define faces (6 faces of a box)
            faces = [
                [0, 1, 2, 3],  # bottom
                [4, 7, 6, 5],  # top
                [0, 4, 5, 1],  # front
                [2, 6, 7, 3],  # back
                [0, 3, 7, 4],  # left
                [1, 5, 6, 2],  # right
            ]
            
            # Flatten faces for Mesh3d (each quad face needs 2 triangles)
            i_vals = []
            j_vals = []
            k_vals = []
            for face in faces:
                # First triangle: 0-1-2
                i_vals.append(face[0])
                j_vals.append(face[1])
                k_vals.append(face[2])
                # Second triangle: 0-2-3
                i_vals.append(face[0])
                j_vals.append(face[2])
                k_vals.append(face[3])
            
            # Extract edge color (full opacity for wireframe)
            # Convert rgba color to full opacity for edges
            edge_color = re.sub(r'rgba\(([^,]+),([^,]+),([^,]+),([^)]+)\)', 
                               r'rgba(\1,\2,\3,1.0)', color)
            
            # Add filled cuboid
            fig.add_trace(go.Mesh3d(
                x=x_verts,
                y=y_verts,
                z=z_verts,
                i=i_vals,
                j=j_vals,
                k=k_vals,
                color=color,
                flatshading=True,
                name=name,
                showlegend=show_legend,
                hovertemplate=f"<b style='color:white'>{name}</b><br>X: {x:.0f}<br>Y: {y:.0f}<br>Height: {height:.0f}ft<extra></extra>",
            ))
            
            # Add wireframe edges (all 12 edges)
            # Bottom face: 4 edges
            bottom_x = [vertices[0][0], vertices[1][0], vertices[2][0], vertices[3][0], vertices[0][0]]
            bottom_y = [vertices[0][1], vertices[1][1], vertices[2][1], vertices[3][1], vertices[0][1]]
            bottom_z = [vertices[0][2], vertices[1][2], vertices[2][2], vertices[3][2], vertices[0][2]]
            fig.add_trace(go.Scatter3d(
                x=bottom_x,
                y=bottom_y,
                z=bottom_z,
                mode='lines',
                line=dict(color=edge_color, width=5),
                showlegend=False,
                hoverinfo='skip',
            ))
            # Top face: 4 edges
            top_x = [vertices[4][0], vertices[5][0], vertices[6][0], vertices[7][0], vertices[4][0]]
            top_y = [vertices[4][1], vertices[5][1], vertices[6][1], vertices[7][1], vertices[4][1]]
            top_z = [vertices[4][2], vertices[5][2], vertices[6][2], vertices[7][2], vertices[4][2]]
            fig.add_trace(go.Scatter3d(
                x=top_x,
                y=top_y,
                z=top_z,
                mode='lines',
                line=dict(color=edge_color, width=5),
                showlegend=False,
                hoverinfo='skip',
            ))
            # Vertical edges: 4 edges connecting bottom to top
            for i in range(4):
                fig.add_trace(go.Scatter3d(
                    x=[vertices[i][0], vertices[i+4][0]],
                    y=[vertices[i][1], vertices[i+4][1]],
                    z=[vertices[i][2], vertices[i+4][2]],
                    mode='lines',
                    line=dict(color=edge_color, width=5),
                    showlegend=False,
                    hoverinfo='skip',
                ))
        
        # UPS (top-left) - bright yellow (scaled down 20x)
        ups_x, ups_y = 5.0, 42.5  # (was 100, 850)
        ups_room_height = height  # Default
        for room_name, room_data in rooms.items():
            x_min, x_max = room_data["bounds"][0]
            y_min, y_max = room_data["bounds"][1]
            if x_min <= ups_x <= x_max and y_min <= ups_y <= y_max:
                ups_room_height = room_data["height"]
                break
        ups_width, ups_depth, ups_height = 15.0, 5.0, ups_room_height * 0.6  # (was 300, 100)
        create_cuboid(ups_x, ups_y, 0, ups_width, ups_depth, ups_height, 
                     'rgba(255, 255, 0, 0.8)', "UPS", show_legend=True)
        
        # Generators (right side) - light pink (scaled down 20x)
        generator_positions = [(77.5, 10), (77.5, 20)]  # (was 1550, 200), (1550, 400)
        for idx, (gen_x, gen_y) in enumerate(generator_positions):
            gen_room_height = height  # Default
            for room_name, room_data in rooms.items():
                x_min, x_max = room_data["bounds"][0]
                y_min, y_max = room_data["bounds"][1]
                if x_min <= gen_x <= x_max and y_min <= gen_y <= y_max:
                    gen_room_height = room_data["height"]
                    break
            gen_width, gen_depth, gen_height = 2.5, 5.0, gen_room_height * 0.6  # (was 50, 100)
            create_cuboid(gen_x, gen_y, 0, gen_width, gen_depth, gen_height,
                         'rgba(255, 182, 193, 0.8)', "Generators", show_legend=(idx == 0))
        
        # NOC start point (top-right corner) - light brown (wooden door look)
        # Dimensions: width from 1500 to 1600 (100 ft wide, centered at 1550) -> 75 to 80 (5 ft wide, centered at 77.5)
        #            depth from 850 to 900 (50 ft deep, centered at 875) -> 42.5 to 45 (2.5 ft deep, centered at 43.75)
        #            Moved 200ft (10 in scaled) along depth axis (Y) to the right/deeper
        noc_x, noc_y = 77.5, 53.75  # Center of the NOC area (scaled down 20x, moved +10 along Y axis)
        noc_room_height = height  # Default
        for room_name, room_data in rooms.items():
            x_min, x_max = room_data["bounds"][0]
            y_min, y_max = room_data["bounds"][1]
            if x_min <= noc_x <= x_max and y_min <= noc_y <= y_max:
                noc_room_height = room_data["height"]
                break
        # NOC dimensions: width = 5 ft (75 to 80), depth = 2.5 ft (42.5 to 45) (scaled down 20x)
        noc_width, noc_depth, noc_height = 5.0, 2.5, noc_room_height * 0.8
        create_cuboid(noc_x, noc_y, 0, noc_width, noc_depth, noc_height,
                     'rgba(139, 90, 43, 0.9)', "NOC (Start)", show_legend=True)
    
    # Configure 3D layout with black background
    dark_bg = "rgb(0, 0, 0)"  # Black background
    dark_grid = "rgba(100, 100, 120, 0.3)"  # Subtle grid on dark
    
    fig.update_layout(
        scene=dict(
            xaxis=dict(
                title="Width (ft)",
                titlefont=dict(size=14, color="white"),
                range=[0, width],
                backgroundcolor=dark_bg,
                gridcolor=dark_grid,
                showbackground=True,
                showgrid=True,
            ),
            yaxis=dict(
                title="Depth (ft)",
                titlefont=dict(size=14, color="white"),
                range=[0, depth],
                backgroundcolor=dark_bg,
                gridcolor=dark_grid,
                showbackground=True,
                showgrid=True,
            ),
            zaxis=dict(
                title="Height (ft)",
                titlefont=dict(size=14, color="white"),
                range=[0, height],
                backgroundcolor=dark_bg,
                gridcolor=dark_grid,
                showbackground=True,
                showgrid=True,
            ),
            aspectmode='manual',
            aspectratio=dict(x=1, y=depth/width, z=height/width),
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.2),  # Isometric view
                center=dict(x=0, y=0, z=0),
            ),
            bgcolor=dark_bg,
        ),
        width=1200,
        height=800,
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(
            x=0.02,
            y=0.98,
            bgcolor="rgba(0, 0, 0, 0.8)",
            bordercolor="rgba(255, 255, 255, 0.3)",
            borderwidth=1,
            font=dict(size=12, color="white"),
        ),
        paper_bgcolor=dark_bg,
        plot_bgcolor=dark_bg,
    )
    
    return fig

