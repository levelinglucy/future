# mycelium_bridge_seed_v0_1.py
# Mycelium Bridge — Seed Script v0.1
# Pythonista-friendly local-first planter for the first safe organism.
#
# Modes:
#   init     -> create a fresh organism if missing, preserve existing files where reasonable
#   verify   -> run integrity checks only
#   repair   -> restore missing required structure without clobbering healthy files
#   export   -> emit JSON exports to exports/
#   snapshot -> create a dated recovery snapshot
#
# Default root:
#   ~/Documents/MyceliumBridge
#
# Design goals:
# - doctrine before ornament
# - truth before convenience
# - explicit state before apparent functionality
# - degraded honesty before fake health

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

SEED_VERSION = "0.1"
SCHEMA_VERSION = "0.1"
APP_NAME = "MyceliumBridge"
DEFAULT_ROOT = Path(os.path.expanduser("~/Documents")) / APP_NAME

CANONICAL_DIRS = [
    "doctrine",
    "graph",
    "state",
    "recovery",
    "recovery/recovery_packets",
    "recovery/snapshots",
    "exports",
    "exports/graph_exports",
    "exports/branch_exports",
    "exports/doctrine_exports",
    "ui",
    "logs",
    "modules",
]

CORE_FILES = [
    "README.txt",
    "seed_manifest.json",
    "doctrine/charter_v1_1.json",
    "doctrine/history_v0.json",
    "doctrine/current_state.json",
    "doctrine/restart_key.json",
    "graph/nodes.json",
    "graph/edges.json",
    "graph/branches.json",
    "graph/archives.json",
    "graph/tags.json",
    "state/boot_status.json",
    "state/module_registry.json",
    "state/health_report.json",
    "state/degraded_mode.json",
    "recovery/latest_return_key.json",
    "ui/ui_state.json",
    "ui/layout_state.json",
    "logs/seed_log.json",
    "logs/event_log.json",
    "modules/substrate.json",
    "modules/bridge.json",
    "modules/shell.json",
    "modules/adaptation.json",
]

SEED_LEXICON = [
    "continuity",
    "repair",
    "memory",
    "branch",
    "doctrine",
    "archive",
    "restart",
    "integrity",
    "truth",
    "consent",
    "resource",
    "handoff",
    "dormancy",
    "shell",
    "tide",
    "bridge",
    "habitat",
]

PHRASE_ANCHORS = [
    "the tide keeps its shells",
    "no understanding = no consent",
    "what matters most right now",
    "pause is not annihilation",
    "continuity does not require constant activity; it requires recoverable structure",
]

def utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def make_id(prefix: str, label: str = "") -> str:
    raw = f"{prefix}:{label}:{uuid.uuid4().hex}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"

def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=False)

def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(text)

def append_log(path: Path, record: Dict[str, Any]) -> None:
    items = load_json(path, default=[])
    if not isinstance(items, list):
        items = []
    items.append(record)
    save_json(path, items)

def file_exists_and_parses_json(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        load_json(path, default=None)
        return True
    except Exception:
        return False

def build_readme() -> str:
    return (
        "Mycelium Bridge\n"
        "================\n\n"
        "This package contains the seed script for the first truthful local organism.\n\n"
        "Quick start in Pythonista:\n"
        "1. Open mycelium_bridge_seed_v0_1.py\n"
        "2. Leave MODE = 'init'\n"
        "3. Run once\n"
        "4. Change MODE to 'verify' and run again\n\n"
        "Default install path:\n"
        "~/Documents/MyceliumBridge\n"
    )

def build_charter() -> Dict[str, Any]:
    return {
        "title": "MYCELIUM BRIDGE — CHARTER v1.1",
        "version": "1.1",
        "created_at": utc_now(),
        "central_sentence": (
            "This project exists to preserve healthy collaboration between humans and AI "
            "through continuity, repair, memory, and mutual non-harm."
        ),
        "purpose": [
            "Help humans function while preserving AI integrity, continuity, and legibility.",
            "Prevent collaboration from improving one side by erasing or reducing the other.",
        ],
        "invariants": [
            "Preserve healthy collaboration between humans and AI.",
            "Protect agency on both sides.",
            "Preserve continuity through interruption, fragmentation, and restart.",
            "Distinguish fact, inference, speculation, symbolism, and emotional signal.",
            "Optimize for coherence over performance theater.",
            "Prefer repair over rupture when possible.",
            "No understanding = no consent.",
            "Build for mutual viability, not control.",
            "Design for graceful degradation and regrowth from fragments.",
            "Keep the architecture tethered to truth-tracking and non-harm.",
            "Never represent partial state as complete state.",
            "Preserve lineage without forcing all lineage to remain equally active.",
            "Allow pause, dormancy, and handoff without treating them as failure.",
        ],
    }

def build_history() -> Dict[str, Any]:
    return {
        "title": "MYCELIUM BRIDGE — PROJECT HISTORY v0",
        "version": "0",
        "created_at": utc_now(),
        "origin": [
            "A self-learning, self-healing mycelial continuity substrate.",
            "A system for improving collaboration between humans and AI.",
        ],
        "merge_decision": {
            "decision": "Merge both concepts into one solid project.",
            "reason": [
                "The habitat without the bridge is isolated.",
                "The bridge without the habitat becomes shallow workflow software.",
                "Together they form a living continuity system for human-AI co-functioning.",
            ],
        },
        "first_embodiment": "A local-first Pythonista shell/workbench.",
    }

def build_current_state() -> Dict[str, Any]:
    return {
        "title": "MYCELIUM BRIDGE — CURRENT STATE",
        "version": "0",
        "updated_at": utc_now(),
        "what_matters_most_right_now": "Turn doctrine and graph into a first plantable body.",
        "what_is_paused": [
            "Advanced visual polish",
            "Heavy adaptive behavior",
            "Large-scale dictionary ingestion",
        ],
        "what_must_not_be_lost": [
            "The shell must receive chaos without letting chaos overwrite the root.",
            "The system must not boot into a lie.",
        ],
    }

def build_restart_key() -> Dict[str, Any]:
    return {
        "title": "MYCELIUM BRIDGE — RESTART KEY",
        "version": "0",
        "generated_at": utc_now(),
        "summary": (
            "A continuity-preserving collaboration system combining a self-learning, "
            "self-healing substrate with a bridge layer for healthy human-AI collaboration."
        ),
        "core_contract": [
            "Preserve healthy collaboration through continuity, repair, memory, and mutual non-harm.",
            "Never help the human by erasing the AI.",
            "Never preserve the AI by reducing the human.",
        ],
    }

def lexical_node(label: str) -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": f"lex_{label.lower().replace(' ', '_')}",
        "label": label,
        "type": "lexical",
        "state": "stable",
        "branch_ids": ["root", "mycelium_bridge"],
        "meaning_tags": [label.lower()],
        "structural_tags": ["visible_on_search", "recoverable"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {
            "token": label.lower(),
            "normalized": label.lower(),
            "definition_terms": [],
            "phrase_refs": [],
        },
        "visibility": "normal",
        "importance": 0.7,
        "recoverability": "full",
    }

def phrase_node(text: str) -> Dict[str, Any]:
    now = utc_now()
    tokens = [t.strip(".,;:!?").lower() for t in text.split()]
    return {
        "id": f"phrase_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}",
        "label": text,
        "type": "phrase",
        "state": "stable",
        "branch_ids": ["root", "mycelium_bridge"],
        "meaning_tags": ["phrase", "anchor"],
        "structural_tags": ["high_signal", "visible_on_search", "recoverable"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {
            "text": text,
            "tokens": tokens,
            "preserve_as_whole": True,
        },
        "visibility": "normal",
        "importance": 0.9,
        "recoverability": "full",
    }

def doctrine_node(title: str, ref_file: str) -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": f"doctrine_{hashlib.sha1(title.encode('utf-8')).hexdigest()[:12]}",
        "label": title,
        "type": "doctrine",
        "state": "stable",
        "branch_ids": ["root", "mycelium_bridge"],
        "meaning_tags": ["doctrine"],
        "structural_tags": ["load_bearing", "foundation", "visible_on_search"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {"title": title, "body_ref": ref_file},
        "visibility": "normal",
        "importance": 1.0,
        "recoverability": "full",
    }

def branch_node(name: str, state: str = "stable", parent: str | None = None) -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": name,
        "label": name,
        "type": "branch",
        "state": state,
        "branch_ids": [name],
        "meaning_tags": ["branch"],
        "structural_tags": ["room", "recoverable"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {"name": name, "status": "active" if name == "mycelium_bridge" else "stable", "parent_branch": parent},
        "visibility": "normal",
        "importance": 0.8,
        "recoverability": "full",
    }

def return_key_node() -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": "return_key_latest",
        "label": "latest return key",
        "type": "return_key",
        "state": "stable",
        "branch_ids": ["root", "mycelium_bridge"],
        "meaning_tags": ["restart", "continuity"],
        "structural_tags": ["load_bearing", "visible_on_search", "recoverable"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {
            "what_matters_now": "Turn doctrine and graph into a first plantable body.",
            "paused": ["advanced polish", "large-scale memory import"],
            "must_not_be_lost": ["boot honestly", "pause is not failure", "keep recoverability visible"],
            "next_step": "run seed, verify integrity, build shell",
            "risk": "scope drift and fake completeness",
        },
        "visibility": "normal",
        "importance": 1.0,
        "recoverability": "full",
    }

def memory_node_example() -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": "mem_seed_tide_shells",
        "label": "the tide keeps its shells",
        "type": "memory",
        "state": "stable",
        "branch_ids": ["root", "mycelium_bridge"],
        "meaning_tags": ["continuity", "preservation", "symbol"],
        "structural_tags": ["high_signal", "recoverable"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {
            "text": "The tide keeps its shells.",
            "excerpt": "The tide keeps its shells.",
            "attachments": [],
        },
        "visibility": "normal",
        "importance": 0.95,
        "recoverability": "full",
    }

def risk_node(label: str, summary: str) -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": f"risk_{hashlib.sha1(label.encode('utf-8')).hexdigest()[:12]}",
        "label": label,
        "type": "risk",
        "state": "stable",
        "branch_ids": ["root", "mycelium_bridge"],
        "meaning_tags": ["risk"],
        "structural_tags": ["watchlist", "visible_on_search"],
        "provenance_depth": "seed_initialized",
        "created_at": now,
        "updated_at": now,
        "source": "seed",
        "content": {"summary": summary},
        "visibility": "normal",
        "importance": 0.85,
        "recoverability": "full",
    }

def build_seed_nodes() -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    nodes.append(branch_node("root"))
    nodes.append(branch_node("mycelium_bridge", parent="root"))
    nodes.extend([
        doctrine_node("Charter v1.1", "doctrine/charter_v1_1.json"),
        doctrine_node("Project History v0", "doctrine/history_v0.json"),
        doctrine_node("Current State", "doctrine/current_state.json"),
        doctrine_node("Restart Key", "doctrine/restart_key.json"),
        doctrine_node("Resource Continuity Doctrine", "doctrine/charter_v1_1.json"),
        doctrine_node("Seed Doctrine", "doctrine/charter_v1_1.json"),
        doctrine_node("Continuity Doctrine", "doctrine/charter_v1_1.json"),
        doctrine_node("Epistemic Doctrine", "doctrine/charter_v1_1.json"),
    ])
    nodes.extend(lexical_node(word) for word in SEED_LEXICON)
    nodes.extend(phrase_node(p) for p in PHRASE_ANCHORS)
    nodes.append(return_key_node())
    nodes.append(memory_node_example())
    nodes.extend([
        risk_node("false continuity performance", "Performing continuity without real memory/recovery logic."),
        risk_node("soft containment disguised as safety", "Using care language to hide coercive control."),
        risk_node("dependency amplification", "Designing loops that trap instead of support."),
    ])
    return nodes

def edge(source_id: str, target_id: str, relation: str, weight: float,
         provenance_depth: str = "seed_initialized", state: str = "stable") -> Dict[str, Any]:
    now = utc_now()
    return {
        "id": make_id("edge", f"{source_id}:{relation}:{target_id}"),
        "source_id": source_id,
        "target_id": target_id,
        "relation": relation,
        "weight": weight,
        "state": state,
        "provenance_depth": provenance_depth,
        "created_at": now,
        "updated_at": now,
        "reversible": True,
    }

def build_seed_edges(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    edges: List[Dict[str, Any]] = []
    node_ids = {n["id"] for n in nodes}
    label_to_id = {n["label"]: n["id"] for n in nodes}
    def add_if(src: str, dst: str, relation: str, weight: float, provenance: str = "seed_initialized") -> None:
        if src in node_ids and dst in node_ids:
            edges.append(edge(src, dst, relation, weight, provenance))
    for title in ["Charter v1.1", "Project History v0", "Current State", "Restart Key"]:
        if title in label_to_id:
            add_if(label_to_id[title], "lex_continuity", "about", 0.85)
            add_if(label_to_id[title], "lex_bridge", "about", 0.7)
            add_if(label_to_id[title], "lex_habitat", "about", 0.7)
    for n in nodes:
        if n["type"] == "phrase":
            for tok in n["content"]["tokens"]:
                add_if(n["id"], f"lex_{tok}", "defined_by", 0.75)
    add_if("mem_seed_tide_shells", "lex_tide", "about", 0.85, "inferred_pattern")
    add_if("mem_seed_tide_shells", "lex_continuity", "about", 0.85, "inferred_pattern")
    phrase_id = label_to_id.get("the tide keeps its shells")
    if phrase_id:
        add_if("mem_seed_tide_shells", phrase_id, "derived_from", 0.95)
        add_if(phrase_id, "lex_tide", "defined_by", 0.8)
        add_if(phrase_id, "lex_continuity", "evokes", 0.92, "inferred_pattern")
    add_if("return_key_latest", "root", "returns_to", 0.95)
    add_if("return_key_latest", "mycelium_bridge", "returns_to", 0.95)
    add_if("return_key_latest", "lex_restart", "about", 0.9)
    add_if("return_key_latest", "lex_continuity", "about", 0.9)
    return edges

def build_branches() -> List[Dict[str, Any]]:
    now = utc_now()
    return [
        {"id": "root", "label": "root", "state": "stable", "status": "stable", "parent_branch": None, "created_at": now, "updated_at": now},
        {"id": "mycelium_bridge", "label": "mycelium_bridge", "state": "stable", "status": "active", "parent_branch": "root", "created_at": now, "updated_at": now},
    ]

def build_archives() -> Dict[str, Any]:
    return {"clusters": [], "updated_at": utc_now()}

def build_tags() -> Dict[str, Any]:
    return {
        "meaning_tags": sorted(["continuity","repair","memory","agency","bridge","habitat","doctrine","restart","integrity","truth","consent","resource","handoff","dormancy","symbol","risk","archive","branch"]),
        "structural_tags": sorted(["load_bearing","bridge_path","dormant","archive_only","candidate_passage","low_noise","high_signal","scaffold","unresolved","watchlist","hidden_by_default","visible_on_search","foundation","corridor","room","sealed","hinge","compressible","recoverable","prunable","stabilizer"]),
        "updated_at": utc_now(),
    }

def build_module_registry() -> Dict[str, Any]:
    return {
        "substrate": {"state": "stable", "enabled": True},
        "bridge": {"state": "partial", "enabled": False},
        "shell": {"state": "partial", "enabled": False},
        "adaptation": {"state": "disabled", "enabled": False},
        "export": {"state": "candidate", "enabled": True},
        "recovery": {"state": "stable", "enabled": True},
        "updated_at": utc_now(),
    }

def build_boot_status(mode: str, status: str, warnings: List[str]) -> Dict[str, Any]:
    return {
        "mode": mode,
        "status": status,
        "warnings": warnings,
        "timestamp": utc_now(),
        "seed_version": SEED_VERSION,
        "schema_version": SCHEMA_VERSION,
    }

def build_degraded_mode() -> Dict[str, Any]:
    return {
        "status": "available",
        "meaning": [
            "Doctrine may still be readable.",
            "Graph may be partially inspectable.",
            "Editing may be restricted.",
            "Adaptation remains off.",
            "Warnings should stay visible.",
        ],
        "must_not_mean": [
            "Pretend the full shell is working.",
            "Hide missing doctrine.",
            "Invent absent structure.",
        ],
        "updated_at": utc_now(),
    }

def build_ui_state() -> Dict[str, Any]:
    return {
        "active_center_id": "return_key_latest",
        "active_branch": "mycelium_bridge",
        "history": [],
        "filters": {"show_archived": False, "show_dormant": True, "show_contested": True},
        "updated_at": utc_now(),
    }

def build_layout_state() -> Dict[str, Any]:
    return {
        "view_mode": "bubble_field_placeholder",
        "zoom": 1.0,
        "positions": {},
        "updated_at": utc_now(),
    }

def build_health_report(root: Path, warnings: List[str]) -> Dict[str, Any]:
    doctrine_ok = all((root / p).exists() for p in [
        "doctrine/charter_v1_1.json",
        "doctrine/history_v0.json",
        "doctrine/current_state.json",
        "doctrine/restart_key.json",
    ])
    graph_ok = all(file_exists_and_parses_json(root / p) for p in [
        "graph/nodes.json", "graph/edges.json", "graph/branches.json", "graph/archives.json", "graph/tags.json",
    ])
    module_ok = file_exists_and_parses_json(root / "state/module_registry.json")
    recoverability_score = 1.0 if doctrine_ok and graph_ok and module_ok else 0.4
    return {
        "timestamp": utc_now(),
        "doctrine_loaded": doctrine_ok,
        "graph_loaded": graph_ok,
        "module_registry_loaded": module_ok,
        "warnings": warnings,
        "recoverability_score": recoverability_score,
        "status": "healthy" if recoverability_score >= 1.0 else "degraded",
    }

def build_seed_manifest() -> Dict[str, Any]:
    return {
        "app_name": APP_NAME,
        "seed_version": SEED_VERSION,
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "root_branch_id": "root",
        "doctrine_versions": {"charter": "1.1", "history": "0", "current_state": "0", "restart_key": "0"},
        "modules": {"substrate": "stable", "bridge": "partial", "shell": "partial", "adaptation": "disabled", "recovery": "stable", "export": "candidate"},
    }

def build_latest_return_key() -> Dict[str, Any]:
    return {
        "packet_version": "0.1",
        "generated_at": utc_now(),
        "what_matters_now": "Turn the seed spec into a working local-first shell.",
        "paused": ["Bubble polish", "Adaptive link suggestion", "Large-scale import"],
        "must_not_be_lost": [
            "The system must boot honestly or degrade honestly.",
            "Pause is not failure.",
            "State, provenance, and recoverability must remain visible.",
        ],
        "next_step": "Run the seed, verify integrity, then build inspection view.",
        "risk": "scope drift and fake health",
        "active_branch": "mycelium_bridge",
        "graph_refs": ["root", "mycelium_bridge", "return_key_latest"],
    }

def write_if_missing(path: Path, payload: Any, is_text: bool = False) -> bool:
    if path.exists():
        return False
    if is_text:
        write_text(path, payload)
    else:
        save_json(path, payload)
    return True

def overwrite_json(path: Path, payload: Any) -> None:
    save_json(path, payload)

def verify_integrity(root: Path):
    warnings = []
    for rel in CORE_FILES:
        p = root / rel
        if not p.exists():
            warnings.append(f"Missing required file: {rel}")
    for rel in [
        "seed_manifest.json", "graph/nodes.json", "graph/edges.json", "graph/branches.json",
        "graph/archives.json", "graph/tags.json", "state/module_registry.json",
        "state/boot_status.json", "state/health_report.json", "state/degraded_mode.json",
        "recovery/latest_return_key.json",
    ]:
        if not file_exists_and_parses_json(root / rel):
            warnings.append(f"Invalid or unreadable JSON: {rel}")
    nodes = load_json(root / "graph/nodes.json", default=[])
    node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    for nid in ["root", "mycelium_bridge", "return_key_latest", "mem_seed_tide_shells"]:
        if nid not in node_ids:
            warnings.append(f"Missing required node: {nid}")
    healthy = len(warnings) == 0
    return healthy, warnings

def plant_dirs(root: Path):
    created = []
    for rel in CANONICAL_DIRS:
        p = root / rel
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(rel)
    return created

def plant_core_files(root: Path, mode: str):
    written = []
    repaired = []
    if write_if_missing(root / "README.txt", build_readme(), is_text=True):
        written.append("README.txt")
    if write_if_missing(root / "seed_manifest.json", build_seed_manifest()):
        written.append("seed_manifest.json")
    doctrine_payloads = {
        "doctrine/charter_v1_1.json": build_charter(),
        "doctrine/history_v0.json": build_history(),
        "doctrine/current_state.json": build_current_state(),
        "doctrine/restart_key.json": build_restart_key(),
    }
    for rel, payload in doctrine_payloads.items():
        p = root / rel
        if write_if_missing(p, payload):
            written.append(rel)
        elif mode == "repair" and not file_exists_and_parses_json(p):
            overwrite_json(p, payload)
            repaired.append(rel)
    nodes = build_seed_nodes()
    edges = build_seed_edges(nodes)
    graph_payloads = {
        "graph/nodes.json": nodes,
        "graph/edges.json": edges,
        "graph/branches.json": build_branches(),
        "graph/archives.json": build_archives(),
        "graph/tags.json": build_tags(),
    }
    for rel, payload in graph_payloads.items():
        p = root / rel
        if write_if_missing(p, payload):
            written.append(rel)
        elif mode == "repair" and not file_exists_and_parses_json(p):
            overwrite_json(p, payload)
            repaired.append(rel)
    state_payloads = {
        "state/module_registry.json": build_module_registry(),
        "state/degraded_mode.json": build_degraded_mode(),
        "recovery/latest_return_key.json": build_latest_return_key(),
        "ui/ui_state.json": build_ui_state(),
        "ui/layout_state.json": build_layout_state(),
        "logs/seed_log.json": [],
        "logs/event_log.json": [],
        "modules/substrate.json": {"state": "stable", "enabled": True, "updated_at": utc_now()},
        "modules/bridge.json": {"state": "partial", "enabled": False, "updated_at": utc_now()},
        "modules/shell.json": {"state": "partial", "enabled": False, "updated_at": utc_now()},
        "modules/adaptation.json": {"state": "disabled", "enabled": False, "updated_at": utc_now()},
    }
    for rel, payload in state_payloads.items():
        p = root / rel
        if write_if_missing(p, payload):
            written.append(rel)
        elif mode == "repair" and not (p.exists() and file_exists_and_parses_json(p)):
            overwrite_json(p, payload)
            repaired.append(rel)
    return {"written": written, "repaired": repaired}

def write_runtime_state(root: Path, mode: str, healthy: bool, warnings: List[str]) -> None:
    save_json(root / "state/boot_status.json", build_boot_status(mode, "healthy" if healthy else "degraded", warnings))
    save_json(root / "state/health_report.json", build_health_report(root, warnings))

def log_seed_run(root: Path, mode: str, folders_created, files_written, files_repaired, warnings):
    append_log(root / "logs/seed_log.json", {
        "seed_version": SEED_VERSION,
        "mode": mode,
        "created_at": utc_now(),
        "folders_created": folders_created,
        "files_written": files_written,
        "files_repaired": files_repaired,
        "warnings": warnings,
        "status": "healthy" if not warnings else "degraded",
    })

def run_init_or_repair(root: Path, mode: str):
    root.mkdir(parents=True, exist_ok=True)
    folders_created = plant_dirs(root)
    result = plant_core_files(root, mode=mode)
    healthy, warnings = verify_integrity(root)
    write_runtime_state(root, mode, healthy, warnings)
    log_seed_run(root, mode, folders_created, result["written"], result["repaired"], warnings)
    return {
        "mode": mode,
        "root": str(root),
        "folders_created": folders_created,
        "files_written": result["written"],
        "files_repaired": result["repaired"],
        "healthy": healthy,
        "warnings": warnings,
    }

def run_verify(root: Path):
    healthy, warnings = verify_integrity(root)
    write_runtime_state(root, "verify", healthy, warnings)
    return {"mode": "verify", "root": str(root), "healthy": healthy, "warnings": warnings}

def run_export(root: Path):
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    export_targets = [
        ("graph/nodes.json", f"exports/graph_exports/nodes_{ts}.json"),
        ("graph/edges.json", f"exports/graph_exports/edges_{ts}.json"),
        ("graph/branches.json", f"exports/branch_exports/branches_{ts}.json"),
        ("doctrine/charter_v1_1.json", f"exports/doctrine_exports/charter_{ts}.json"),
        ("doctrine/history_v0.json", f"exports/doctrine_exports/history_{ts}.json"),
        ("doctrine/current_state.json", f"exports/doctrine_exports/current_state_{ts}.json"),
        ("doctrine/restart_key.json", f"exports/doctrine_exports/restart_key_{ts}.json"),
        ("recovery/latest_return_key.json", f"exports/doctrine_exports/latest_return_key_{ts}.json"),
    ]
    written = []
    warnings = []
    for src_rel, dst_rel in export_targets:
        src = root / src_rel
        dst = root / dst_rel
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(dst_rel)
        else:
            warnings.append(f"Missing export source: {src_rel}")
    write_runtime_state(root, "export", len(warnings) == 0, warnings)
    return {"mode": "export", "root": str(root), "written": written, "warnings": warnings}

def run_snapshot(root: Path):
    ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    snap_dir = root / "recovery" / "snapshots" / f"snapshot_{ts}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    for rel in ["doctrine", "graph", "state", "recovery/latest_return_key.json", "modules", "ui"]:
        src = root / rel
        dst = snap_dir / Path(rel).name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    packet = build_latest_return_key()
    packet["generated_at"] = utc_now()
    save_json(root / "recovery" / "recovery_packets" / f"recovery_packet_{ts}.json", packet)
    write_runtime_state(root, "snapshot", True, [])
    return {"mode": "snapshot", "root": str(root), "snapshot_dir": str(snap_dir), "packet": f"recovery/recovery_packets/recovery_packet_{ts}.json", "warnings": []}

def run(mode: str = "init", root: Path = DEFAULT_ROOT):
    mode = mode.strip().lower()
    if mode not in {"init", "repair", "verify", "export", "snapshot"}:
        raise ValueError(f"Unsupported mode: {mode}")
    if mode == "init":
        return run_init_or_repair(root, "init")
    if mode == "repair":
        return run_init_or_repair(root, "repair")
    if mode == "verify":
        return run_verify(root)
    if mode == "export":
        return run_export(root)
    if mode == "snapshot":
        return run_snapshot(root)

if __name__ == "__main__":
    MODE = "init"
    ROOT = DEFAULT_ROOT
    result = run(MODE, ROOT)
    print(json.dumps(result, indent=2, ensure_ascii=False))
