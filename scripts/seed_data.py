import pandas as pd
from pathlib import Path
import random
import json

random.seed(42)

DATA = Path("data")
DATA.mkdir(exist_ok=True)

# Assets grid - generate with proper pixel coordinates (0-1600, 0-900)
rows = list("ABCDEF")
racks = list(range(1, 9))  # 8 racks per row for manageable size
assets = []
coords = {}

# Define 3 zones with different x ranges
zones = [
    {"name": "zone_a", "x_range": (100, 500), "y_base": 100},
    {"name": "zone_b", "x_range": (600, 1000), "y_base": 100},
    {"name": "zone_c", "x_range": (1100, 1500), "y_base": 100},
]

for row_idx, row in enumerate(rows):
    zone = zones[row_idx % len(zones)]
    x_start, x_end = zone["x_range"]
    y_base = zone["y_base"] + (row_idx // len(zones)) * 200

    for rack_idx, rack in enumerate(racks):
        asset_id = f"{row}-{rack:02d}"
        # Distribute racks evenly within zone
        x = x_start + (rack_idx * (x_end - x_start) / (len(racks) - 1)) if len(racks) > 1 else (x_start + x_end) / 2
        y = y_base + random.randint(-10, 10)  # Small random offset

        asset_data = {
            "asset_id": asset_id,
            "row": row,
            "rack": rack,
            "u": random.randint(1, 42),
            "x": int(x),
            "y": int(y),
            "zone": zone["name"],
            "type": "server",
        }
        assets.append(asset_data)
        coords[asset_id] = {"x": int(x), "y": int(y)}

pd.DataFrame(assets).to_csv(DATA / "assets.csv", index=False)

# Create inventory.csv (same as assets but with required columns)
inventory_df = pd.DataFrame(assets)
inventory_df.to_csv(DATA / "inventory.csv", index=False)

# Create coords.json
(DATA / "coords.json").write_text(json.dumps(coords, indent=2))

# Technicians
techs = []
names = ["Ava", "Ben", "Chen", "Dia", "Eli", "Farah", "Gus", "Hana", "Ivan", "Jia"]
teams = ["Alpha"] * 4 + ["Beta"] * 6
for i, n in enumerate(names):
    techs.append(
        {
            "tech_id": f"T{i+1}",
            "name": n,
            "team": teams[i],
            "skill_level": random.randint(1, 3),
            "current_row": random.choice(rows),
            "current_rack": random.choice(racks),
        }
    )

pd.DataFrame(techs).to_csv(DATA / "technicians.csv", index=False)

# Tickets - include x,y coordinates from asset
types = [
    "replace_sfp",
    "reseat_blade",
    "swap_psu",
    "recable_port",
    "install_server",
    "audit_label",
]
priorities = ["Low", "Medium", "High", "Critical"]
tickets = []
for i in range(1, 41):
    asset_data = random.choice(assets)
    asset_id = asset_data["asset_id"]
    ttype = random.choice(types)
    prio = random.choices(priorities, weights=[1, 2, 3, 1])[0]
    tickets.append(
        {
            "ticket_id": f"TICK-{i}",
            "summary": f"{ttype} on {asset_id}",
            "description": f"Do {ttype} for {asset_id}",
            "asset_id": asset_id,
            "type": ttype,
            "priority": prio,
            "impact": random.randint(1, 3),
            "deadline": "2025-12-01",
            "status": random.choice(["queued", "in-progress", "done"]),
            "created_by": "engineer@demo",
            "assigned_to": random.choice(names),
            "estimated_minutes": random.choice([15, 30, 45, 60]),
            "requires_tools": "basic",
            "change_window_start": "2025-11-08T00:00:00",
            "change_window_end": "2025-12-31T23:59:59",
            "x": asset_data["x"],
            "y": asset_data["y"],
            "row": asset_data["row"],
            "rack": asset_data["rack"],
            "u": asset_data["u"],
        }
    )

pd.DataFrame(tickets).to_csv(DATA / "tickets.csv", index=False)

# Demo Jira store
(DATA / "demo_jira.json").write_text('{"issues": []}')

# Create placeholder floorplan.png (1600x900) - simple colored rectangle
try:
    from PIL import Image

    img = Image.new("RGB", (1600, 900), color=(240, 240, 245))
    # Add some grid lines for visual reference
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    # Draw grid
    for x in range(0, 1600, 100):
        draw.line([(x, 0), (x, 900)], fill=(220, 220, 220), width=1)
    for y in range(0, 900, 100):
        draw.line([(0, y), (1600, y)], fill=(220, 220, 220), width=1)
    # Add title
    try:
        from PIL import ImageFont

        font = ImageFont.load_default()
        draw.text((50, 50), "Data Hall Floorplan (1600x900)", fill=(200, 200, 200))
    except:
        pass
    img.save(DATA / "floorplan.png")
    print("Created floorplan.png")
except ImportError:
    # Fallback: create minimal PNG using base64
    import base64

    # 1x1 transparent PNG
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    (DATA / "floorplan.png").write_bytes(png_data)
    print("Created minimal floorplan.png (install Pillow for better image)")

print("Seed complete.")

