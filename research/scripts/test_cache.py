"""Quick test of the caching layer."""
import sys
sys.path.insert(0, "research/scripts")
from cached_llm import CachedLLM

llm = CachedLLM()

# First call - cache miss
r = llm.generate(
    "claude-sonnet-4-20250514", "You are helpful.", "Say exactly: cache test ok",
    temperature=0.0, max_tokens=20,
)
print(f"Call 1: {r.content[:50]} | hit={r.cache_hit} | cost=${r.cost_usd:.4f}")

# Second call - should be cache hit
r2 = llm.generate(
    "claude-sonnet-4-20250514", "You are helpful.", "Say exactly: cache test ok",
    temperature=0.0, max_tokens=20,
)
print(f"Call 2: {r2.content[:50]} | hit={r2.cache_hit} | cost=${r2.cost_usd:.4f}")

print(f"Stats: {llm.stats()}")
