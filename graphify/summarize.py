"""Deterministic file-level node summaries (Option A: attribute on graph.json).

Opt-in via `graphify summarize`. Builds one bounded sentence per file node from
graph-local signal only — no LLM, no sidecar.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path, PurePosixPath

import networkx as nx
from networkx.readwrite import json_graph

from graphify.build import edge_data
from graphify.paths import write_json_atomic

SUMMARY_VERSION = 1
GENERATED_BY = "deterministic"
# ponytail: hard cap; raise if agents need more signal than ~one sentence
MAX_SUMMARY_LEN = 280
_MAX_SYMBOLS = 5
_MAX_IMPORTS = 3


def is_file_node(data: dict) -> bool:
    """True for the file-root node of a source file (label == basename)."""
    ft = data.get("file_type")
    if ft is not None and ft not in ("code", "document", "paper", "image", ""):
        return False
    sf = data.get("source_file") or ""
    label = data.get("label") or ""
    if not sf or not label:
        return False
    return PurePosixPath(sf.replace("\\", "/")).name == label


def _clip(text: str, n: int = MAX_SUMMARY_LEN) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def _first_clause(text: str) -> str:
    text = " ".join(text.split())
    for sep in (". ", "; ", " — ", " - "):
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    return text.rstrip(".;:")


def _neighbor_labels(G: nx.Graph, nid: str, relation: str, *, outgoing: bool) -> list[str]:
    labels: list[str] = []
    neighbors = G.successors(nid) if outgoing else G.predecessors(nid)
    for nb in neighbors:
        u, v = (nid, nb) if outgoing else (nb, nid)
        if edge_data(G, u, v).get("relation") != relation:
            continue
        lab = (G.nodes[nb].get("label") or "").strip()
        if not lab or G.nodes[nb].get("file_type") == "rationale":
            continue
        labels.append(lab)
    labels.sort(key=lambda x: (x.startswith("_"), x.lower()))
    return labels


def _module_doc(G: nx.Graph, nid: str) -> str | None:
    """Module docstring / top rationale attached via rationale_for → file."""
    best: str | None = None
    for nb in G.predecessors(nid):
        if edge_data(G, nb, nid).get("relation") != "rationale_for":
            continue
        lab = (G.nodes[nb].get("label") or "").strip()
        if len(lab) < 20:
            continue
        # Prefer the earliest / longest-ish human sentence; first hit is fine.
        best = lab
        break
    return best


def _dominant_relation(G: nx.Graph, nid: str) -> str | None:
    counts: Counter[str] = Counter()
    for nb in G.successors(nid):
        rel = edge_data(G, nid, nb).get("relation")
        if rel and rel not in ("contains", "rationale_for"):
            counts[rel] += 1
    for nb in G.predecessors(nid):
        rel = edge_data(G, nb, nid).get("relation")
        if rel and rel not in ("contains", "rationale_for"):
            counts[rel] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def build_summary(G: nx.Graph, nid: str) -> str:
    """One bounded sentence describing a file-level node's responsibility."""
    d = G.nodes[nid]
    parts: list[str] = []

    doc = _module_doc(G, nid)
    if doc:
        parts.append(_first_clause(doc))

    symbols = _neighbor_labels(G, nid, "contains", outgoing=True)[:_MAX_SYMBOLS]
    if symbols:
        verb = "defines" if not parts else "exports"
        parts.append(f"{verb} {', '.join(symbols)}")

    if not parts:
        imports = _neighbor_labels(G, nid, "imports", outgoing=True)[:_MAX_IMPORTS]
        if not imports:
            imports = _neighbor_labels(G, nid, "imports_from", outgoing=True)[:_MAX_IMPORTS]
        if imports:
            parts.append(f"Imports {', '.join(imports)}")
        dom = _dominant_relation(G, nid)
        if dom:
            parts.append(f"mainly {dom}")
        community = (d.get("community_name") or "").strip()
        if community and not community.startswith("Community "):
            parts.append(f"in {community}")

    if not parts:
        label = d.get("label") or nid
        sf = d.get("source_file") or ""
        parts.append(f"File {label}" + (f" ({sf})" if sf else ""))

    text = "; ".join(parts)
    if not text.endswith("."):
        text += "."
    return _clip(text)


def summarize_graph(G: nx.Graph) -> dict[str, str]:
    """Return {node_id: summary} for every file-level node that gets a summary."""
    out: dict[str, str] = {}
    for nid, data in G.nodes(data=True):
        if not is_file_node(data):
            continue
        summary = build_summary(G, nid)
        if summary:
            out[nid] = summary
    return out


def apply_summaries_to_raw(raw: dict, summaries: dict[str, str]) -> int:
    """Mutate raw graph.json dict in place. Returns number of nodes updated."""
    n = 0
    for node in raw.get("nodes", []):
        nid = node.get("id")
        if nid not in summaries:
            continue
        node["summary"] = summaries[nid]
        node["generated_by"] = GENERATED_BY
        node["summary_version"] = SUMMARY_VERSION
        n += 1
    return n


def _load_digraph(raw: dict) -> nx.Graph:
    payload = dict(raw)
    if "links" not in payload and "edges" in payload:
        payload = dict(payload, links=payload["edges"])
    payload = {**payload, "directed": True}
    try:
        return json_graph.node_link_graph(payload, edges="links")
    except TypeError:
        return json_graph.node_link_graph(payload)


def summarize_graph_file(path: Path) -> int:
    """Load graph.json, attach file-level summaries, write atomically. Returns count."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    G = _load_digraph(raw)
    summaries = summarize_graph(G)
    n = apply_summaries_to_raw(raw, summaries)
    write_json_atomic(path, raw, indent=2)
    return n


if __name__ == "__main__":
    # Smallest check that fails if file-node detection or clipping breaks.
    G = nx.DiGraph()
    G.add_node(
        "f",
        label="mod.py",
        file_type="code",
        source_file="pkg/mod.py",
        source_location="L1",
        community_name="Parsers",
    )
    G.add_node("r", label="Loads widgets from disk and caches them.", file_type="rationale")
    G.add_node("fn", label="load()", file_type="code", source_file="pkg/mod.py")
    G.add_edge("r", "f", relation="rationale_for")
    G.add_edge("f", "fn", relation="contains")
    s = build_summary(G, "f")
    assert "Loads widgets" in s, s
    assert "load()" in s, s
    assert len(s) <= MAX_SUMMARY_LEN
    assert is_file_node(G.nodes["f"])
    assert not is_file_node(G.nodes["fn"])
    print("ok", s)
