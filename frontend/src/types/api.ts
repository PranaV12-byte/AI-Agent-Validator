export type AuthResponse = {
  access_token: string
  token_type: string
  api_key?: string | null
  refresh_token?: string | null
}

export type TenantProfile = {
  id: string
  company_name: string
  email: string
  api_key_prefix: string
  active_policy_version: number
}

export type RegenerateApiKeyResponse = {
  api_key: string
  api_key_prefix: string
}

export type ForgotPasswordResponse = {
  message: string
  reset_url?: string | null
}

export type DashboardStats = {
  total_requests: number
  blocked_requests: number
  avg_latency_ms: number
}

export type UsageTrend = {
  date: string
  total_requests: number
  blocked_count: number
  allowed_count: number
  redacted_count: number
  avg_latency_ms: number
}

export type DashboardResponse = {
  total_requests: number
  blocked_requests: number
  avg_latency_ms: number
}

export type AuditLog = {
  id: string
  tenant_id: string
  session_id: string | null
  hook_type: string
  action: "BLOCKED" | "ALLOWED" | "REDACTED"
  violation_type: string | null
  severity: string
  input_preview: string | null
  details: Record<string, unknown>
  payload_hash: string | null
  policy_version: number | null
  algorand_tx_id: string | null
  processing_ms: number | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export type AuditListResponse = {
  logs: AuditLog[]
  total: number
  page: number
  page_size: number
}

export type PolicyRuleType =
  | "semantic"
  | "keyword"
  | "regex_match"
  | "llm_eval"
  | "pii_redaction"
  | "prompt_injection"

export type Policy = {
  id: string
  tenant_id: string
  name: string
  description: string | null
  rule_text: string
  rule_type: PolicyRuleType
  parameters: Record<string, unknown>
  is_enabled: boolean
  version: number
  policy_hash: string | null
  algorand_tx_id: string | null
  created_at: string
  updated_at: string
}

export type PolicyListResponse = {
  policies: Policy[]
  total: number
}

export type PolicyCreatePayload = {
  name: string
  description?: string | null
  rule_text: string
  rule_type: PolicyRuleType
  parameters?: Record<string, unknown>
}

export type PolicyUpdatePayload = {
  name?: string
  description?: string | null
  rule_text?: string
  rule_type?: PolicyRuleType
  parameters?: Record<string, unknown>
  is_enabled?: boolean
}

export type SafetyConfig = {
  id: string
  tenant_id: string
  global_block_enabled: boolean
  injection_protection: boolean
  injection_sensitivity: string
  pii_redaction: boolean
  pii_types: string[]
  policy_enforcement: boolean
  fail_mode: string
  fallback_message: string
  log_retention_days: number
  created_at: string
  updated_at: string
}

export type SafetyConfigUpdatePayload = {
  global_block_enabled?: boolean
  injection_protection?: boolean
  injection_sensitivity?: string
  pii_redaction?: boolean
  pii_types?: string[]
  policy_enforcement?: boolean
  fail_mode?: string
  fallback_message?: string
  log_retention_days?: number
}

export type PolicyConfig = {
  tenant_id: string
  active_policy_version: number
  injection_protection: boolean
  injection_sensitivity: "strict" | "moderate" | "lenient"
  pii_redaction: boolean
  policy_enforcement: boolean
  fail_mode: "open" | "closed"
  fallback_message: string
}

export type PolicyConfigUpdatePayload = {
  injection_protection?: boolean
  injection_sensitivity?: "strict" | "moderate" | "lenient"
  pii_redaction?: boolean
  policy_enforcement?: boolean
  fail_mode?: "open" | "closed"
  fallback_message?: string
}
