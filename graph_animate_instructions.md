# Using the Script With Your Own Graphs

The key function is `build_animated_svg(graph, output_path)`. You just need to create a **NetworkX graph** and pass it in. Here's how:

## 1. From an Edge List (Most Common)

If you have pairs of connected nodes, just feed them in:

```python
from gen_animated_graph_svg import build_animated_svg
import networkx as nx

G = nx.Graph()
G.add_edges_from([
    ("Alice", "Bob"),
    ("Bob", "Carol"),
    ("Carol", "Dave"),
    ("Alice", "Carol"),
    ("Dave", "Eve"),
])

build_animated_svg(G, output_path="my_graph.svg")
```

## 2. From a CSV File of Edges

If you have a CSV like:

```list
source,target
Alice,Bob
Bob,Carol
Carol,Dave
```

```python
import csv
import networkx as nx
from gen_animated_graph_svg import build_animated_svg

G = nx.Graph()
with open("edges.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        G.add_edge(row["source"], row["target"])

build_animated_svg(G, output_path="my_graph.svg")
```

## 3. From an Adjacency Matrix (NumPy)

```python
import numpy as np
import networkx as nx
from gen_animated_graph_svg import build_animated_svg

# 1 = connected, 0 = not connected
matrix = np.array([
    [0, 1, 1, 0],
    [1, 0, 1, 1],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
])

G = nx.from_numpy_array(matrix)
build_animated_svg(G, output_path="my_graph.svg")
```

## 4. From a Directed Graph

```python
import networkx as nx
from gen_animated_graph_svg import build_animated_svg

G = nx.DiGraph()
G.add_edges_from([
    ("Start", "Process"),
    ("Process", "Validate"),
    ("Validate", "End"),
    ("Validate", "Error"),
    ("Error", "Process"),
])

build_animated_svg(G, output_path="flow_graph.svg")
```

> **Note:** The script uses `nx.shortest_path` to find the animation path, which works with both directed and undirected graphs.

## 5. Customizing Appearance

Edit the constants at the top of the script:

```python
# Colors — change these to match your theme
EDGE_COLOR = "#4db18f"       # lit edge color
NODE_COLOR = "#4db18f"       # lit node color
NODE_HIGHLIGHT = "#7ee8c8"   # flash color on pop
BG_COLOR = "#0d1117"         # SVG background

# Canvas size
SVG_WIDTH = 900
SVG_HEIGHT = 360

# Timing
MASTER_PERIOD = 10.0 # loop length in seconds

# Node sizes
NODE_RADIUS = 4        # dim/default
NODE_POP_RADIUS = 8    # flash size
NODE_LIT_RADIUS = 5.6  # settled lit size
```

## 6. Choosing a Different Layout

In `compute_layout()`, swap the layout algorithm:

```python
# Force-directed (default — good for most graphs)
pos = nx.spring_layout(graph, seed=42)

# Better for structured/graph-like data
pos = nx.kamada_kawai_layout(graph)

# Circular — good for ring topologies
pos = nx.circular_layout(graph)

# Hierarchical — good for trees/DAGs
pos = nx.nx_agraph.pygraphviz_layout(graph, prog="dot")
```

## 7. Controlling Which Path Gets Animated

By default, the script finds the **longest shortest path**. To animate a specific path instead, modify `plan_timeline()`:

```python
def plan_timeline(graph, pos):
    # Force a specific path to animate
    my_path = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    
    path_nodes = my_path
    path_edges = list(zip(my_path[:-1], my_path[1:]))
    
    # ... rest of the timing logic stays the same
```

## Quick Checklist

| Step | What to do |
| ------ | ----------- |
| **Install** | `pip install networkx numpy` |
| **Build graph** | Create a `nx.Graph()` and add edges/nodes |
| **Call** | `build_animated_svg(G, "output.svg")` |
| **Embed** | Drop the `.svg` into a GitHub README, HTML, or presentation |
| **Customize** | Tweak colors/sizes/timing in the config block |

That's it — any NetworkX graph works. The output is a single `.svg` file with no dependencies, so it animates anywhere SVGs are supported.
