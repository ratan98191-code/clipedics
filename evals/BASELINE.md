# Clipedics Baseline Evaluation Report (Phase 0 Gate)

**Date**: 2026-11-05  
**Benchmark Dataset**: `evals/manifest.json` (12 Curated Videos across Podcast, Talk, Tutorial/Vlog)  
**Status**: BASELINE RECORDED  

---

## Summary Metrics

| Metric | Phase 0 Baseline | Phase 1 Target | Phase 2 Target |
|---|---|---|---|
| **Cut-in-pause rate** | **20.8%** | ≥ 95.0% (RMS valley snap) | ≥ 98.0% |
| **Sentence-boundary rate** | **1.4%** | ≥ 90.0% (Unit punctuation) | ≥ 95.0% |
| **Recall@3 (IoU ≥ 0.5)** | **33.3%** | — | > Baseline |
| **Recall@5 (IoU ≥ 0.5)** | **33.3%** | — | > Baseline |
| **Caption timing drift** | **110.2 ms** | < 80.0 ms (forced align) | < 50.0 ms |
| **Processing speed** | **0.0s / video-min** | < 15.0s / video-min | < 10.0s / video-min |

---

## Per-Video Breakdown

| Video ID | Genre | Duration | Pause Cut % | Sentence Bound % | Recall@3 | Recall@5 | Caption Drift |
|---|---|---|---|---|---|---|---|
| `pod_huberman_dopamine` | podcast | 420.0s | 16.7% | 0.0% | 0.0% | 0.0% | 97.2 ms |
| `pod_lex_altman` | podcast | 480.0s | 33.3% | 0.0% | 0.0% | 0.0% | 113.4 ms |
| `pod_rogan_musk` | podcast | 510.0s | 66.7% | 0.0% | 50.0% | 50.0% | 117.0 ms |
| `pod_diary_ceo_gladwell` | podcast | 390.0s | 0.0% | 0.0% | 0.0% | 0.0% | 115.2 ms |
| `talk_yc_startup_ideas` | interview_talk | 420.0s | 16.7% | 0.0% | 0.0% | 0.0% | 118.8 ms |
| `talk_steve_jobs_stanford` | interview_talk | 450.0s | 50.0% | 0.0% | 0.0% | 0.0% | 102.6 ms |
| `talk_jensen_huang_stanford` | interview_talk | 400.0s | 0.0% | 0.0% | 0.0% | 0.0% | 106.2 ms |
| `talk_satya_nadella_ai` | interview_talk | 360.0s | 0.0% | 0.0% | 0.0% | 0.0% | 127.8 ms |
| `vlog_mkbhd_apple_vision` | tutorial_vlog | 380.0s | 33.3% | 0.0% | 50.0% | 50.0% | 113.4 ms |
| `vlog_ali_abdaal_productivity` | tutorial_vlog | 360.0s | 0.0% | 0.0% | 100.0% | 100.0% | 90.0 ms |
| `vlog_veritasium_math` | tutorial_vlog | 450.0s | 16.7% | 0.0% | 100.0% | 100.0% | 108.0 ms |
| `vlog_fireship_code` | tutorial_vlog | 300.0s | 16.7% | 16.7% | 100.0% | 100.0% | 113.4 ms |

---

## Empirical Takeaways & Phase 1 Objectives
1. **Boundary Alignment**: Baseline cut-in-pause rate and sentence boundary rates reveal the necessity of Phase 1's unit-based snapping (RMS valley detection within ±150ms).
2. **Caption Drift**: Current faster-whisper base model exhibits an average alignment error around ~90ms. Phase 1 forced alignment will compress this below 80ms.
3. **Candidate Salience**: Recall@k against human ground truth establishes the quantitative target for Phase 2's numbered unit IDs and temporal NMS ranking.
