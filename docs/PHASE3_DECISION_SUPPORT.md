# Phase 3 — Scenario-aware decision support

## Audit (4 November 2026)

The existing FastAPI `/api/v2` router owns twin snapshots, controls, telemetry
ingestion, what-if analysis, history, fleet, missions and a WebSocket stream.
`backend/twin/model.py` implements a deterministic reduced-order demonstrator.
`backend/twin/laptop1.py` is a separate read-only Protocol 1 client. Live Mission
already displays both sources and has a persistent operator review UI.

`operator_decisions` already stores source, aircraft/engine identity, mission,
scenario, JSON evidence, pending/approved/rejected status, comment and timestamps.
The conditional pending-to-decided SQL update rejects duplicate decisions (409).
The legacy `/recommendations/current` retains its existing response contract.
Legacy `/api/analyze`, replay and `/telemetry/live` are separate pipelines; they
are not authoritative Laptop 1 sources and are not used by Phase 3.

Initial integration check: this execution environment had no
`LAPTOP1_TELEMETRY_WS_URL`; local HTTP requests to ports 8000 and 8001 failed.
No live Laptop 1 frame was observed. Repository fixtures containing `coastal`
are synthetic test inputs, not proof of connection or scenario support.
The URL, scenario catalogue, engineering limits, fault semantics, and reset/
clock behavior were requested from the integrator before implementation.
The production frontend configuration points to
`https://sih26054-phm-v2.onrender.com`. A read-only request to that backend's
`/api/v2/laptop1` returned HTTP 404. Its deployed bridge is therefore not verified
either. The implementation in this checkout has not been deployed.

## Supported scope

Phase 3 reuses all active V2 maintenance findings, adds the existing V2 mission
gate, and separately evaluates Laptop 1 data quality and raw reported faults.
No trained AI, calibrated failure probabilities, flight clearance, or actuator
commands are provided. Approval only updates the existing decision table.

V2 simulation scenarios: `nominal`, `engine_degradation`, `sensor_bias`,
`fuel_leak`, `compressor_fouling`, `engine_overheating`, `cooling_loss`, `oil_leak`,
`sensor_drift`, `bearing_wear`, `fuel_restriction`. Their existing model dynamics
remain unchanged. In particular, `sensor_drift` at the default operating point
does not activate a named fault rule; Phase 3 does not fabricate a diagnosis.
Several scenarios can trigger several envelope rules simultaneously.

Laptop 1 scenario and phase are retained verbatim as context. There is no verified
geographic/environmental scenario policy. All scenario names receive the same
quality/source-fault review rules. Numerical coastal, dust, ash, wind, thermal,
battery, fuel-reserve or emergency-action rules require authoritative source
documentation and are deliberately unavailable.

External V2 telemetry carries neither aircraft registration nor a scenario.
Its identity is explicitly the V2 engine ID (`VAYU-01`), its scenario is
`unreported`, and assessment excludes selected simulated fault injections.
External sample rules still use V2 demonstration limits, not aircraft limits.

## Data mappings and units

| Source | Inputs used | Treatment |
| --- | --- | --- |
| V2 sensors | `rpm` rpm; `egt`, `cht`, `oil_temperature` °C; `oil_pressure` bar; `fuel_flow` L/h; `vibration` mm/s RMS | Existing validated sensor schema and model features; no new conversion |
| V2 assessment | health /100, model reliability %, fault severity %, maintenance priority | Explicit synthetic model evidence, not measured aircraft probability |
| Protocol 1 envelope | protocol, seq, aircraft_id, mission_id, scenario, phase, timezone-aware timestamp | Identity/context and freshness evidence; no aliases |
| Protocol 1 faults | raw list or object | Preserve as JSON evidence; nonempty means review, empty means no source-reported entries |
| Protocol 1 containers | flight, propulsion, environment, mission | Must be objects for decision use; otherwise quality advisory |
| Protocol 1 propulsion | Existing UI displays rpm, engine_temp_c, battery_voltage, current_a, fuel_percent | No decision thresholds. Temperature is not EGT/CHT; percentage is not L/h |
| Bridge | connection status, last error, last received timestamp | Receipt freshness and integrity gating |

Protocol 1 hello remains `{"type":"hello","client":"skynex-3d","protocol":1}`.
No fields are renamed, added to outgoing frames, or transmitted as commands.
Nonfinite JSON values (including overflow such as `1e999`) are rejected.
Repeated/non-increasing sequence or source time within the same aircraft/mission
does not refresh receipt time or replace accepted data. A fresh increasing frame
clears that error; a new mission may restart sequence numbering. A producer that
resets sequence within the same mission needs a confirmed restart contract;
until then the decision layer reports unavailable quality rather than fresh data.

## Existing thresholds and rule provenance

All engineering numbers below are already in `backend/twin/model.py`, explicitly
synthetic. `decision_support.py` documents their predicates and consumes `assess()`;
it does not replace the model or introduce engineering thresholds.

| V2 rule | Existing predicate |
| --- | --- |
| Engine degradation | Selected injected scenario; ramp severity > 0.18 |
| Sensor bias / fuel leak / compressor fouling | Corresponding injected scenario; ramp severity > 0.12 |
| Lubrication pressure loss | Oil pressure < 2.5 bar (subject to existing model branch precedence) |
| Thermal overload | CHT > 220 °C or oil temperature > 120 °C |
| Rotating assembly anomaly | Vibration > 5 mm/s RMS |
| Fuel delivery anomaly | Fuel flow < 80% of operating-point expectation |
| Power/combustion deviation | Absolute RPM residual > 700 rpm or EGT > 820 °C |
| Uncovered envelope excursion | Channel outside its existing SIGNALS envelope and not covered by another finding |
| Routine inspection | No maintenance predicate active; evidence includes all channels |
| Mission HOLD / INSPECT | Critical maintenance, reliability < 80%, or health < 55 |
| Mission REVIEW REQUIRED | Otherwise reliability < 95% or high maintenance |

SIGNALS nominal envelopes: rpm 2000–5500; EGT 350–820 °C; CHT 70–220 °C;
oil temperature 60–120 °C; oil pressure 2.5–6 bar; fuel flow 8–32 L/h;
vibration 0–5 mm/s RMS. Evidence includes expected values, residuals, envelopes
and residual tolerances directly from the model. Rule severities and maintenance
actions are inherited from that model.

Quality gates reuse software timing policy, not engineering limits:

- V2 must report live quality, have a timestamp no older than 5 s, and be no more
  than 2 s in the future (existing ingestion tolerance).
- Laptop 1 must be connected without an outstanding error. Receipt and source
  age must be within the existing bridge's 2 s freshness window. Future source
  tolerance is 2 s; a future receipt is invalid. This assumes synchronized clocks;
  a mismatch produces a quality advisory, not an aircraft fault.
- Unusable data yields only a warning to restore/verify that source. Stale
  source faults are not promoted into current condition advice.
- Fresh Protocol 1 faults produce warning-level *operator review urgency*.
  Source severity remains raw evidence; the system does not certify it.
- An empty faults container produces informational monitoring advice, never a
  healthy-aircraft declaration. Unknown limits remain visible on every card.

## API, persistence and operator semantics

`POST /api/v2/recommendations/evaluate` takes no telemetry payload. It evaluates
server-owned bridge/twin snapshots, persists records in the existing table and
returns `ruleset_version`, `evaluated_at`, `advisory_only`, and `recommendations`.
Each recommendation contains source, identity, mission, scenario and existing
decision fields. Its details contain rule ID/version, category, severity, action,
explanation, supporting evidence, evaluation/sample timestamps and limitations.

Identity hashes cover source, aircraft/engine ID, mission, scenario, rule/version,
severity, action, phase, quality failure and the complete source-fault signature. They deliberately exclude envelope sample
numbers, timestamps and changing measurements, preventing one pending decision
per telemetry tick. Like the existing workflow, a rule/scope/severity receives
one review per mission; recurrence does not silently reopen an approved record.
New missions and changed severity/quality/phase receive distinct records. A changed
raw source-fault payload also receives a distinct record, so a new fault cannot
inherit a previous approval. Without an authoritative fault schema, no fields
inside that payload are ignored (including embedded source timestamps).

Stored `recommendation_details` are immutable original evidence. `current_details`
are freshly evaluated evidence returned alongside the stored record. An approved
card therefore does not imply approval of new samples. Original evidence remains
inspectable. Old pending records remain in history and are not presented as current
advice. A separate collapsed review area preserves approval/rejection of earlier
pending records. The existing decision endpoint is shared by both workflows.
The UI polls evaluation every 2 s; it disables review on evaluation failure or
after 5 s without a successful evaluation, reusing the V2 display freshness window.
Evaluation is on demand through that endpoint, not a background alerting service.

The legacy single-recommendation endpoint remains compatible for other clients;
Live Mission uses the quality-gated Phase 3 endpoint. Existing database rows need
no migration and are not overwritten. Tests use isolated databases, not data/twin.sqlite3.

## Validation strategy

Backend coverage: all supported simulation scenarios, simultaneous faults, strict
threshold boundaries, external-source isolation, normal/stale/missing/invalid
Protocol 1 inputs, unknown scenarios, duplicate/out-of-order frames, immutable
evidence, concurrent deduplication, restart persistence, HTTP approval/rejection
and absence of control/state side effects. Frontend unit tests, production build,
mocked browser flows and a real local API browser test cover display, decisions,
history and failures. Synthetic socket tests do not verify Laptop 1 integration.

## Verification results (4 November 2026)

| Check | Command | Result |
| --- | --- | --- |
| Full backend suite | `.venv/Scripts/python.exe -B -m pytest tests -q --basetemp artifacts/phase3-release-backend` | 176 passed; 1 existing Starlette/httpx deprecation warning |
| Frontend unit tests (from frontend/) | `npm.cmd test` | 19 passed |
| Production build (from frontend/) | `npm.cmd run build` | Passed; 2652 modules transformed |
| Edge browser suite (from frontend/) | `npm.cmd run test:phase3` | 11 passed, including a real isolated local API workflow and mocked source faults/staleness |

Browser checks include required comments, approval/rejection, duplicate conflicts,
reload history, current versus historical evidence, unavailable evaluation and
recovery, mobile width, source units and no aircraft-command requests. The browser
test API uses an in-memory database; backend restart tests use temporary SQLite
files. Production `data/twin.sqlite3` was not used for these Phase 3 tests.
Screenshots and JSON results are in frontend/test-results; generated test build
and temporary backend test directories can be removed and recreated by the commands.

Initial sandbox attempts failed on Windows temporary-file access and child-process
spawning (`EPERM`). Authorized reruns succeeded. No tests establish a live Laptop 1
connection, validated aircraft limits, or a deployed Phase 3 service.
