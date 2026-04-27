"""
Minimal Belief Graph
Tracks what the agent knows about the codebase.
"""


class BeliefNode:
    """A single piece of the assembled puzzle — a code entity."""
    
    def __init__(self, identity, signature=None, source="inferred", confidence=0.5):
        self.identity = identity          # e.g., "calculate_tax"
        self.signature = signature or {}  # e.g., {"params": ["amount", "rate"], "returns": "float"}
        self.source = source              # "human", "inferred", "synapse"
        self.confidence = confidence      # 0.0 to 1.0
        self.dependencies = []            # other BeliefNodes this one needs
        self.dependents = []             # other BeliefNodes that need this one
        self.test_coverage = []          # test names that validate this
    
    def __repr__(self):
        return f"BeliefNode({self.identity}, conf={self.confidence:.2f})"


class BeliefGraph:
    """The assembled puzzle so far."""
    
    def __init__(self):
        self.nodes = {}  # identity -> BeliefNode
    
    def add_node(self, node):
        self.nodes[node.identity] = node
    
    def get_node(self, identity):
        return self.nodes.get(identity)
    
    def describe(self):
        """Human-readable summary of current beliefs."""
        lines = ["=== Belief Graph ==="]
        for name, node in self.nodes.items():
            sig = node.signature or "unknown"
            lines.append(f"  {name}: {sig} [conf={node.confidence:.2f}, src={node.source}]")
        return "\n".join(lines)
