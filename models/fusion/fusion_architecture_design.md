# Multimodal ML Fusion V1 — Architecture Design

Status: **design only — nothing in this document is wired into production runtime.**
See `fusion_task_definition.json` for the full option comparison and reasoning; this
document focuses on the concrete mechanics of the selected approach.

## 1. What this is, and is not

This is **evidence-level fusion** (Candidate 2: weighted evidence fusion), not a trained
multimodal classifier. No fusion model is trained in this task, and none should be
trained until a real synchronized thermal+vibration+acoustic dataset exists — see
`fusion_task_definition.json`'s `label_problem` section for why one does not exist today.

## 2. Where this sits relative to the existing deterministic engine

```
        deterministic evidence                    ML evidence
   (app/fusion/engine.py, unchanged)      (per-modality confidence-gated ML output)
                  │                                     │
                  │                                     ▼
                  │                      ┌───────────────────────────────┐
                  │                      │  ML Evidence Fusion (this doc) │
                  │                      │  Candidate 2: weighted average │
                  │                      └───────────────────────────────┘
                  │                                     │
                  ▼                                     ▼
        MachineHealthState                    ml_fusion_severity
   (health_score, status, ...)               ml_fusion_confidence
                  │                            ml_fusion_reliability
                  │                                     │
                  └───────────────┬─────────────────────┘
                                   ▼
                    one telemetry payload, BOTH blocks
                    visible side by side (supplementary,
                    not a replacement for either)
```

`app/fusion/engine.py` is **not modified** and remains authoritative for
`health_score` / `status` / `severity` / events. ML fusion produces a **separate**,
additively-named evidence block that would sit alongside it in a future telemetry
payload — not implemented in this task.

## 3. Per-modality evidence mapping (inputs to fusion)

Each modality's raw confidence-gate output (already implemented and live-integrated
in prior tasks) is mapped into the common schema defined in
`fusion_evidence_schema.json`. This mapping is **new** (not yet implemented) but
requires **no changes** to any existing modality code — it is a pure read of each
modality's already-produced gate output.

| Modality  | Source of raw evidence | `anomaly_strength` mapping |
|---|---|---|
| Thermal   | `apply_confidence_gate()` output (`ml_condition`) | 0.0 Healthy / 1.0 Corroded Bearing / null if suppressed |
| Vibration | `apply_confidence_gate()` output (`prediction`) | 0.0 healthy / 0.5 degrading / 1.0 severe / null if suppressed |
| Acoustic  | `apply_confidence_gate()` output (`prediction`) | 0.0 normal / 1.0 anomaly / null if suppressed |

A modality contributes **zero weight** to fusion whenever its own gate marked it
`reliability="low"` (suppressed) or `"unavailable"` (missing/failed) — never treated
as equally strong evidence as a `"high"` reading. This directly implements the task's
explicit example (thermal high, vibration high, acoustic low/suppressed → acoustic
must not count as full evidence).

## 4. Confidence propagation — exact formula

For each modality `m` in `{thermal, vibration, acoustic}`:

```
weight_m = confidence_m   if reliability_m == "high"
         = 0              otherwise (low / unavailable / absent)

fused_severity   = Σ(weight_m * anomaly_strength_m) / Σ(weight_m)     if Σ(weight_m) > 0
                  = null ("unavailable")                              otherwise

fused_confidence = Σ(weight_m) / 3
```

**Why this formula, not an arbitrary one:** it is a direct generalization of the
pattern already implemented in `app/fusion/engine.py`:

- The deterministic engine computes `avg_severity = sum(severities) / len(severities)`
  over calibrated (present) modalities — an implicit **uniform**-weighted average.
  This formula generalizes that to a **confidence-weighted** average, using each
  modality's own already-computed ML confidence instead of a flat 1/N weight.
- The deterministic engine computes `confidence = len(calibrated) / len(ALL_MODALITIES)`
  — a coverage fraction. `fused_confidence` generalizes this the same way: instead of
  counting "is this modality present" as 0 or 1, it counts "how much high-confidence
  evidence did this modality actually contribute" as a value in `[0, 1]`.

No new hyperparameter, tuning constant, or arbitrary scaling factor is introduced —
every term in the formula is either an existing per-modality output or a fixed count
(3 modalities).

### Worked example (from the task's own scenario)

Thermal: confidence 0.94, reliability high, anomaly_strength 0.0 (Healthy)
Vibration: confidence 0.97, reliability high, anomaly_strength 1.0 (severe)
Acoustic: confidence 0.67, reliability **low** (suppressed)

```
weight_thermal   = 0.94
weight_vibration = 0.97
weight_acoustic  = 0            (suppressed → excluded, NOT 0.67)

fused_severity   = (0.94*0.0 + 0.97*1.0) / (0.94 + 0.97) = 0.508
fused_confidence = (0.94 + 0.97 + 0) / 3 = 0.637
```

Acoustic's raw confidence (0.67) is preserved in its own evidence block (per the
"preserve raw confidence even when suppressed" convention every V1 gate already
follows) but contributes **nothing** to the fused number — exactly matching the
task's instruction not to treat a suppressed modality as equally strong evidence.

## 5. Missing-modality behavior

Identical algebra handles every subset automatically — a modality that is `absent`
(never configured for the session) gets `weight_m = 0` exactly like a `suppressed`
one; the two are distinguished only in the evidence block's `reliability` field
(`"unavailable"` either way, but `available: false` vs `available: true` distinguishes
"never present" from "present but rejected by its own gate" for anyone inspecting the
evidence, not for the fusion arithmetic itself).

| Scenario | Result |
|---|---|
| All 3 present, high confidence | Full weighted average, `fused_confidence` up to 1.0 |
| 2 present, 1 absent | Weighted average of the 2; `fused_confidence` capped at ≤ 2/3 |
| 1 present | That modality's own `anomaly_strength`; `fused_confidence` ≤ 1/3 |
| 0 present, or all suppressed | `fused_severity = null`, `reliability = "unavailable"` — **never fabricated** |

This mirrors `FusionEngine.combine()`'s own handling of `missing_modalities` and its
`if not calibrated: return status="unknown"` branch — same philosophy, applied to the
ML-evidence layer.

## 6. Why Candidates 3 and 4 are deferred, not rejected outright

A shallow meta-classifier (Candidate 3) or small neural fusion network (Candidate 4)
could, in principle, learn a better-than-uniform, data-driven weighting than the
formula above. Both require labeled examples of `[modality evidence] → [true
multimodal machine state]`, which requires the synchronized dataset this task
confirmed does not exist. If such a dataset is ever acquired (e.g. a real
instrumented rig recording all three modalities simultaneously with known
ground-truth machine condition), Candidate 3 should be attempted **before** Candidate
4 — a shallow linear model over 3 already-meaningful evidence scores needs far less
data than a neural network, and stays interpretable enough to sanity-check against
the Candidate 2 formula it would replace.

## 7. What a future implementation task would need to touch (not done here)

Purely informational — no code below is written or wired in this task:

- A new `app/fusion/ml_evidence_fusion.py` implementing the schema mapping (§3) and
  formula (§4) as pure functions, unit-testable exactly like each modality's own
  confidence gate.
- A new field on `TelemetryPayload` (e.g. `ml_fusion: dict | None`) — additive,
  following the same pattern as thermal/vibration/acoustic's own `ml_*` telemetry
  fields.
- A call site in `demo_runner._fusion_loop()` that gathers each modality runtime's
  `latest_ml_evidence`, maps it through the schema, and calls the fusion function —
  additive to the existing `_telemetry_block` merge pattern, never replacing
  `FusionEngine.combine()`'s own call.

## 8. Demo scenario validation (offline, no runtime change)

`scripts/fusion_evidence_fusion_demo.py` implements §3–§5 as a small, dependency-free
pure-Python module and runs it against the four scenarios from
`fusion_evidence_schema.json`'s `worked_examples` (all-high mixed severity, acoustic
suppressed, thermal-only, all-unavailable) to confirm the formula behaves as
documented before any implementation task builds on it.
