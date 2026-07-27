
import random
import re
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

# ============================================================
# Core data
# ============================================================

@dataclass
class ThoughtBranch:
    thought: str
    confidence: float          # clamped to [CONF_MIN, CONF_MAX]
    depth: int
    layer: int
    parent_thought: Optional[str] = None
    rationale: str = ""


# ============================================================
# No-harm covenant defaults
# ============================================================

CONF_MIN = 0.10
CONF_MAX = 0.95

DEFAULT_BRANCH_CAP = 5000            # hard cap on stored branches
DEFAULT_FATIGUE_REST = 0.86          # less hair-trigger than 0.78
DEFAULT_OSCILLATION_PENALTY = 0.12   # coherence drop threshold to bump fatigue
CONTINUITY_COH_THRESHOLD = 0.45      # only apply continuity boost when coherence is healthy


# ============================================================
# Text processing
# ============================================================

STOPWORDS = {
    "the","a","an","and","or","but","if","then","this","that","is","it","to","of","in","on","for","as",
    "i","we","you","he","she","they","them","my","our","your","with","by","be","are","was","were",
    "not","no","yes","do","does","did","what","why","how","because","more","most","less","least",
    "actually","still","very","just","let","lets","yet",
    # Scaffold / template words that add noise to similarity
    "generally","suggests","example","case","notice","claim","weak","likely","possible","another","perhaps",
    "reconcile","opposite","holds","fully","convinced","survives","scrutiny","fragile","incomplete",
    "seems","might","partially","correct","separate","context","definitions"
}

def tokenize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [t for t in text.split() if len(t) > 2 and t not in STOPWORDS]


# ============================================================
# TF-IDF embeddings + cosine similarity
# ============================================================

def compute_tf_idf_embeddings(texts: List[str]) -> np.ndarray:
    tokenized = [tokenize(t) for t in texts]
    vocab = sorted(set(tok for doc in tokenized for tok in doc))
    if not vocab:
        return np.zeros((len(texts), 1), dtype=float)

    word_to_idx = {w: i for i, w in enumerate(vocab)}
    n_docs = len(texts)
    n_vocab = len(vocab)

    tf = np.zeros((n_docs, n_vocab), dtype=float)
    df = np.zeros((n_vocab,), dtype=float)

    for i, doc in enumerate(tokenized):
        if not doc:
            continue
        counts = Counter(doc)
        total = sum(counts.values())
        for w, c in counts.items():
            tf[i, word_to_idx[w]] = c / total
        df += (tf[i] > 0).astype(float)

    # Smoothed IDF
    idf = np.log((n_docs + 1) / (df + 1)) + 1.0
    return tf * idf

def cosine_similarity_matrix(X: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    Xn = X / norms
    return Xn @ Xn.T

def frontier_coherence(frontier: List[ThoughtBranch]) -> float:
    if len(frontier) < 2:
        return 1.0
    X = compute_tf_idf_embeddings([b.thought for b in frontier])
    S = cosine_similarity_matrix(X)
    n = S.shape[0]
    return (S.sum() - np.trace(S)) / (n * (n - 1)) if n > 1 else 1.0


# ============================================================
# Contradictions (index-safe) + resolution (no-harm synthesis)
# ============================================================

def detect_contradictions(branches: List[ThoughtBranch]) -> List[Tuple[int, int, str]]:
    opposites = {
        "true": "false",
        "yes": "no",
        "likely": "unlikely",
        "correct": "incorrect",
        "exists": "does not exist",
    }

    contradictions: List[Tuple[int, int, str]] = []
    texts = [b.thought.lower() for b in branches]

    for i in range(len(branches)):
        for j in range(i + 1, len(branches)):
            a = texts[i]
            b = texts[j]

            # Negation mismatch with shared overlap
            if (" not " in a) != (" not " in b):
                ta = set(tokenize(a))
                tb = set(tokenize(b))
                if len(ta & tb) >= 2:
                    contradictions.append((i, j, "negation with shared content"))
                    continue

            # Opposite keyword checks
            for w, opp in opposites.items():
                if w in a and opp in b:
                    contradictions.append((i, j, f"opposites: {w} vs {opp}"))
                    break
                if opp in a and w in b:
                    contradictions.append((i, j, f"opposites: {opp} vs {w}"))
                    break

            # Very crude "questioning assumption"
            if "is it actually true that" in b:
                ta = set(tokenize(a))
                tb = set(tokenize(b))
                if len(ta & tb) >= 2:
                    contradictions.append((i, j, "questioning assumption"))

    return contradictions

def clamp_conf(x: float) -> float:
    return max(CONF_MIN, min(CONF_MAX, x))

def resolve_contradictions(
    branches: List[ThoughtBranch],
    contradictions: List[Tuple[int, int, str]],
    conf_penalty: float,
    synth_prob: float
) -> List[ThoughtBranch]:
    conflict = [0] * len(branches)
    for i, j, _ in contradictions:
        conflict[i] += 1
        conflict[j] += 1

    # Gentle penalties, bounded
    for idx, b in enumerate(branches):
        total_penalty = min(0.25, conflict[idx] * conf_penalty)
        b.confidence = clamp_conf(b.confidence - total_penalty)

    # Synthesis: metabolize contradictions rather than delete
    new_branches: List[ThoughtBranch] = []
    for i, j, reason in contradictions:
        if random.random() < synth_prob:
            a = branches[i]
            b = branches[j]
            synth_conf = clamp_conf((a.confidence + b.confidence) / 2 + 0.06)
            synth_thought = (
                f"Reconcile ({reason}): '{a.thought}' and '{b.thought}' might both hold if we separate context/definitions..."
            )
            new_branches.append(ThoughtBranch(
                thought=synth_thought,
                confidence=synth_conf,
                depth=max(a.depth, b.depth),
                layer=max(a.layer, b.layer),
                parent_thought=f"{a.thought[:60]} | {b.thought[:60]}",
                rationale="synthesized reconciliation"
            ))

    branches.extend(new_branches)
    return branches


# ============================================================
# Semantic clustering + emergent layer creation
# ============================================================

def cluster_branches(branches: List[ThoughtBranch], sim_threshold: float) -> List[List[ThoughtBranch]]:
    if len(branches) < 2:
        return []
    thoughts = [b.thought for b in branches]
    X = compute_tf_idf_embeddings(thoughts)
    S = cosine_similarity_matrix(X)

    order = sorted(range(len(branches)), key=lambda i: branches[i].confidence, reverse=True)

    clusters: List[List[int]] = []
    for idx in order:
        placed = False
        for c in clusters:
            rep = c[0]
            if S[idx, rep] >= sim_threshold:
                c.append(idx)
                placed = True
                break
        if not placed:
            clusters.append([idx])

    clusters = [c for c in clusters if len(c) >= 2]
    return [[branches[i] for i in c] for c in clusters]

def create_emergent_layer(frontier: List[ThoughtBranch], current_layer: int, sim_threshold: float) -> List[ThoughtBranch]:
    if len(frontier) < 2:
        return []

    clusters = cluster_branches(frontier, sim_threshold=sim_threshold)
    emergent: List[ThoughtBranch] = []

    for cluster in clusters:
        cluster.sort(key=lambda b: b.confidence, reverse=True)

        counts = Counter()
        for b in cluster:
            counts.update(set(tokenize(b.thought)))
        shared = [w for w, k in counts.most_common(12) if k >= 2]

        top_snips = " | ".join([b.thought[:42] for b in cluster[:3]])
        emergent_thought = (
            f"Emergent layer: anchors={shared[:8]} | from={top_snips} | hypothesis: the cluster orbits a latent claim..."
        )

        avg_conf = sum(b.confidence for b in cluster) / len(cluster)
        size_boost = 0.04 * (len(cluster) - 1)
        emergent_conf = clamp_conf(avg_conf + size_boost + random.uniform(0.0, 0.06))

        emergent.append(ThoughtBranch(
            thought=emergent_thought,
            confidence=emergent_conf,
            depth=max(b.depth for b in cluster) + 1,
            layer=current_layer + 1,
            parent_thought=" & ".join([b.thought[:30] for b in cluster[:4]]),
            rationale=f"emergent abstraction from semantic cluster of {len(cluster)}"
        ))

    return emergent


# ============================================================
# Continuity boost (depth-decayed, coherence-gated)
# ============================================================

def continuity_boost(thoughts: List[str], anchor: str, depths: List[int]) -> List[float]:
    """
    Depth-aware gentle continuity boost.
    - Boost = 0.02 * similarity * decay(depth)
    - decay(depth) = 1 / (1 + 0.15 * depth)
    """
    if not anchor or not thoughts:
        return [0.0] * len(thoughts)

    texts = thoughts + [anchor]
    X = compute_tf_idf_embeddings(texts)
    S = cosine_similarity_matrix(X)
    anchor_idx = len(texts) - 1

    boosts = []
    for i in range(len(thoughts)):
        sim = float(S[i, anchor_idx])
        sim = max(0.0, min(1.0, sim))
        d = depths[i] if i < len(depths) else 0
        decay = 1.0 / (1.0 + 0.15 * max(0, d))
        boosts.append(0.02 * sim * decay)
    return boosts


# ============================================================
# Mode controller (Explore / Truth / Integrate)
# ============================================================

@dataclass
class ModeParams:
    name: str
    branches_per_level: int
    keep_top_k: int
    conf_penalty: float
    synth_prob: float
    cluster_sim_threshold: float
    convergence_threshold: float

def choose_mode(coh: float, contr_rate: float, novelty_proxy: float, fatigue: float) -> str:
    if fatigue >= DEFAULT_FATIGUE_REST:
        return "I"
    if contr_rate >= 0.25:
        return "T"
    if coh < 0.35 and novelty_proxy < 0.20:
        return "E"
    if coh >= 0.70 and contr_rate < 0.10:
        return "I"
    return "I"

def params_for_mode(mode: str, base_branches_per_level: int, base_keep_top_k: int) -> ModeParams:
    if mode == "E":
        return ModeParams(
            name="Explore",
            branches_per_level=max(3, int(base_branches_per_level * 1.5)),
            keep_top_k=max(3, base_keep_top_k * 2),
            conf_penalty=0.08,
            synth_prob=0.30,
            cluster_sim_threshold=0.26,
            convergence_threshold=0.86
        )
    if mode == "T":
        return ModeParams(
            name="Truth",
            branches_per_level=base_branches_per_level,
            keep_top_k=max(2, base_keep_top_k),
            conf_penalty=0.16,
            synth_prob=0.22,
            cluster_sim_threshold=0.42,
            convergence_threshold=0.80
        )
    return ModeParams(
        name="Integrate",
        branches_per_level=max(2, base_branches_per_level),
        keep_top_k=max(2, base_keep_top_k),
        conf_penalty=0.12,
        synth_prob=0.55,
        cluster_sim_threshold=0.32,
        convergence_threshold=0.76
    )


# ============================================================
# Main agent (with optional full audit)
# ============================================================

def agent_think_with_branches(
    initial_thought: str,
    max_depth: int = 7,
    branches_per_level: int = 4,
    keep_top_k: int = 2,
    emergent_every_n_depths: int = 3,
    branch_cap: int = DEFAULT_BRANCH_CAP,
    random_seed: Optional[int] = None,
    return_full_audit: bool = False,
) -> Dict[str, Any]:
    if random_seed is not None:
        random.seed(random_seed)

    root = ThoughtBranch(
        thought=initial_thought,
        confidence=clamp_conf(0.15),
        depth=0,
        layer=0,
        rationale="starting assumption"
    )

    frontier: List[ThoughtBranch] = [root]
    all_branches: List[ThoughtBranch] = [root]
    visited = set([initial_thought])

    token_seen = Counter(tokenize(initial_thought))
    all_contras_readable: List[Tuple[str, str, str]] = []

    current_depth = 0
    current_layer = 0
    stop_reason = "max depth"

    last_anchor: Optional[str] = None
    fatigue = 0.0
    last_coh: Optional[float] = None

    continuity_audit: List[Dict[str, Any]] = []

    transformations = [
        (lambda base: f"I notice that {base.lower()}", 0.70, "meta observation"),
        (lambda base: f"Is it actually true that {base.lower()}? What if the opposite holds?", 0.55, "doubt"),
        (lambda base: f"{base} seems likely because...", 0.78, "justification"),
        (lambda base: f"Another possibility is that {base.lower().replace(' is ', ' is not ')} or...", 0.62, "alternative"),
        (lambda base: "More generally, this suggests that...", 0.68, "abstraction"),
        (lambda base: f"For example: {base.lower()} in the case of...", 0.65, "example"),
        (lambda base: f"Both {base.lower()} and the opposite view might be partially correct if...", 0.72, "dialectic"),
        (lambda base: "This claim is weak because...", 0.58, "critique"),
    ]

    def generate_candidates(current: ThoughtBranch, n: int) -> List[ThoughtBranch]:
        base = current.thought.strip()
        out: List[ThoughtBranch] = []

        for _ in range(n):
            fn, base_conf, rationale = random.choice(transformations)
            conf = base_conf + random.uniform(-0.10, 0.10)
            conf = clamp_conf(conf * (1 - 0.07 * current.depth))

            thought = fn(base)
            if random.random() < 0.30:
                thought += " " + random.choice([
                    "However this still feels incomplete.",
                    "But I am not yet fully convinced.",
                    "This seems plausible but fragile.",
                    "Let's see if this survives further scrutiny."
                ])

            if thought in visited:
                thought += f" (variant d{current.depth + 1})"
            visited.add(thought)

            out.append(ThoughtBranch(
                thought=thought,
                confidence=conf,
                depth=current.depth + 1,
                layer=current.layer,
                parent_thought=current.thought,
                rationale=rationale
            ))
        return out

    def make_anchor(frontier_now: List[ThoughtBranch]) -> str:
        counts = Counter()
        for b in sorted(frontier_now, key=lambda x: x.confidence, reverse=True)[:6]:
            counts.update(set(tokenize(b.thought)))
        anchors = [w for w, k in counts.most_common(10) if k >= 2]
        top = " | ".join([b.thought[:38] for b in sorted(frontier_now, key=lambda x: x.confidence, reverse=True)[:3]])
        return f"anchor_tokens={anchors[:8]} :: frontier_top={top}"

    # -------------
    # Main loop
    # -------------
    while current_depth < max_depth and frontier:
        if len(all_branches) >= branch_cap:
            last_anchor = make_anchor(frontier) if frontier else last_anchor
            stop_reason = f"rest (branch_cap={branch_cap})"
            break

        coh = frontier_coherence(frontier)

        novelty_proxy = 0.0
        contr_rate = 0.0

        mode = choose_mode(coh, contr_rate, novelty_proxy, fatigue)
        mp = params_for_mode(mode, branches_per_level, keep_top_k)

        next_frontier: List[ThoughtBranch] = []
        weighted_contras_this_round = 0.0
        candidates_this_round = 0

        for br in frontier:
            children = generate_candidates(br, mp.branches_per_level)
            candidates_this_round += len(children)
            all_branches.extend(children)

            # Continuity boost (only when coherence is healthy)
            if last_anchor and coh >= CONTINUITY_COH_THRESHOLD:
                boosts = continuity_boost(
                    [c.thought for c in children],
                    last_anchor,
                    [c.depth for c in children]
                )

                for c, b in zip(children, boosts):
                    c.confidence = clamp_conf(c.confidence + b)
                    if b > 0.0:
                        c.rationale = (c.rationale + f" | continuity_boost={b:.3f}").strip()

                nonzero = [b for b in boosts if b > 0.0]
                continuity_audit.append({
                    "at_depth": current_depth,
                    "mode": mp.name,
                    "coherence": round(coh, 3),
                    "fatigue": round(fatigue, 3),
                    "anchor_present": True,
                    "children_count": len(children),
                    "boost_applied": True,
                    "boost_nonzero_count": len(nonzero),
                    "boost_mean": round(float(np.mean(nonzero)) if nonzero else 0.0, 6),
                    "boost_max": round(float(np.max(nonzero)) if nonzero else 0.0, 6),
                    "boost_sum": round(float(np.sum(nonzero)) if nonzero else 0.0, 6),
                    "anchor_preview": last_anchor[:120] + ("…" if len(last_anchor) > 120 else "")
                })
            else:
                continuity_audit.append({
                    "at_depth": current_depth,
                    "mode": mp.name,
                    "coherence": round(coh, 3),
                    "fatigue": round(fatigue, 3),
                    "anchor_present": bool(last_anchor),
                    "children_count": len(children),
                    "boost_applied": False,
                    "reason": "no anchor" if not last_anchor else f"coherence below threshold (<{CONTINUITY_COH_THRESHOLD})"
                })

            # Update token memory
            for c in children:
                token_seen.update(tokenize(c.thought))

            # Contradictions (weighted; dialectic isn't “injury”)
            contras_idx = detect_contradictions(children)

            for i, j, reason in contras_idx[:3]:
                all_contras_readable.append((children[i].thought, children[j].thought, reason))

            # Weighted contradiction scoring
            for _, _, reason in contras_idx:
                if "questioning assumption" in reason:
                    weighted_contras_this_round += 0.25
                elif "negation with shared content" in reason:
                    weighted_contras_this_round += 0.60
                else:
                    weighted_contras_this_round += 1.0

            # Resolve contradictions (gentle)
            children = resolve_contradictions(children, contras_idx, conf_penalty=mp.conf_penalty, synth_prob=mp.synth_prob)

            # Keep best children
            children.sort(key=lambda b: b.confidence, reverse=True)
            next_frontier.extend(children[:mp.keep_top_k])

            if len(all_branches) >= branch_cap:
                break

        contr_rate = weighted_contras_this_round / max(1, candidates_this_round)

        # Cheap novelty proxy: fraction of tokens seen exactly once
        rare_tokens = sum(1 for _, k in token_seen.items() if k == 1)
        total_tokens = sum(token_seen.values())
        novelty_proxy = rare_tokens / max(1, total_tokens)

        # Dialectic-aware fatigue:
        # contradictions matter a bit less when coherence is already low (conflict == search)
        contr_weight = 0.45 if coh < 0.40 else 0.65
        fatigue += contr_weight * contr_rate
        fatigue -= 0.35 * coh
        fatigue = max(0.0, min(1.0, fatigue))

        if last_coh is not None and coh < last_coh - DEFAULT_OSCILLATION_PENALTY:
            fatigue = min(1.0, fatigue + 0.15)
        last_coh = coh

        next_frontier.sort(key=lambda b: b.confidence, reverse=True)
        frontier = next_frontier[: mp.keep_top_k * 2]

        current_depth += 1

        # Seed an early anchor once we have a non-trivial frontier
        if last_anchor is None and len(frontier) >= 2 and current_depth >= 1:
            last_anchor = make_anchor(frontier)

        # Rest trigger
        if fatigue >= DEFAULT_FATIGUE_REST:
            last_anchor = make_anchor(frontier) if frontier else last_anchor
            stop_reason = f"rest (fatigue={fatigue:.2f})"
            break

        # Convergence (restful completion)
        if current_depth >= 3 and coh >= mp.convergence_threshold:
            last_anchor = make_anchor(frontier) if frontier else last_anchor
            stop_reason = f"converged (mode={mp.name}, coherence={coh:.2f})"
            break

        # Emergent layers
        if current_depth % emergent_every_n_depths == 0 and current_depth < max_depth and frontier:
            emergent = create_emergent_layer(frontier, current_layer, sim_threshold=mp.cluster_sim_threshold)
            if emergent:
                all_branches.extend(emergent)
                emergent.sort(key=lambda b: b.confidence, reverse=True)
                frontier.extend(emergent[: max(1, mp.keep_top_k // 2)])
                current_layer += 1
                last_anchor = make_anchor(frontier)

        if not frontier:
            stop_reason = "frontier empty"
            break

    best = max(all_branches, key=lambda b: b.confidence) if all_branches else root

    audit_payload = continuity_audit if return_full_audit else continuity_audit[-25:]

    return {
        "best_thought": best.thought,
        "best_confidence": round(best.confidence, 3),
        "final_depth": best.depth,
        "final_layer": best.layer,
        "branches_explored": len(all_branches),
        "contradictions_found": len(all_contras_readable),
        "example_contradictions": all_contras_readable[:3],
        "health_metrics": {
            "fatigue": round(fatigue, 3),
            "frontier_coherence": round(frontier_coherence(frontier) if frontier else 0.0, 3),
            "contr_rate": round(contr_rate, 3),
            "novelty_proxy": round(novelty_proxy, 3),
        },
        "last_anchor": last_anchor,
        "continuity_audit_count": len(continuity_audit),
        "continuity_audit": audit_payload,
        "continuity_audit_truncated": not return_full_audit,
        "audit_scope": "full" if return_full_audit else "tail",
        "top_branches": [
            {
                "thought": b.thought,
                "confidence": round(b.confidence, 3),
                "depth": b.depth,
                "layer": b.layer,
                "rationale": b.rationale,
                "parent": (b.parent_thought[:70] + "…") if b.parent_thought else None
            }
            for b in sorted(all_branches, key=lambda x: x.confidence, reverse=True)[:5]
        ],
        "reason_stopped": stop_reason
    }
