"""File-level node summaries (docs/node-summaries-rfc.md Option A)."""
from __future__ import annotations

import json

import networkx as nx

import graphify.__main__ as mainmod
from graphify.summarize import (
    MAX_SUMMARY_LEN,
    apply_summaries_to_raw,
    build_summary,
    is_file_node,
    summarize_graph,
    summarize_graph_file,
)


def _tiny_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node(
        "mod",
        label="mod.py",
        file_type="code",
        source_file="pkg/mod.py",
        source_location="L1",
        community_name="Parsers",
    )
    G.add_node(
        "load",
        label="load()",
        file_type="code",
        source_file="pkg/mod.py",
        source_location="L10",
    )
    G.add_node(
        "_priv",
        label="_helper()",
        file_type="code",
        source_file="pkg/mod.py",
        source_location="L20",
    )
    G.add_node(
        "rat",
        label="Loads widgets from disk and caches them for reuse.",
        file_type="rationale",
        source_file="pkg/mod.py",
        source_location="L1",
    )
    G.add_edge("rat", "mod", relation="rationale_for", confidence="EXTRACTED")
    G.add_edge("mod", "load", relation="contains", confidence="EXTRACTED")
    G.add_edge("mod", "_priv", relation="contains", confidence="EXTRACTED")
    return G


def test_is_file_node_matches_basename_only():
    G = _tiny_graph()
    assert is_file_node(G.nodes["mod"])
    assert not is_file_node(G.nodes["load"])
    assert not is_file_node(G.nodes["rat"])


def test_build_summary_uses_doc_and_exports_and_stays_bounded():
    s = build_summary(_tiny_graph(), "mod")
    assert "Loads widgets" in s
    assert "load()" in s
    assert len(s) <= MAX_SUMMARY_LEN
    # Public symbols before private
    assert s.index("load()") < s.index("_helper()")


def test_summarize_graph_skips_symbol_nodes():
    summaries = summarize_graph(_tiny_graph())
    assert set(summaries) == {"mod"}
    assert "Loads widgets" in summaries["mod"]


def test_default_graph_has_no_summaries_until_opt_in(tmp_path):
    raw = {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "mod",
                "label": "mod.py",
                "file_type": "code",
                "source_file": "pkg/mod.py",
                "source_location": "L1",
            },
            {
                "id": "load",
                "label": "load()",
                "file_type": "code",
                "source_file": "pkg/mod.py",
                "source_location": "L10",
            },
        ],
        "links": [
            {
                "source": "mod",
                "target": "load",
                "relation": "contains",
                "confidence": "EXTRACTED",
            }
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(raw))
    loaded = json.loads(p.read_text())
    assert all("summary" not in n for n in loaded["nodes"])

    n = summarize_graph_file(p)
    assert n == 1
    out = json.loads(p.read_text())
    by_id = {n["id"]: n for n in out["nodes"]}
    assert "summary" in by_id["mod"]
    assert by_id["mod"]["generated_by"] == "deterministic"
    assert by_id["mod"]["summary_version"] == 1
    assert "summary" not in by_id["load"]
    assert len(by_id["mod"]["summary"]) <= MAX_SUMMARY_LEN


def test_apply_summaries_missing_id_is_noop():
    raw = {"nodes": [{"id": "a", "label": "a.py", "source_file": "a.py"}]}
    assert apply_summaries_to_raw(raw, {"missing": "x"}) == 0
    assert "summary" not in raw["nodes"][0]


def test_explain_shows_summary_when_present(monkeypatch, tmp_path, capsys):
    raw = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "mod",
                "label": "mod.py",
                "file_type": "code",
                "source_file": "pkg/mod.py",
                "source_location": "L1",
                "community": 0,
                "summary": "Loads widgets from disk.",
                "generated_by": "deterministic",
                "summary_version": 1,
            }
        ],
        "links": [],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(raw))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "explain", "mod.py", "--graph", str(p)]
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Summary:   Loads widgets from disk." in out


def test_explain_omits_summary_when_absent(monkeypatch, tmp_path, capsys):
    raw = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "mod",
                "label": "mod.py",
                "file_type": "code",
                "source_file": "pkg/mod.py",
                "community": 0,
            }
        ],
        "links": [],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(raw))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "explain", "mod.py", "--graph", str(p)]
    )
    mainmod.main()
    assert "Summary:" not in capsys.readouterr().out


def test_summarize_cli(monkeypatch, tmp_path, capsys):
    raw = {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {
                "id": "mod",
                "label": "mod.py",
                "file_type": "code",
                "source_file": "pkg/mod.py",
                "source_location": "L1",
            }
        ],
        "links": [],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(raw))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv", ["graphify", "summarize", "--graph", str(p)]
    )
    mainmod.main()
    assert "Summarized 1 file-level node" in capsys.readouterr().out
    assert json.loads(p.read_text())["nodes"][0]["summary"]
