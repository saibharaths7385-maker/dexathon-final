# SIH26054 Mission Control — project audit

**Scope:** Repository source as inspected on 2026-09-28, including the current React/Vite route tree, supporting page modules, the parallel V2 cockpit, and FastAPI twin/API modules. Existing local edits were treated as in-progress work and preserved.

## Executive summary

The repository contains a substantial PHM demonstrator: a legacy telemetry-analysis API, a persistent V2 digital-twin service, interactive mission/reliability and what-if views, a fleet endpoint, and an analysis/replay UI. The main risk was not a lack of dashboard code, but fragmented entry points: the active app exposed only a subset of the existing pages, while a richer, API-backed V2 cockpit was not mounted by the active router.

The current UI now exposes the requested seven mission screens. Dashboard and Digital Twin use explicitly labeled local simulation values; Fleet uses the existing V2 fleet API and existing fleet-command component; Replay, Diagnosis, and Analytics retain the existing legacy API flows. Shared Health Score, Remaining Useful Life, and Mission Recommendation visualizations are present. These changes improve the demonstrator but do not make its synthetic model safe for operational decisions or deployment as an airworthiness product.

## Screen-by-screen status

| Screen | Status | Current implementation and remaining limitations |
|---|---|---|
| Dashboard | Improved; demonstrator-only | Shared health score, scenario RUL range, risk/recommendation panel, and fault-injection controls. Its current telemetry and scenario values come from local mock data, not the V2 engine service. |
| Telemetry | Present; demonstrator-only | Live-looking RPM, CHT, EGT, fuel, and vibration charts update from local simulated samples. No external sensor connection is made on this screen. |
| Fleet | Improved; API-backed demonstrator | Reuses the existing V2 fleet-command UI and `/api/v2/fleet` refresh flow, with selectable assets, readiness, risk, health, and RUL. The backend derives companion aircraft from the lead engine using offsets; it is not independent aircraft telemetry. Refresh failures are surfaced and can be retried. |
| Digital Twin | Improved; demonstrator-only | Adds health and RUL context, expected-versus-measured plots, numeric residuals, and deviation indicators. Nominal channel values are illustrative frontend constants, not a calibrated engine reference model. |
| Replay | Present; API-backed legacy flow | Retains the backend replay request, frame controls, speed selection, seek, and reset. Replay depends on valid timestamped telemetry and a reachable legacy API. |
| Diagnosis | Present; API-backed legacy flow | Retains backend fault classification, explanation, severity, and classifier confidence. This is separate from the V2 model/explainability pipeline. |
| Analytics | Present; API-backed legacy flow | Displays backend health, risk, residual, and uncertainty histories. These charts are legacy API histories rather than the V2 twin's history stream. |

## Completed

- Kept the existing React/Vite application, router, backend services, and page/API contracts; no replacement dashboard or new backend model was introduced.
- Made the seven requested mission screens reachable from the shared responsive command navigation.
- Added reusable health-score gauge, RUL estimate/range, and mission-recommendation components. Labels disclose the demonstrator/synthetic nature of the estimates.
- Improved mission dashboard, digital-twin residual presentation, chart legibility, keyboard focus, mobile navigation, and the existing fleet command view.
- Preserved the fleet component's five-second API refresh and surfaced failed refreshes without replacing stale data with invented success.
- Repaired the current mission provider's build failure (JSX in a `.js` hook), while clarifying that its data is mock simulation data.

## Partially complete

- **Product integration:** The active app still combines local mock screens and a legacy API workflow. The richer `src/v2/V2App.jsx` mission cockpit is not the active application entry point; it contains additional twin, prognostics, reliability, maintenance, what-if, and report workflows. These code paths should be consolidated or intentionally retired after feature-by-feature acceptance, not silently abandoned.
- **Twin visualization:** Current active Digital Twin references are frontend constants and the local telemetry generator. Backend V2 computes its own seven-channel expected/observed values, residuals, wear, reliability, and uncertainty but is not the data source for this page.
- **Fleet data:** Fleet presentation is wired to the backend V2 endpoint, but companion-aircraft readings are synthetic offsets from a single lead asset.
- **Health, RUL, confidence, and risk:** The V2 model explicitly describes its assumptions as synthetic and its confidence as heuristic. Its RUL band is an assumed sensitivity band, not a calibrated statistical interval. The active mock dashboard also uses scenario-coded estimates.
- **Analytics continuity:** The active Analytics, Diagnosis, and Replay screens query the legacy API, whereas V2 streams/persists data separately. A consistent mission ID and data lineage across those pipelines is not yet established.
- **Data acquisition:** V2 provides a telemetry-ingestion route and source selector, but ingestion requires explicit source selection and fresh, increasing timestamps. It is not evidence of a production sensor link, authenticated device onboarding, or validated aircraft integration.

## Missing or not demonstrated

- Validated aircraft/OEM limits, fleet-calibrated degradation and RUL models, representative labeled evaluation data, and uncertainty calibration.
- Production identity and role-based authorization, operator audit trails, secret/configuration management, security review, and data-retention policy.
- Operational telemetry-device integration, transport/retry/clock/sensor-quality policy, fleet registry, and independent asset identity.
- Safety-case approval and qualified human procedures before any recommendation could be used to make real mission or maintenance decisions.
- Production deployment acceptance for the complete active route tree against the intended production API, beyond local frontend build and focused browser coverage.

## Recommended deployment priorities

1. **Set the operational boundary:** Keep all synthetic screens marked as demonstration-only. Do not use current RUL, health, reliability, or recommendations for flight release or maintenance decisions.
2. **Choose and document the canonical application flow:** Decide whether the legacy API pages and V2 cockpit are both supported. Bring their navigation, telemetry sources, mission identity, and failure/retry behavior under one tested entry point.
3. **Validate model outputs before presenting them operationally:** Obtain approved reference limits and representative fleet data; independently validate classification, health, reliability, and RUL across operating envelopes, faults, sensor failures, and missing/stale data.
4. **Harden service boundaries:** Add deployment-appropriate authentication/authorization, explicit CORS and WebSocket origin policy, managed secrets, request/rate limits, persistence/backup and retention policy, structured operational logging, health/readiness probes, and alerting.
5. **Test the deployed topology:** Run all frontend unit/browser tests and backend integration tests against the actual routing, API origin, websocket, database persistence, and supported browsers. Define a release gate and rollback procedure.
6. **Verify operator UX:** Validate responsive layouts and accessible controls with representative operators; ensure stale/offline data and model uncertainty remain visible and recommendations have documented human approval workflows.

## Verification performed

- `npm test` in `frontend/`: **15 passed**.
- `npm run build` in `frontend/`: **passed**.
- Focused Playwright checks for the seven screens, fleet selection, and mobile navigation: **2 passed**.
- A full Python/backend suite and production-backend/live deployment test were not run for this frontend-focused change.
# SKYNEX 3.0 — Phase 1 AI Engine Codebase Audit

**Audit date:** 2026-11-05  
**Scope:** `backend/`, `backend/twin/`, `src/uav_health/`, `tests/`, database/persistence code, and the active React/Vite integration.  
**Decision gate:** Audit and implementation plan only. No implementation refactor, model training, schema migration, deletion, or database reset was performed.

## 1. Current architecture findings

SKYNEX currently has two distinct PHM paths:

1. **Legacy PHM/API path**
   - `backend/api/main.py` exposes `/api/analyze`, `/api/replay`, `/api/health-history`, `/api/experiment`, `/api/validation`, and `/api/demo-flight`.
   - It composes the reusable `src/uav_health` modules: EKF estimation, unified physics prediction, residual generation, deterministic fault classification, and mission decision.
   - It calculates a health/risk score from residual magnitudes in the HTTP adapter. The score is not a calibrated health model.
   - `/api/validation` currently returns hard-coded metrics; these must not be presented as evidence that an ML model is validated.

2. **Versioned V2 twin/decision-support path**
   - `backend/twin/router.py` exposes `/api/v2` twin snapshots, source selection, live telemetry ingestion, replay, history, fleet, what-if, recommendations, decisions, and a WebSocket stream.
   - `backend/twin/model.py` is a deterministic reduced-order synthetic engine model. It includes configurable simulation controls, synthetic envelopes, rule predicates, explainability features, health, heuristic reliability/RUL-like values, and maintenance advisories.
   - `backend/twin/laptop1.py` validates and normalizes Laptop 1 Protocol 1 frames without changing the source frame. It rejects malformed, non-finite, stale/out-of-order frames through the bridge workflow.
   - `backend/twin/service.py` persists checkpoints, history, missions, fault history, and operator decisions in SQLite. It uses WAL mode and conditional pending-to-decided updates.
   - `backend/twin/decision_support.py` creates advisory-only, provenance-bearing recommendations. Protocol 1 source faults are retained as evidence and are deliberately not interpreted with unverified engineering thresholds.

The frontend has both the legacy API client (`frontend/src/api/phmApi.js`) and the V2 client (`frontend/src/v2/api.js`, `useTwin.js`). The V2 cockpit is API/WebSocket-backed; legacy diagnosis/replay/analytics screens remain separate. This split should be made explicit before implementation rather than silently merging incompatible contracts.

### Capability status

| Required capability | Existing implementation | Status and audit conclusion |
|---|---|---|
| Telemetry preprocessing | Pydantic strict models in `backend/api/models.py` and `backend/twin/schemas.py`; Protocol 1 validation/normalization in `backend/twin/laptop1.py`; CSV validation in `src/uav_health/flight_data/validator.py` | **Reusable and partially complete.** Original Protocol 1 data is retained, but a canonical engine-health preprocessing record with missing-value policy, feature provenance, and scenario context is missing. |
| Engine health assessment | `backend/twin/model.py:assess`; `src/uav_health/physics_model`; EKF-assisted legacy analysis | **Implemented as deterministic demonstrator.** It uses synthetic envelopes and should not be treated as aircraft/OEM limits. |
| Engineering fault detection | V2 predicates for pressure, temperature, vibration, fuel flow, RPM/EGT and envelope excursions | **Partially implemented.** Thresholds are embedded in the synthetic model and need an explicit configurable, source/provenance-aware threshold registry. No aircraft-specific limits may be invented. |
| Anomaly detection | `fault_progress.anomaly_detected` is a deterministic scenario-progress flag; no Isolation Forest or equivalent trained anomaly model exists | **Missing as validated ML.** Do not label current flags as ML anomaly scores. |
| Predictive fault analysis | `damage_rate`, heuristic reliability, assumed RUL sensitivity band, historical snapshots | **Demonstrator only.** No validated trend-risk estimator, failure probability, or RUL model exists. |
| Health scoring | Legacy residual score and V2 `health_index`/`hybrid.fused_health` | **Implemented but uncalibrated.** Current “AI health” is a transparent residual surrogate, not a validated learned output. |
| Explainability | V2 `features`, residuals, expected values, penalties, importance, rule basis, evidence and limitations | **Strong reusable foundation.** Needs a common response contract shared with the legacy path and future model outputs. |
| Maintenance recommendations | V2 `maintenance`, `decision_support.py`, persisted recommendation evidence | **Implemented advisory workflow.** Several actions are synthetic/model-derived and must remain advisory until approved engineering documentation exists. |
| Operator decisions | `operator_decisions` SQLite table; pending/approved/rejected routes; comments/timestamps; immutable recommendation evidence and duplicate-decision protection | **Implemented and reusable.** Preserve this workflow and extend only additively if needed. |

## 2. Existing reusable components

### Working modules

- **Input contracts and rejection:** strict Pydantic contracts reject extra fields, invalid ranges, NaN/Infinity, malformed timestamps, and invalid replay ordering.
- **Protocol 1 bridge:** `Laptop1TelemetryClient`, `validate_telemetry_frame`, `normalize_telemetry_frame`, and frame-order checks preserve raw source data and canonical mappings.
- **Digital-twin state and persistence:** `TwinService`, `EngineState`, checkpoint recovery, bounded history, mission/fault history, and thread locking.
- **Engineering demonstrator:** `SIGNALS`, `expected_state`, `assess`, `damage_rate`, and `advance` are a coherent synthetic baseline.
- **Legacy scientific pipeline:** `EKFEngineStateEstimator`, `DigitalTwin`, `SimplePhysicsModel`, `calculate_residuals`, `FaultClassifier`, `MissionDecision`, CSV loader/validator, replay, and metrics calculation.
- **Explainability/provenance:** V2 feature records include observed value, expected value, residual, envelope, penalty, status, and importance. Decision support adds rule ID, ruleset version, evidence, timestamps, limitations, and source identity.
- **Operator workflow:** `record_current_recommendation`, `scenario_recommendations`, `pending_recommendations`, `decision_history`, and `decide_recommendation`.
- **Frontend transport:** V2 request wrapper, WebSocket stream with polling/watchdog fallback, history merge by sequence, recommendation evaluation, and decision submission.

### Partially implemented

- Canonical telemetry preprocessing is fragmented across legacy API models, V2 schemas, Protocol 1 normalization, and CSV validation.
- Environmental context is carried as scenario text/mission severity, but there is no approved Urban/Volcanic/Desert/Forest/Snow Mountain engineering policy.
- Trend history exists, but no parameter trend extraction or validated predictive-risk calculation consumes it.
- V2 synthetic reliability/RUL fields are clearly caveated in some responses, but the frontend still displays them as prominent prognostic values; future contracts must make validation status and synthetic status machine-readable.
- Legacy and V2 APIs expose overlapping health/fault concepts with different field names (`health_score` vs `health_index`, `fault_type` vs maintenance findings).

### Missing

- A modular hybrid engine service with a stable internal result contract.
- Configurable engineering threshold registry with units, valid operating context, source document/version, and enabled/disabled status.
- Explicit missing/invalid sensor policy that preserves original telemetry and reports confidence limitations.
- Trained Isolation Forest lifecycle: explicit training dataset selection, feature schema, model artifact/version, fit metadata, validation report, and unavailable/untrained behavior.
- Evidence-backed trend-risk analysis with minimum history, data quality gates, validation metrics, and no fabricated probabilities/RUL.
- Scenario-aware environmental modifiers backed by approved engineering evidence.
- Unified API schemas for current health, anomaly, fault risk, score, recommendations, and analytics.
- Authentication/authorization and operator identity are not part of the current implementation; the existing comment/timestamp history must not be mistaken for production access control.

## 3. Recommended hybrid AI architecture

Add a new engine orchestration layer rather than duplicating the current twin or legacy components:

```text
Telemetry source
  -> Ingestion/provenance boundary
  -> Canonical preprocessing
       - validation and quality flags
       - original payload preservation
       - RPM/temperature/voltage/fuel/trend features
       - scenario/environment context
  -> Parallel evidence producers
       - EngineeringRuleEngine (configurable, documented limits)
       - AnomalyDetector (optional trained Isolation Forest)
       - TrendRiskAnalyzer (validated historical trend features only)
       - Existing EKF/physics/residual adapters
  -> Evidence fusion and HealthScorer
  -> Explainability/RecommendationPolicy
  -> Advisory result + existing operator decision persistence
```

### Component rules

- **Preprocessing:** never overwrite original telemetry; distinguish missing, invalid, stale, and unavailable values; return per-field quality and units; include source, aircraft/engine ID, mission, scenario, and environment without assuming that scenario names imply limits.
- **Engineering rules:** load thresholds from versioned configuration; require units and applicability context; use only approved limits; return `rule_id`, observed value, threshold, direction, source, and severity. If no approved limit applies, return “not assessed,” not a guessed fault.
- **Anomaly detection:** use Isolation Forest only after an explicit training-data selection step. Store model version, feature schema, training dataset identifier/hash, fit timestamp, contamination/configuration, and validation results. Return `unavailable/untrained` rather than a fabricated score when prerequisites fail. Keep anomaly score semantics documented and stable.
- **Trend risk:** require enough chronological, quality-approved history; calculate trends with confidence/coverage; report direction and evidence. Only emit risk categories where validation supports them. Do not output failure probabilities or RUL without approved training and validation.
- **Health scoring:** combine rule findings and validated model outputs with explicit weights/version. Missing data, disagreement, unavailable models, and out-of-domain context reduce confidence and appear as contributing factors. The score must identify whether it is synthetic, rule-only, or validated hybrid.
- **Explainability/recommendations:** each factor and recommendation must point to a rule or model output, telemetry timestamps, feature values, model/rule versions, and limitations. Keep current maintenance actions advisory and do not add operational controls.
- **Operator workflow:** call existing persistence methods; preserve recommendation identity hashing, evidence snapshots, comments, timestamps, pending state, and duplicate-decision rejection. Approval/rejection must never execute aircraft controls.

## 4. Scenario awareness

Add an explicit scenario context enum/metadata object for `urban`, `volcanic`, `desert`, `forest`, and `snow_mountain`, plus `unknown`. The context should include source, confidence, effective time, and applicable engineering-policy version.

Until approved engineering data exists:

- retain the scenario in every result and recommendation;
- use it for context, segmentation, and data-quality reporting only;
- do not apply identical thresholds across environments;
- do not invent ash, dust, humidity, temperature, wind, fuel, or vibration limits;
- return `not_assessed` when a scenario-specific rule is unavailable.

The existing synthetic V2 `environmental_severity` is a simulation control, not a validated environmental modifier.

## 5. API and frontend integration plan

Preserve all existing endpoints. Add a versioned hybrid namespace under `/api/v2` or a separately documented `/api/v3` only after approval. Recommended contracts:

| Capability | Proposed endpoint | Key response fields |
|---|---|---|
| Current engine health | `GET /api/v2/health/current` | engine/source identity, timestamp, quality, health score, risk category, confidence, contributing factors, scenario, validation status |
| Anomaly detection | `GET /api/v2/health/anomaly` or analysis subresource | status (`available/untrained/unavailable/out_of_domain`), score/classification, model version, training dataset ID, features, limitations |
| Fault-risk assessment | `GET /api/v2/health/fault-risk` | risk category only when validated, trend directions, evidence window, coverage, validation status |
| Health score | `GET /api/v2/health/score` | rule score, validated AI score if available, fusion version/weights, final score, confidence and missing-data factors |
| Recommendations | Existing `POST /api/v2/recommendations/evaluate` | preserve current response; add structured health/anomaly/risk evidence and model/rule provenance additively |
| Operator decisions | Existing `GET /api/v2/decisions/history`, `GET /api/v2/recommendations/pending`, `POST /api/v2/recommendations/{id}/decision` | preserve current fields and semantics; later add authenticated operator identity |
| Historical analytics | Existing `GET /api/v2/history`; add filtered analytics query if needed | bounded time window, source/scenario filters, health/risk/anomaly series, data-quality gaps, model-version provenance |

The React V2 client should consume the canonical result contract through `frontend/src/v2/api.js` and `useTwin.js`. Legacy pages should remain functional and explicitly labeled as legacy/synthetic until migrated. WebSocket snapshots must carry the same quality, scenario, validation status, and provenance fields as HTTP responses.

## 6. Database and persistence plan

No database change is required for Phase 1 audit approval. Do not delete, reset, or rewrite existing SQLite data.

The existing tables are:

- `checkpoint`: current twin state;
- `history`: bounded time-indexed snapshots;
- `missions`: mission summaries;
- `fault_history`: non-routine fault evidence;
- `operator_decisions`: recommendation evidence and pending/approved/rejected decisions.

If implementation is approved, prefer additive migrations:

1. `telemetry_observations`: raw payload hash, canonical values, source, identity, scenario, timestamp, quality flags, and ingestion metadata.
2. `health_assessments`: assessment ID, observation reference, rule/model versions, scores, risk status, confidence, contributing factors, and validation status.
3. `model_registry`/`model_training_runs`: model version, feature schema, training dataset hash, training time, validation metrics, and lifecycle status.
4. Optional `trend_features`: reproducible window boundaries, sample coverage, slopes, and quality exclusions.

Keep raw source payloads and approved recommendation evidence immutable. Add indexes and retention rules only after confirming operational storage requirements.

## 7. Testing plan

### Preprocessing and rules

- healthy telemetry produces a rule-only healthy/nominal result with source and synthetic status;
- abnormal temperature, RPM, voltage, and fuel-flow cases identify the affected parameter when an approved limit exists;
- missing values preserve the original frame, mark the field missing, lower confidence, and do not silently substitute a healthy value;
- invalid/non-finite/out-of-range telemetry is rejected or marked invalid according to the agreed boundary, without entering model inference;
- source timestamps, sequence order, stale frames, duplicate frames, and scenario context are covered;
- Urban, Volcanic, Desert, Forest, Snow Mountain use context-specific policies where configured and `not_assessed` otherwise.

### Model lifecycle

- trained Isolation Forest uses only explicitly selected training data and records dataset/model metadata;
- insufficient, invalid, out-of-domain, or untrained data returns an explicit unavailable status;
- anomaly score/classification is deterministic for a pinned artifact and feature schema;
- trend analysis requires minimum chronological coverage and reports insufficient-history safely;
- no unsupported failure probability or RUL is emitted;
- model/rule disagreement and missing-data confidence limitations are included in score explanations.

### API/persistence/frontend

- current health, anomaly, risk, score, recommendations, analytics contracts validate;
- legacy `/api/analyze`, replay, live telemetry, and `/api/v2` telemetry remain backward compatible;
- Laptop 1 to Laptop 2 live telemetry continues to accept only valid increasing Protocol 1 frames;
- original telemetry and synthetic demonstration labels are retained;
- recommendation evidence is persisted and traceable to rule/model versions;
- operator approval and rejection preserve comments/timestamps/history;
- duplicate decisions are rejected and historical decisions survive service restart;
- WebSocket and HTTP snapshots agree on sequence, quality, scenario, and provenance;
- frontend displays unavailable/untrained/insufficient-confidence states without converting them to healthy or risky values.

The existing suite already covers many API, replay, bridge, twin, decision, classifier, physics, and persistence behaviors. The targeted `pytest -q tests` command was not executable in this environment because `pytest` was unavailable; install/use the project test environment before implementation validation.

## 8. Safe implementation sequence

1. **Architecture approval and safety boundary:** approve the canonical result contract, scenario policy, threshold ownership, and explicit non-operational boundary.
2. **Contract inventory:** freeze existing endpoint/schema compatibility tests and document legacy versus V2 ownership.
3. **Canonical preprocessing:** add provenance/quality/feature objects while preserving raw telemetry and live transport.
4. **Configurable engineering rules:** extract existing synthetic predicates behind a versioned registry; do not change limits or claim aircraft applicability.
5. **Hybrid orchestration:** adapt existing EKF/physics/residual/explainability components into the new internal contract without duplicating them.
6. **Scenario policy:** implement only approved environment-specific policies; otherwise return `not_assessed`.
7. **Anomaly lifecycle:** add explicit dataset selection, training, artifact/version tracking, validation, and safe unavailable behavior. Keep the feature disabled until validated.
8. **Trend-risk analysis:** implement history quality gates and validated trend outputs; defer probabilities/RUL until evidence supports them.
9. **Score/recommendation integration:** fuse only supported outputs, propagate confidence/limitations, and reuse existing advisory persistence.
10. **Additive persistence migration:** add assessment/model metadata tables only if runtime requirements justify them; retain all current records.
11. **API/frontend integration:** add endpoints or additive fields, then migrate V2 UI first while preserving legacy screens and Laptop 1 transport.
12. **Validation gate:** run unit, integration, persistence, browser, replay, missing-data, model-unavailable, and scenario tests; review outputs before enabling any new model.

**Phase 1 conclusion:** The repository provides a solid deterministic demonstrator, telemetry bridge, explainability foundation, durable history, and human approval workflow. It does not yet contain an operational hybrid AI engine, validated anomaly detector, or evidence-backed predictive fault-risk model. Implementation should stop here pending architecture and safety-boundary approval.
