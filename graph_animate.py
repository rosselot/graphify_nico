"""
gen_animated_graph_svg.py

Generates a self-contained, animated SVG of a graph using SMIL animations.
No JavaScript, no external libraries at runtime — just pure SVG + CSS + SMIL.

Requires: networkx, numpy
Install:  pip install networkx numpy
"""

import math
import textwrap
import networkx as nx
import numpy as np


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SVG_WIDTH = 900
SVG_HEIGHT = 360
PADDING = 60
MASTER_PERIOD = 10.0  # seconds — everything loops over this period

# Colors
DIM_EDGE = "#2a3a3a"
DIM_NODE = "#2a3a3a"
EDGE_COLOR = "#4db18f"
NODE_COLOR = "#4db18f"
NODE_HIGHLIGHT = "#7ee8c8"
GLOW_COLOR = "#4db18f"
BG_COLOR = "#0d1117"
TEXT_COLOR = "#c9d1d9"

# Node sizing
NODE_RADIUS = 4
NODE_POP_RADIUS = 8
NODE_LIT_RADIUS = 5.6
GLOW_RADIUS = 14
EDGE_WIDTH = 2


# ---------------------------------------------------------------------------
# SMIL Helper Functions
# ---------------------------------------------------------------------------

def kt(*pairs):
    """
    Given (value, time) pairs, return (values_str, keyTimes_str) for SMIL.

    Example:
        kt((141.4, 0), (141.4, 0.3), (0, 0.35), (0, 0.96), (141.4, 1))
 -> ("141.4; 141.4; 0; 0; 141.4", "0; 0.3; 0.35; 0.96; 1")
    """
    values = [str(p[0]) for p in pairs]
    times = [str(p[1]) for p in pairs]
    return "; ".join(values), "; ".join(times)


def time_fraction(seconds):
    """Convert absolute seconds to a fraction of the master period."""
    return round(seconds / MASTER_PERIOD, 6)


# ---------------------------------------------------------------------------
# Graph Layout
# ---------------------------------------------------------------------------

def compute_layout(graph, width=SVG_WIDTH, height=SVG_HEIGHT, padding=PADDING):
    """
    Use NetworkX spring layout, then scale/shift normalized coordinates
    to fit the SVG canvas with padding.
    """
    pos = nx.spring_layout(graph, seed=42, k=1.5 / math.sqrt(len(graph)))

    # Extract all x and y values
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Avoid division by zero
    range_x = max(max_x - min_x, 1e-6)
    range_y = max(max_y - min_y, 1e-6)

    usable_w = width - 2 * padding
    usable_h = height - 2 * padding

    scaled_pos = {}
    for node, (x, y) in pos.items():
        sx = padding + (x - min_x) / range_x * usable_w
        sy = padding + (y - min_y) / range_y * usable_h
        scaled_pos[node] = (sx, sy)

    return scaled_pos


# ---------------------------------------------------------------------------
# Animation Timeline Planning
# ---------------------------------------------------------------------------

def plan_timeline(graph, pos):
    """
    Plan the animation timeline:
 - Pick a path through the graph (longest simple path or a BFS path).
      - Assign each edge in the path a start time.
      - Assign each node in the path a "pop" time (when the incoming edge finishes).

    Returns:
        path_nodes:  list of node IDs in order
        path_edges:  list of (u, v) edges in order
        edge_timings: dict mapping edge index -> (start_time, end_time)
        node_timings: dict mapping node -> pop_time
    """
    # Find a reasonably long simple path using a heuristic:
    # try all pairs and pick the longest shortest path.
    nodes = list(graph.nodes())
    best_path = []
    for source in nodes:
        for target in nodes:
            if source == target:
                continue
            try:
                path = nx.shortest_path(graph, source=source, target=target)
                if len(path) > len(best_path):
                    best_path = path
            except nx.NetworkXNoPath:
                continue

    if not best_path and nodes:
        best_path = [nodes[0]]

    path_nodes = best_path
    path_edges = list(zip(best_path[:-1], best_path[1:]))

    # Time budget: reserve time for draw-on + hold + fade-out within MASTER_PERIOD
    draw_duration = 0.35 # seconds per edge draw-on
    total_draw_time = len(path_edges) * draw_duration
    start_offset = 0.5     # delay before animation starts
    hold_time = 1.5        # hold after last edge draws
    fade_duration = 0.5    # fade everything back to dim

    # If the total is too long, compress draw_duration
    max_draw_time = MASTER_PERIOD - start_offset - hold_time - fade_duration
    if total_draw_time > max_draw_time:
        draw_duration = max_draw_time / max(len(path_edges), 1)
        total_draw_time = len(path_edges) * draw_duration

    edge_timings = {}
    node_timings = {}

    current_time = start_offset
    for i, (u, v) in enumerate(path_edges):
        edge_start = current_time
        edge_end = current_time + draw_duration
        edge_timings[i] = (edge_start, edge_end)

        # First node pops at the very start
        if i == 0:
            node_timings[u] = start_offset
        # Receiving node pops when the edge finishes drawing
        node_timings[v] = edge_end

        current_time = edge_end

    return path_nodes, path_edges, edge_timings, node_timings


# ---------------------------------------------------------------------------
# SVG Generation
# ---------------------------------------------------------------------------

def generate_svg(graph, pos, path_nodes, path_edges, edge_timings, node_timings):
    """Generate the full animated SVG string."""

    # --- SVG header and defs ---
    svg_parts = []

    svg_header = f"""\
<svg xmlns="http://www.w3.org/2000/svg"
     width="{SVG_WIDTH}" height="{SVG_HEIGHT}"
     viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}"
     style="background-color:{BG_COLOR}; display:block;">
  <defs>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{GLOW_COLOR}" stop-opacity="0.6"/>
      <stop offset="60%" stop-color="{GLOW_COLOR}" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="{GLOW_COLOR}" stop-opacity="0"/>
    </radialGradient>
    <style>
      .label {{
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 11px;
        fill: {TEXT_COLOR};
        text-anchor: middle;
        dominant-baseline: middle;
        pointer-events: none;
      }}
    </style>
  </defs>
"""

    svg_parts.append(svg_header)

    # --- Dim base layer: all edges ---
    dim_edges_svg = []
    for u, v in graph.edges():
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        dim_edges_svg.append(
            f'  <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{DIM_EDGE}" stroke-width="{EDGE_WIDTH}" '
            f'stroke-linecap="round"/>'
        )
    svg_parts.append("  <!-- Dim base edges -->\n")
    svg_parts.append("\n".join(dim_edges_svg) + "\n")

    # --- Dim base layer: all nodes ---
    dim_nodes_svg = []
    for node in graph.nodes():
        cx, cy = pos[node]
        dim_nodes_svg.append(
            f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{NODE_RADIUS}" '
            f'fill="{DIM_NODE}"/>'
        )
    svg_parts.append("  <!-- Dim base nodes -->\n")
    svg_parts.append("\n".join(dim_nodes_svg) + "\n")

    # --- Animated edges (draw-on effect) ---
    svg_parts.append("  <!-- Animated path edges -->\n")
    for i, (u, v) in enumerate(path_edges):
        x1, y1 = pos[u]
        x2, y2 = pos[v]
        length = math.hypot(x2 - x1, y2 - y1)
        start_t, end_t = edge_timings[i]

        # KeyTimes for the draw-on:
        #   0            -> start_t  : hidden (offset = length)
        #   start_t      -> end_t    : drawing (offset goes length -> 0)
        #   end_t        -> fade_start : visible (offset = 0)
        #   fade_start   -> T : fade back to hidden        
        fade_start = MASTER_PERIOD - 0.5
        if fade_start < end_t:
            fade_start = end_t + 0.05

        vals, times = kt(
            (length, 0),
            (length, time_fraction(start_t)),
            (0, time_fraction(end_t)),
            (0, time_fraction(fade_start)),
            (length, 1.0),
        )

        edge_svg = f"""\
  <line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"
        stroke="{EDGE_COLOR}" stroke-width="{EDGE_WIDTH}"
        stroke-linecap="round"
        stroke-dasharray="{length:.2f}" stroke-dashoffset="{length:.2f}">
    <animate attributeName="stroke-dashoffset"
             values="{vals}"
             keyTimes="{times}"
             dur="{MASTER_PERIOD}s" repeatCount="indefinite"/>
  </line>"""
        svg_parts.append(edge_svg + "\n")

    # --- Animated nodes (pop + glow effect) ---
    svg_parts.append("  <!-- Animated path nodes -->\n")

    # We need to render glow circles first (behind nodes), then node circles.
    glow_parts = []
    node_parts = []

    for node in path_nodes:
        cx, cy = pos[node]
        pop_time = node_timings[node]

        # Glow: opacity 0 -> 1 at pop_time, then fade back near end
        fade_start = MASTER_PERIOD - 0.5
        glow_vals, glow_times = kt(
            (0, 0),
            (0, time_fraction(pop_time)),
            (1, time_fraction(pop_time + 0.05)),
            (1, time_fraction(fade_start)),
            (0, 1.0),
        )

        glow_parts.append(
            f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{GLOW_RADIUS}" '
            f'fill="url(#glow)" opacity="0">\n'
            f'    <animate attributeName="opacity"\n'
            f'             values="{glow_vals}"\n'
            f'             keyTimes="{glow_times}"\n'
            f'             dur="{MASTER_PERIOD}s" repeatCount="indefinite"/>\n'
            f'  </circle>'
        )

        # Node fill: dim -> highlight -> lit -> dim
        fill_vals, fill_times = kt(
            (DIM_NODE, 0),
            (DIM_NODE, time_fraction(pop_time)),
            (NODE_HIGHLIGHT, time_fraction(pop_time + 0.05)),
            (NODE_COLOR, time_fraction(pop_time + 0.2)),
            (NODE_COLOR, time_fraction(fade_start)),
            (DIM_NODE, 1.0),
        )

        # Node radius: standard -> pop -> settle -> standard        
        radius_vals, radius_times = kt(
            (NODE_RADIUS, 0),
            (NODE_RADIUS, time_fraction(pop_time)),
            (NODE_POP_RADIUS, time_fraction(pop_time + 0.05)),
            (NODE_LIT_RADIUS, time_fraction(pop_time + 0.2)),
            (NODE_LIT_RADIUS, time_fraction(fade_start)),
            (NODE_RADIUS, 1.0),
        )

        node_parts.append(
            f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{NODE_RADIUS}" '
            f'fill="{DIM_NODE}">\n'
            f'    <animate attributeName="fill"\n'
            f'             values="{fill_vals}"\n'
            f'             keyTimes="{fill_times}"\n'
            f'             dur="{MASTER_PERIOD}s" repeatCount="indefinite"/>\n'
            f'    <animate attributeName="r"\n'
            f'             values="{radius_vals}"\n'
            f'             keyTimes="{radius_times}"\n'
            f'             dur="{MASTER_PERIOD}s" repeatCount="indefinite"/>\n'
            f'  </circle>'
        )

    svg_parts.append("\n".join(glow_parts) + "\n")
    svg_parts.append("\n".join(node_parts) + "\n")

    # --- Node labels (optional, subtle) ---
    svg_parts.append("  <!-- Node labels -->\n")
    label_parts = []
    for node in path_nodes:
        cx, cy = pos[node]
        label_parts.append(
            f'  <text x="{cx:.1f}" y="{cy - 12:.1f}" class="label">{node}</text>'
        )
    svg_parts.append("\n".join(label_parts) + "\n")

    # --- Close SVG ---
    svg_parts.append("</svg>")

    return "\n".join(svg_parts)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def build_animated_svg(graph, output_path="animated_graph.svg"):
    """
    Take a NetworkX graph, compute layout, plan animation timeline,
    and write a self-contained animated SVG file.
    """
    pos = compute_layout(graph)
    path_nodes, path_edges, edge_timings, node_timings = plan_timeline(graph, pos)
    svg_string = generate_svg(
        graph, pos, path_nodes, path_edges, edge_timings, node_timings
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_string)

    print(f"✅ Animated SVG written to: {output_path}")
    print(f"   Nodes: {graph.number_of_nodes()}")
    print(f"   Edges: {graph.number_of_edges()}")
    print(f"   Path length: {len(path_nodes)} nodes, {len(path_edges)} edges")
    print(f"   Master period: {MASTER_PERIOD}s")
    return svg_string


# ---------------------------------------------------------------------------
# Demo / Test Cases
# ---------------------------------------------------------------------------

def demo_graph_small():
    """A small 6-node graph for quick testing."""
    G = nx.Graph()
    G.add_edges_from([
        ("A", "B"),
        ("B", "C"),
        ("C", "D"),
        ("D", "E"),
        ("E", "F"),
        ("B", "D"),
        ("A", "C"),
    ])
    return G


def demo_graph_grid():
    """A 3x3 grid graph — good for testing layout on structured data."""
    return nx.grid_2d_graph(3, 3)


def demo_graph_random():
    """A random Erdős–Rényi graph — good for testing on messy data."""
    return nx.gnp_random_graph(12, 0.25, seed=99)


def demo_graph_karate():
    """The famous Karate Club graph — a real-world social network."""
    return nx.karate_club_graph()


if __name__ == "__main__":
    import sys

    demos = {
        "small":  ("demo_small_graph.svg",  demo_graph_small),
        "grid":   ("demo_grid_graph.svg",   demo_graph_grid),
        "random": ("demo_random_graph.svg", demo_graph_random),
        "karate": ("demo_karate_graph.svg", demo_graph_karate),
    }

    if len(sys.argv) > 1 and sys.argv[1] in demos:
        name = sys.argv[1]
    else:
        name = "small"
        print("Usage: python gen_animated_graph_svg.py [small|grid|random|karate]")
        print(f"Defaulting to '{name}'\n")

    output_file, graph_fn = demos[name]
    graph = graph_fn()
    build_animated_svg(graph, output_path=output_file)