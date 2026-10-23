"""Markdown extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
import os

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


_MD_INLINE_LINK_RE = re.compile(r'(?<!\!)\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+[^)]*)?\)')

_MD_REF_DEF_RE = re.compile(r'^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?')

_MD_WIKILINK_RE = re.compile(r'(?<!\!)\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]')

_MD_LINKABLE_EXTS = {".md", ".mdx", ".qmd", ".markdown", ".rst", ".txt"}

# Vault / PKM / Task / Temporal extraction patterns
_TASK_CHECKBOX_RE = re.compile(r'^(\s*)[-*+]\s+\[([ xX/\->?!])\]\s+(.+)$')
_DATAVIEW_INLINE_RE = re.compile(r'\[([a-zA-Z0-9_\-]+)::\s*(\[\[[^\]]+\]\]|[^\]]+)\]')
_OBSIDIAN_DUE_RE = re.compile(r'📅\s*(\d{4}-\d{2}-\d{2})')
_OBSIDIAN_SCHED_RE = re.compile(r'⏳\s*(\d{4}-\d{2}-\d{2})')
_ISO_DATE_RE = re.compile(r'\b(20\d{2}-\d{2}-\d{2})\b')
_US_DATE_RE = re.compile(r'\b(0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])[/-](20\d{2})\b')
_COMPACT_MMDDYYYY_RE = re.compile(r'\b(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(20\d{2})\b')
_PARTIAL_MON_DAY_TIME_RE = re.compile(
    r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})(?!\d)(?:\s+at\s+(\d{1,2})[:.\-](\d{2}))?',
    re.IGNORECASE,
)
_EXCALIDRAW_TS_RE = re.compile(r'(20\d{2}-\d{2}-\d{2})\s+(\d{2})[.:](\d{2})(?:[.:](\d{2}))?')
_TIME_12H_24H_RE = re.compile(r'\b(?:([01]?\d|2[0-3]):([0-5]\d)(?:\s*([aApP][mM]))?|([1-9]|1[0-2])\s*([aApP][mM]))\b')

_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def extract_temporal_envelope(path: Path, source: str = "", frontmatter: dict | None = None) -> dict:
    """Extract multi-signal temporal envelope for cross-channel temporal correlation.

    Combines:
    1. YAML frontmatter dates (captured_at, date, created, updated, document_date)
    2. Filename temporal patterns (ISO dates, MMDDYYYY, Excalidraw timestamps,
       and partial 'Jun 22 at 16-35' voice-memo style dates without year)
    3. Content timestamps & dates
    4. Filesystem st_birthtime and st_mtime
    """
    fm = frontmatter or {}
    fname = path.name
    dates_found: list[str] = []
    times_found: list[str] = []
    partial_month_day: str | None = None
    explicit_iso: str | None = None
    basis = "unknown"

    # 1. Frontmatter dates
    for key in ("captured_at", "document_date", "date", "created", "updated"):
        val = str(fm.get(key) or "").strip().strip('"').strip("'")
        if not val or "{{" in val:
            continue
        m_iso = _ISO_DATE_RE.search(val)
        if m_iso:
            dates_found.append(m_iso.group(1))
            if "T" in val:
                explicit_iso = val
            basis = f"frontmatter:{key}"
            break

    # 2. Filename patterns
    m_exc = _EXCALIDRAW_TS_RE.search(fname)
    if m_exc:
        d_str = m_exc.group(1)
        t_str = f"{m_exc.group(2)}:{m_exc.group(3)}"
        dates_found.append(d_str)
        times_found.append(t_str)
        explicit_iso = f"{d_str}T{t_str}:{m_exc.group(4) or '00'}"
        if basis == "unknown":
            basis = "filename_timestamp"

    for m in _ISO_DATE_RE.finditer(fname):
        if m.group(1) not in dates_found:
            dates_found.append(m.group(1))
            if basis == "unknown":
                basis = "filename_iso_date"

    for m in _US_DATE_RE.finditer(fname):
        iso_d = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        if iso_d not in dates_found:
            dates_found.append(iso_d)
            if basis == "unknown":
                basis = "filename_us_date"

    for m in _COMPACT_MMDDYYYY_RE.finditer(fname):
        iso_d = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        if iso_d not in dates_found:
            dates_found.append(iso_d)
            if basis == "unknown":
                basis = "filename_compact_date"

    m_part = _PARTIAL_MON_DAY_TIME_RE.search(fname)
    if m_part:
        mon_num = _MONTH_MAP.get(m_part.group(1)[:3].lower(), 1)
        day_num = int(m_part.group(2))
        partial_month_day = f"{mon_num:02d}-{day_num:02d}"
        if m_part.group(3) and m_part.group(4):
            times_found.append(f"{int(m_part.group(3)):02d}:{m_part.group(4)}")
        if basis == "unknown":
            basis = "filename_partial_month_day"

    # 3. Content dates & times (first 2000 chars)
    snippet = source[:2000] if source else ""
    for m in _ISO_DATE_RE.finditer(snippet):
        if m.group(1) not in dates_found:
            dates_found.append(m.group(1))
            if basis == "unknown":
                basis = "content_iso_date"
    for m in _US_DATE_RE.finditer(snippet):
        iso_d = f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
        if iso_d not in dates_found:
            dates_found.append(iso_d)
            if basis == "unknown":
                basis = "content_us_date"

    # 4. Filesystem timestamps
    fs_mtime = None
    fs_birthtime = None
    try:
        st = path.stat()
        fs_mtime = st.st_mtime
        fs_birthtime = getattr(st, "st_birthtime", None) or st.st_ctime
    except OSError:
        pass

    if not dates_found and partial_month_day and fs_birthtime:
        from datetime import datetime, timezone
        inferred_year = datetime.fromtimestamp(fs_birthtime, tz=timezone.utc).year
        dates_found.append(f"{inferred_year}-{partial_month_day}")
        basis = "partial_filename_plus_birthtime_year"

    primary_date = dates_found[0] if dates_found else None
    primary_time = times_found[0] if times_found else None
    if not explicit_iso and primary_date and primary_time:
        explicit_iso = f"{primary_date}T{primary_time}:00"

    return {
        "primary_date": primary_date,
        "primary_time": primary_time,
        "canonical_iso": explicit_iso,
        "partial_month_day": partial_month_day,
        "all_dates": dates_found[:5],
        "all_times": times_found[:5],
        "fs_birthtime": fs_birthtime,
        "fs_mtime": fs_mtime,
        "temporal_basis": basis,
    }


def _parse_yaml_frontmatter(lines: list[str]) -> tuple[dict, int]:
    """Lightweight stdlib YAML frontmatter parser returning (metadata_dict, end_line_idx)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    fm: dict = {}
    current_list_key: str | None = None
    end_idx = 0
    for idx in range(1, min(len(lines), 80)):
        raw = lines[idx]
        if raw.strip() in ("---", "..."):
            end_idx = idx + 1
            break
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith(("  - ", "- ")) and current_list_key:
            item_val = raw.split("-", 1)[1].strip().strip('"').strip("'")
            if isinstance(fm.get(current_list_key), list):
                fm[current_list_key].append(item_val)
            continue
        if ":" in raw and not raw.startswith(" "):
            k, v = raw.split(":", 1)
            key = k.strip()
            val = v.strip()
            if not val:
                fm[key] = []
                current_list_key = key
            elif val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(",") if x.strip()]
                fm[key] = items
                current_list_key = None
            else:
                fm[key] = val.strip('"').strip("'")
                current_list_key = None
    return fm, end_idx


def _resolve_markdown_link(raw: str, source_dir: Path) -> "Path | None":
    """Resolve a markdown link target to the absolute path of a sibling document.

    Returns the resolved (normalized, not necessarily existing) path when the
    target is a *local* relative/absolute file-path link to a document, or None
    when it should be skipped: external URLs (http/https/mailto/protocol-
    relative/data), pure in-page anchors (``#section``), and links to non-doc
    file types (code/assets are handled by their own extractors).

    The anchor fragment (``#section``) and query (``?x=1``) are stripped before
    resolution so ``./repo.md#setup`` resolves to the same node as ``./repo.md``.
    Extension-less targets (typical of wikilinks) are treated as sibling ``.md``.
    """
    target = raw.strip()
    if not target:
        return None
    # Drop anchor / query so #section links still resolve to the target doc.
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return None
    low = target.lower()
    if "://" in target or low.startswith(("mailto:", "tel:", "//", "data:")):
        return None
    suffix = Path(target).suffix.lower()
    if suffix == "":
        target = target + ".md"
        suffix = ".md"
    if suffix not in _MD_LINKABLE_EXTS:
        return None
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = source_dir / candidate
    return Path(os.path.normpath(str(candidate)))

def extract_markdown(path: Path) -> dict:
    """Extract structural nodes and edges from a Markdown file.

    Produces nodes for:
    - The file itself
    - Each heading (# / ## / ### etc.)

    Produces edges for:
    - file --contains--> heading
    - parent heading --contains--> child heading (nesting by level)
    - heading --references--> other node (when backtick `Name` matches a known pattern)
    - file --references--> linked document, for inline ``[text](./other.md)``,
      reference-style ``[label]: ./other.md`` and ``[[wikilink]]`` links, so a
      hub doc (``index.md`` / ``table-of-contents.md``) becomes a real hub node
      instead of an under-connected orphan (#1376). The target node ID is built
      from the resolved target path with the same recipe as the target file's
      own node, so the edge merges into that node (no ghost node). External
      URLs, in-page anchors, images and non-document targets are skipped.

    Fenced code blocks (``` ... ```) are skipped during parsing so their
    contents don't get treated as headings, but no node is emitted for
    them — they were always orphans (only a single contains edge to the
    parent doc) and inflated the disconnected-component count (#1077).

    No tree-sitter dependency — pure line-by-line parsing.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, file_type: str = "document") -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": file_type,
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": confidence, "source_file": str_path,
                      "source_location": f"L{line}", "weight": weight})

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    source_dir = path.parent
    # Dedup link edges by resolved target node so a hub doc that links to the
    # same sibling many times yields one edge, not N (keeps weights meaningful).
    linked_targets: set[str] = set()

    def add_link(raw: str, line: int) -> None:
        resolved = _resolve_markdown_link(raw, source_dir)
        if resolved is None:
            return
        # Build the target ID with the SAME recipe as the target file's own
        # node (_make_id(str(path)) at extract time, canonicalized to
        # _file_node_id(rel) by the extract() post-pass). Using the absolute
        # resolved path means both endpoints get remapped identically, so the
        # edge merges into the existing doc node instead of spawning a ghost.
        tgt_nid = _make_id(str(resolved))
        if tgt_nid == file_nid or tgt_nid in linked_targets:
            return
        linked_targets.add(tgt_nid)
        add_edge(file_nid, tgt_nid, "references", line)

    # Track heading stack for nesting: [(level, nid), ...]
    heading_stack: list[tuple[int, str]] = []
    in_code_block = False

    lines = source.splitlines()
    for line_num_0, line_text in enumerate(lines):
        line_num = line_num_0 + 1

        # Skip over fenced code blocks so their contents are not parsed as
        # headings, but do not emit nodes/edges for them (#1077).
        stripped = line_text.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        # Markdown links -> document references (#1376). Scanned on every
        # non-fenced line (including heading lines, which the heading branch
        # below `continue`s past) so links anywhere in the doc are captured.
        for m in _MD_INLINE_LINK_RE.finditer(line_text):
            add_link(m.group(1), line_num)
        for m in _MD_WIKILINK_RE.finditer(line_text):
            add_link(m.group(1), line_num)
        ref_def = _MD_REF_DEF_RE.match(line_text)
        if ref_def:
            add_link(ref_def.group(1), line_num)

        # Detect headings: # Heading, ## Heading, etc.
        heading_match = re.match(r'^(#{1,6})\s+(.+)', line_text)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            h_nid = _make_id(stem, title)
            # Avoid duplicate heading IDs by appending line number
            if h_nid in seen_ids:
                h_nid = _make_id(stem, title, str(line_num))
            add_node(h_nid, title, line_num)

            # Pop headings at same or deeper level
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()

            # Connect to parent heading or file
            parent = heading_stack[-1][1] if heading_stack else file_nid
            add_edge(parent, h_nid, "contains", line_num)

            heading_stack.append((level, h_nid))
            continue

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def extract_vault_markdown(path: Path) -> dict:
    """Enhanced Markdown extractor for Obsidian Vaults, tasks, frontmatter & temporal correlation.

    Extracts:
    - File node enriched with YAML frontmatter (`node_role`, `status`, `para_role`, `project`,
      `depends_on`, `due`, `tags`) and `temporal_envelope`
    - Section headings (`#` .. `######`)
    - Markdown checkbox tasks (`- [ ]`, `- [x]`, `- [/]`, `- [-]`) as first-class task nodes
      with inline Dataview fields (`[depends_on:: ...]`, `[mode:: parallel]`, `[project:: ...]`),
      Obsidian Tasks dates (`📅 YYYY-MM-DD`, `⏳ YYYY-MM-DD`), and sequential/parallel edges
    - Frontmatter `depends_on` / `blocks` / `project` links as directed workflow edges
    """
    base = extract_markdown(path)
    if "error" in base or not base.get("nodes"):
        return base

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return base

    lines = source.splitlines()
    fm, fm_end = _parse_yaml_frontmatter(lines)
    temporal = extract_temporal_envelope(path, source=source, frontmatter=fm)

    nodes: list[dict] = list(base["nodes"])
    edges: list[dict] = list(base["edges"])
    seen_ids: set[str] = {n["id"] for n in nodes}
    str_path = str(path)
    stem = _file_stem(path)
    file_node = nodes[0]
    file_nid = file_node["id"]

    # Enrich file node with frontmatter and temporal envelope
    note_type = str(fm.get("type") or "").lower().strip()
    if not note_type:
        low_parts = [p.lower() for p in path.parts]
        if any("project" in p for p in low_parts):
            note_type = "project"
        elif any("daily" in p for p in low_parts):
            note_type = "daily"
        elif any("inbox" in p for p in low_parts):
            note_type = "inbox"
        elif any("area" in p for p in low_parts):
            note_type = "area"
        elif any("resource" in p for p in low_parts):
            note_type = "resource"
        else:
            note_type = "note"

    file_node["_origin"] = "ast"
    file_node["node_role"] = note_type
    file_node["status"] = str(fm.get("status") or "active")
    file_node["execution_mode"] = str(fm.get("execution_mode") or "independent")
    file_node["para_role"] = str(fm.get("para_role") or note_type)
    file_node["temporal_envelope"] = temporal
    if temporal.get("primary_date"):
        file_node["captured_at"] = temporal.get("canonical_iso") or temporal["primary_date"]
    if fm.get("due"):
        file_node["due"] = str(fm["due"])
    if fm.get("priority_score") is not None:
        try:
            file_node["priority_score"] = float(fm["priority_score"])
        except (ValueError, TypeError):
            pass

    source_dir = path.parent

    def _resolve_wikilink_or_title(raw_ref: str) -> str:
        cleaned = re.sub(r'^\[\[|\]\]$', '', str(raw_ref).strip())
        cleaned = cleaned.split("|", 1)[0].split("#", 1)[0].strip()
        resolved = _resolve_markdown_link(cleaned, source_dir)
        if resolved is not None and resolved.exists():
            return _make_id(str(resolved))
        return _make_id(cleaned)

    # Frontmatter workflow edges (depends_on, blocks, project)
    for dep_key, rel_name in (("depends_on", "depends_on"), ("blocks", "blocks"), ("project", "subtask_of")):
        raw_val = fm.get(dep_key)
        if not raw_val:
            continue
        items = raw_val if isinstance(raw_val, list) else [raw_val]
        for item in items:
            if not item:
                continue
            tgt_id = _resolve_wikilink_or_title(str(item))
            if tgt_id and tgt_id != file_nid:
                edges.append({
                    "source": file_nid,
                    "target": tgt_id,
                    "relation": rel_name,
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": str_path,
                    "source_location": "L1",
                    "weight": 1.5,
                })

    # Parse markdown tasks (- [ ] / - [x]) in body
    in_code_block = False
    current_section_title = ""
    prev_seq_task_id: str | None = None
    indent_stack: list[tuple[int, str]] = []

    for idx in range(fm_end, len(lines)):
        line_num = idx + 1
        line_text = lines[idx]
        stripped = line_text.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        h_match = re.match(r'^(#{1,6})\s+(.+)', line_text)
        if h_match:
            current_section_title = h_match.group(2).strip().lower()
            prev_seq_task_id = None
            indent_stack.clear()
            continue

        t_match = _TASK_CHECKBOX_RE.match(line_text)
        if not t_match:
            continue

        indent_len = len(t_match.group(1).expandtabs(4))
        mark = t_match.group(2).lower()
        raw_task_body = t_match.group(3).strip()

        # Extract inline Dataview fields [key:: value]
        inline_fields: dict[str, str] = {}
        for dv_m in _DATAVIEW_INLINE_RE.finditer(raw_task_body):
            inline_fields[dv_m.group(1).strip().lower()] = dv_m.group(2).strip()

        due_match = _OBSIDIAN_DUE_RE.search(raw_task_body)
        sched_match = _OBSIDIAN_SCHED_RE.search(raw_task_body)
        due_date = inline_fields.get("due") or (due_match.group(1) if due_match else None)
        sched_date = inline_fields.get("scheduled") or (sched_match.group(1) if sched_match else None)

        # Clean display label for the task card
        clean_label = _DATAVIEW_INLINE_RE.sub("", raw_task_body)
        clean_label = _OBSIDIAN_DUE_RE.sub("", clean_label)
        clean_label = _OBSIDIAN_SCHED_RE.sub("", clean_label)
        clean_label = re.sub(r'[⏫🔼🔽🔺⏬]', '', clean_label).strip()
        clean_label = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', clean_label)
        clean_label = re.sub(r'\[\[([^\]]+)\]\]', r'\1', clean_label).strip()
        if not clean_label:
            clean_label = f"Task L{line_num}"

        task_id = inline_fields.get("id") or _make_id(stem, "task", f"L{line_num}", clean_label[:32])
        if task_id in seen_ids:
            task_id = _make_id(stem, "task", str(line_num))
        seen_ids.add(task_id)

        status_map = {
            "x": "completed",
            "/": "in-progress",
            "-": "cancelled",
            ">": "scheduled",
            "?": "needs_review",
            "!": "blocked",
            " ": "ready",
        }
        task_status = inline_fields.get("status") or status_map.get(mark, "ready")

        # Determine sequential vs parallel mode from inline fields, section headers, or cue words
        exec_mode = inline_fields.get("mode") or inline_fields.get("execution_mode")
        if not exec_mode:
            low_body = clean_label.lower()
            if any(k in low_body for k in ("parallel", "idea:", "maybe ", "option ")):
                exec_mode = "parallel"
            elif any(k in low_body for k in ("first ", "then ", "after ", "step ", "1.", "2.", "3.")) or "sequential" in current_section_title:
                exec_mode = "sequential"
            elif "parallel" in current_section_title or "idea" in current_section_title:
                exec_mode = "parallel"
            else:
                exec_mode = "independent"

        node_role = "idea" if ("idea" in current_section_title or clean_label.lower().startswith("idea:")) else "task"

        task_node = {
            "id": task_id,
            "label": clean_label[:120],
            "file_type": "concept",
            "node_role": node_role,
            "task_status": task_status,
            "execution_mode": exec_mode,
            "due": due_date,
            "scheduled": sched_date,
            "source_file": str_path,
            "source_location": f"L{line_num}",
            "temporal_envelope": temporal,
            "_origin": "ast",
        }
        nodes.append(task_node)

        # Link parent file (or parent indented task) -> task_id
        while indent_stack and indent_stack[-1][0] >= indent_len:
            indent_stack.pop()
        if indent_stack:
            parent_task_id = indent_stack[-1][1]
            edges.append({
                "source": parent_task_id,
                "target": task_id,
                "relation": "subtask_of",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str_path,
                "source_location": f"L{line_num}",
                "weight": 1.2,
            })
        else:
            edges.append({
                "source": file_nid,
                "target": task_id,
                "relation": "contains",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": str_path,
                "source_location": f"L{line_num}",
                "weight": 1.0,
            })
        indent_stack.append((indent_len, task_id))

        # Explicit inline depends_on::
        if "depends_on" in inline_fields:
            dep_target = _resolve_wikilink_or_title(inline_fields["depends_on"])
            if dep_target and dep_target != task_id:
                edges.append({
                    "source": dep_target,
                    "target": task_id,
                    "relation": "blocks",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": str_path,
                    "source_location": f"L{line_num}",
                    "weight": 1.5,
                })
        elif exec_mode == "sequential" and prev_seq_task_id and prev_seq_task_id != task_id:
            edges.append({
                "source": prev_seq_task_id,
                "target": task_id,
                "relation": "blocks",
                "confidence": "INFERRED",
                "confidence_score": 0.85,
                "source_file": str_path,
                "source_location": f"L{line_num}",
                "weight": 1.3,
            })

        if exec_mode == "sequential":
            prev_seq_task_id = task_id

        # Link task to any [[wikilink]] referenced inside the task line
        for wm in _MD_WIKILINK_RE.finditer(raw_task_body):
            resolved_doc = _resolve_markdown_link(wm.group(1), source_dir)
            if resolved_doc is not None:
                tgt_doc_id = _make_id(str(resolved_doc))
                if tgt_doc_id != task_id:
                    edges.append({
                        "source": task_id,
                        "target": tgt_doc_id,
                        "relation": "references",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": str_path,
                        "source_location": f"L{line_num}",
                        "weight": 1.2,
                    })

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}
