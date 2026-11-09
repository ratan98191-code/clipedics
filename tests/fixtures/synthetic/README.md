# Synthetic Unit-Test Fixtures

These files generate **deterministic, synthetic** data for use in unit tests.
They are **not** real benchmark data and must never be presented as evaluation
results against real videos.

| File | Purpose |
|------|---------|
| `build_dev_cache.py` | Generates fake `audio.wav` (sine-wave bursts) and synthetic transcripts from hard-coded text |
| `init_annotations.py` | Populates `ground_truth/` with placeholder labels derived from the same synthetic transcripts |

## How to Use

```bash
# Only run these inside tests — they create throwaway artifacts
python tests/fixtures/synthetic/build_dev_cache.py --out-dir /tmp/fake_bench
```

## Generating Real Benchmark Data

See [`evals/bench_v2/README.md`](../../../evals/bench_v2/README.md) for instructions on
downloading real videos, running the pipeline, and hand-annotating ground truth.
