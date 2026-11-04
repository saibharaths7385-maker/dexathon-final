/**
 * @typedef {'NORMAL'|'WARNING'|'CRITICAL'|'NOT_ASSESSED'} EngineeringStatus
 * @typedef {'LOW'|'MODERATE'|'HIGH'|'INSUFFICIENT_DATA'|'NOT_ASSESSED'} TrendRiskCategory
 * @typedef {'HEALTHY'|'DEGRADED'|'WARNING'|'CRITICAL'|'INSUFFICIENT_DATA'|'NOT_CALIBRATED'} HealthStatus
 * @typedef {'pending'|'approved'|'rejected'} RecommendationStatus
 *
 * These JSDoc models mirror the backend Phase 2–6 response shapes. They are
 * intentionally open around evidence payloads because rule and feature fields
 * are configured by the backend.
 */

/** @typedef {{
 *  rule_id?: string,
 *  parameter?: string,
 *  status?: EngineeringStatus,
 *  measurement?: number|null,
 *  evidence?: Record<string, unknown>,
 *  explanation?: string,
 *  condition?: string
 * }} EngineeringFinding */

/** @typedef {{
 *  assessment_id?: string,
 *  aircraft_id?: string,
 *  mission_id?: string,
 *  timestamp?: string,
 *  scenario?: string,
 *  parameter?: string,
 *  observed_trend?: string,
 *  risk_category?: TrendRiskCategory,
 *  data_sufficiency?: Record<string, unknown>,
 *  explanation?: string,
 *  provenance?: Record<string, unknown>
 * }} TrendAssessment */

/** @typedef {{
 *  status?: HealthStatus,
 *  health_score?: number|null,
 *  score_kind?: string,
 *  calibration_status?: string,
 *  contributing_parameters?: string[],
 *  engineering_findings?: EngineeringFinding[],
 *  trend_indicators?: TrendAssessment[],
 *  missing_measurements?: string[],
 *  data_quality?: Record<string, unknown>,
 *  explanation?: string,
 *  algorithm_version?: string,
 *  provenance?: Record<string, unknown>
 * }} HealthAssessment */

/** @typedef {{
 *  recommendation_id: string,
 *  source: string,
 *  aircraft_id: string,
 *  mission_id: string,
 *  scenario: string,
 *  recommendation_details: Record<string, unknown>,
 *  status: RecommendationStatus,
 *  operator_comment?: string|null,
 *  created_at: string,
 *  decision_at?: string|null,
 *  current_details?: Record<string, unknown>
 * }} RecommendationRecord */

/** @typedef {{ recommendations: RecommendationRecord[] }} RecommendationList */
/** @typedef {{ history: RecommendationRecord[] }} DecisionHistory */
