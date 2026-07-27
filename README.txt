EarthText HEAVY v3 🌍🤖🧬 — single-file, offline, stdlib-only

What you get in v3:
1) Deterministic replay foundations
   - Separate RNG streams: climate / tectonics / events / life / governor / naming
   - Stable iteration order where it matters (life IDs sorted when deterministic)

2) Full-state checkpoints (real resume!)
   - Saves complete grid, lifeforms, species genomes, atoms+molecules (toy), RNG states, ID generators
   - Checkpoints: earthtext_out/checkpoint_XXXXXXX.json (+ .sha256)
   - Index: earthtext_out/checkpoint_index.json (+ .sha256)

3) Verify mode
   - Re-sim from scratch up to the latest checkpoint tick
   - Compares computed state hashes to saved hashes
   - Fails closed if PANIC_ON_INTEGRITY_FAIL=True

4) Earth-like circulation belts (toy)
   - Trade winds / westerlies / polar easterlies moisture advection
   - Subtropical drying + mid-lat wetness bands
   - Simple rain shadow behind mountains

Commands:
  python earthtext_heavy_system_v3.py sim
  python earthtext_heavy_system_v3.py resume
  python earthtext_heavy_system_v3.py replay
  python earthtext_heavy_system_v3.py verify
  python earthtext_heavy_system_v3.py both
  python earthtext_heavy_system_v3.py branch my_timeline
  python earthtext_heavy_system_v3.py clean
  python earthtext_heavy_system_v3.py zip

Notes:
- This is still a “toy Earth” (not numerically real Earth), but the patterns are more Earth-ish.
- If you want bigger worlds, the next upgrade is “chemistry compression”: replace explicit atoms with per-cell element inventories (much faster).
