// AUTO-GENERATED — do not edit manually
// Source: axelo/models/contracts.py
// Regenerate: python scripts/gen_ts_contracts.py
// Generated: 2026-04-14 17:29:15
// Models: FieldSpec, FieldEvidence, ReadinessAssessment, ScopeDefinition, AuthSpec, ExecutionSpec, OutputSpec, MissionContract

export interface FieldSpec {
  field_name?: string
  field_alias?: string
  data_type?: string
  required?: boolean
  priority?: number
  description?: string
  example_hint?: string
  validation_hint?: string
}

export interface FieldEvidence {
  field_name?: string
  found?: boolean
  selector?: string
  extractor?: string
  json_path?: string
  sample_values?: string[]
  confidence?: number
  source_evidence_id?: string
  validation_status?: string
  validation_notes?: string
}

export interface ReadinessAssessment {
  confidence?: number
  is_ready?: boolean
  missing_info?: string[]
  blocking_gaps?: string[]
  suggestions?: string[]
  assessed_at?: string
}

export interface ScopeDefinition {
  mode?: string
  seed_urls?: string[]
  login_required?: boolean
  credentials_provided?: boolean
}

export interface AuthSpec {
  mechanism?: string
  login_required?: boolean
  signing_required?: boolean
  signing_description?: string
}

export interface ExecutionSpec {
  stealth_level?: string
  js_rendering?: string
  concurrency?: number
  requests_per_sec?: number
  max_pages?: number
  timeout_sec?: number
  budget_usd?: number
  time_limit_min?: number
}

export interface OutputSpec {
  format?: string
  dedup?: boolean
  dataset_name?: string
  session_label?: string
}

export interface MissionContract {
  contract_id?: string
  session_id?: string
  created_at?: string
  locked_at?: string
  contract_version?: number
  source_chat_turns?: number
  last_updated_by?: string
  assumptions?: string[]
  target_url?: string
  objective?: string
  objective_type?: string
  mechanism_required?: boolean
  target_scope?: ScopeDefinition
  item_limit?: number
  page_limit?: number
  requested_fields?: FieldSpec[]
  auth_spec?: AuthSpec
  execution_spec?: ExecutionSpec
  output_spec?: OutputSpec
  constraints?: string[]
  exclusions?: string[]
  readiness_assessment?: ReadinessAssessment
  field_evidence?: FieldEvidence[]
}
