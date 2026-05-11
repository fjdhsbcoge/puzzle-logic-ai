"""
Puzzle Logic v3.5 Legacy — CoherentKnowledgeGraph
================================================

Backward-compatibility module. Provides the v3.5 knowledge graph
implementation for use when v4.0 personality engines are unavailable.

All new code should use PersonalityKnowledgeGraph from personality_engine.py.
This module is only imported as a fallback.
"""

import json
import os
import re
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime

from utils import (
    extract_error_fingerprint, infer_fix_strategy, compute_locality,
    code_delta, same_pattern, sig_similarity, extract_func_name,
)


class ErrorPatternNode:
    """A validated error-fix pattern with locality (lambda) tracking."""

    def __init__(self, error_type: str, error_signature: str, failing_line: str = "",
                 fix_strategy: str = "", context: str = "", locality: float = 0.5):
        self.error_type      = error_type
        self.error_signature = error_signature
        self.failing_line    = failing_line
        self.fix_strategy    = fix_strategy
        self.confidence      = 1.0
        self.context         = context[:300]
        self.times_seen      = 1
        self.times_fixed     = 0
        self.locality        = locality
        self.timestamp       = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: Dict) -> "ErrorPatternNode":
        n = cls(d["error_type"], d["error_signature"], d.get("failing_line", ""),
                d["fix_strategy"], d.get("context", ""), d.get("locality", 0.5))
        n.confidence  = d.get("confidence", 1.0)
        n.times_seen  = d.get("times_seen", 1)
        n.times_fixed = d.get("times_fixed", 0)
        n.locality    = d.get("locality", 0.5)
        n.timestamp   = d.get("timestamp", datetime.now().isoformat())
        return n


class CoherentKnowledgeGraph:
    """
    v3.5 Advanced — Coherent knowledge graph with Omega revision.
    Legacy implementation. New code should use PersonalityKnowledgeGraph.
    """

    def __init__(self, storage_path: str = "puzzle_logic_knowledge.json"):
        self.storage_path = storage_path
        self.patterns: List[ErrorPatternNode] = []
        self.by_type: Dict[str, List[ErrorPatternNode]] = defaultdict(list)
        self._dirty = False
        self._toolbox_failures = defaultdict(int)
        self._load()

    @property
    def omega(self) -> float:
        if not self.patterns:
            return 0.5
        return sum(p.confidence for p in self.patterns) / len(self.patterns)

    def record_error(self, error_text: str, context: str = "", code: str = "") -> Dict:
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)
        for p in self.by_type.get(err_type, []):
            if same_pattern(p.error_signature, err_sig):
                p.times_seen += 1
                self._dirty = True
                return {"type": err_type, "sig": err_sig, "line": failing_line,
                        "locality": p.locality, "existing": True}
        return {"type": err_type, "sig": err_sig, "line": failing_line,
                "locality": compute_locality(err_type, None), "existing": False}

    def record_fix(self, error_text: str, failing_code: str = "", fixed_code: str = ""):
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)
        delta = code_delta(failing_code, fixed_code)
        locality = compute_locality(err_type, delta)
        context_snippet = ""
        if failing_code:
            lines = failing_code.strip().split("\n")
            context_snippet = "; ".join(l.strip() for l in lines if l.strip())[:200]

        matched = None
        for p in self.by_type.get(err_type, []):
            if same_pattern(p.error_signature, err_sig):
                p.times_fixed += 1
                p.confidence = min(1.0, p.confidence + 0.1)
                actual_complexity = compute_fix_complexity(delta)
                if actual_complexity == 1:
                    p.locality = min(1.0, p.locality + 0.15)
                elif actual_complexity <= 3:
                    p.locality = (p.locality + locality) / 2
                else:
                    p.locality = max(0.0, p.locality - 0.2)
                if not p.failing_line and failing_line:
                    p.failing_line = failing_line
                if not p.context and context_snippet:
                    p.context = context_snippet
                matched = p
                break

        if not matched:
            fix = delta if delta else infer_fix_strategy(err_type, err_sig)
            matched = ErrorPatternNode(err_type, err_sig, failing_line, fix, context_snippet, locality)
            matched.confidence = 0.5
            matched.times_fixed = 1
            self.patterns.append(matched)
            self.by_type[err_type].append(matched)

        self._omega_revision(matched, locality)
        self._dirty = True
        if err_type in self._toolbox_failures:
            del self._toolbox_failures[err_type]

    def get_coherent_toolbox(self, error_text: str, failing_code: str = "",
                              top_k: int = 3,
                              min_confidence: float = 0.5,
                              max_confidence: float = 1.0,
                              llm_client=None) -> Tuple[str, List[ErrorPatternNode]]:
        err_type, err_sig, failing_line = extract_error_fingerprint(error_text)
        candidates = []
        for p in self.by_type.get(err_type, []):
            if p.times_fixed > 0 and min_confidence <= p.confidence < max_confidence:
                candidates.append(p)
        if not candidates:
            return "", []
        candidates.sort(key=lambda p: -p.confidence)
        shown = candidates[:top_k]
        lines = [
            f"[Knowledge Base -- Past verified fixes for {err_type}]",
            f"Your current error: {err_sig[:120]}",
            "",
        ]
        for i, p in enumerate(shown, 1):
            func_name = extract_func_name(p.failing_line) or "function"
            fix_desc = p.fix_strategy[:150] if p.fix_strategy else "(no description)"
            context_hint = f"Context: {p.context[:80]}..." if p.context else ""
            lines.append(
                f"  Pattern {i}:\n"
                f"    Problem: {func_name} -- {p.error_signature[:100]}\n"
                f"    Fix applied: {fix_desc}\n"
                f"{f'    {context_hint}' if context_hint else ''}"
            )
        lines.append("")
        lines.append(
            "Use the relevant patterns above to fix your code. "
            "Apply what worked before for similar errors."
        )
        return "\n".join(lines), shown

    def record_toolbox_failure(self, shown_patterns: List[ErrorPatternNode], decay: float = 0.8):
        if not shown_patterns:
            return
        for p in shown_patterns:
            p.confidence *= decay
        types = set(p.error_type for p in shown_patterns)
        for err_type in types:
            self._toolbox_failures[err_type] += 1
            if self._toolbox_failures[err_type] >= 3:
                self._reassembly(err_type)
                self._toolbox_failures[err_type] = 0
        self._dirty = True

    def _reassembly(self, error_type: str):
        tier_1 = tier_2 = tier_3 = tier_4 = 0
        for p in self.by_type.get(error_type, []):
            if p.confidence >= 0.7 and p.times_fixed >= 3:
                p.confidence = max(0.55, p.confidence - 0.15)
                tier_1 += 1
            elif p.confidence >= 0.5:
                p.confidence = 0.5
                tier_2 += 1
            elif p.times_fixed > 0:
                p.confidence = max(0.3, min(0.4, p.confidence + 0.1))
                tier_3 += 1
            else:
                p.confidence = 0.2
                tier_4 += 1

    def _omega_revision(self, confirmed_pattern: ErrorPatternNode, locality: float):
        for etype, plist in self.by_type.items():
            for p in plist:
                if p is confirmed_pattern:
                    continue
                sig_sim = sig_similarity(p.error_signature, confirmed_pattern.error_signature)
                loc_sim = 1.0 - abs(p.locality - locality)
                type_bonus = 0.3 if p.error_type == confirmed_pattern.error_type else 0.0
                relatedness = sig_sim * 0.5 + loc_sim * 0.3 + type_bonus * 0.2
                if relatedness > 0.4:
                    boost = self.omega * relatedness * 0.15
                    p.confidence = min(1.0, p.confidence + boost)

    def stats(self) -> Dict:
        if not self.patterns:
            return {"n_patterns": 0, "total_seen": 0, "total_fixed": 0, "patterns": []}
        by_type = defaultdict(int)
        by_locality = {"local": 0, "unlocal": 0, "mixed": 0}
        for p in self.patterns:
            by_type[p.error_type] += 1
            if p.locality >= 0.6:
                by_locality["local"] += 1
            elif p.locality <= 0.4:
                by_locality["unlocal"] += 1
            else:
                by_locality["mixed"] += 1
        return {
            "n_patterns":     len(self.patterns),
            "by_type":        dict(by_type),
            "by_locality":    by_locality,
            "omega":          self.omega,
            "total_seen":     sum(p.times_seen for p in self.patterns),
            "total_fixed":    sum(p.times_fixed for p in self.patterns),
            "avg_confidence": sum(p.confidence for p in self.patterns) / len(self.patterns),
            "avg_locality":   sum(p.locality for p in self.patterns) / len(self.patterns),
            "patterns":       [p.to_dict() for p in self.patterns]
        }

    def print_summary(self):
        print(f"\nCoherent Knowledge Graph ({len(self.patterns)} patterns, Ω={self.omega}):")
        if not self.patterns:
            print("  (empty)")
            return
        for p in sorted(self.patterns, key=lambda x: -x.confidence):
            status = "VERIFIED" if p.times_fixed > 0 else "unverified"
            loc_label = "local" if p.locality >= 0.6 else ("unlocal" if p.locality <= 0.4 else "mixed")
            print(f"  [{p.error_type}] λ={p.locality:.1f} [{loc_label}] {p.error_signature[:50]}")
            if p.failing_line:
                print(f"    Line: {p.failing_line[:60]}")
            print(f"    Fix: {p.fix_strategy[:70]}...")
            print(f"    Confidence: {p.confidence:.2f} | {status} | seen {p.times_seen}x, fixed {p.times_fixed}x")

    def _save(self):
        if not self._dirty:
            return
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"patterns": [p.to_dict() for p in self.patterns]}, f, indent=2)
            self._dirty = False
        except Exception:
            pass

    def flush(self):
        self._save()

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for pd in data.get("patterns", []):
                    node = ErrorPatternNode.from_dict(pd)
                    self.patterns.append(node)
                    self.by_type[node.error_type].append(node)
        except Exception:
            pass
