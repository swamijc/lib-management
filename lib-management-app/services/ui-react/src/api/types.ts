export interface Library {
  id: number; sl_no: number | null; package: string; sdk_name: string | null;
  platform: string; current_version: string | null; latest_version: string | null;
  update_needed: string; priority: string | null; repo_url: string | null;
  registry: string | null; comments: string | null; deprecation_notes: string | null;
  status: string; alert_priority: string; deadline_date: string | null;
  deadline_notes: string | null; ecosystem: string; framework_language: string | null;
  created_at: string; updated_at: string;
}
export interface Recommendation {
  id: number; library_id: number; upgrade_recommended: string | null;
  priority: string | null;
  recommendation_summary: string | null; upgrade_pros: string[];
  upgrade_cons: string[]; no_upgrade_pros: string[]; no_upgrade_cons: string[];
  generated_at: string;
}

export interface RecommendationChatTurn {
  role: 'user' | 'assistant'
  text: string
}

export interface RecommendationChatRequest {
  library_id: number
  package: string
  sdk_name?: string | null
  platform: string
  current_version?: string | null
  latest_version?: string | null
  update_needed?: string | null
  status?: string | null
  recommendation_summary?: string | null
  upgrade_recommended?: string | null
  upgrade_pros?: string[]
  upgrade_cons?: string[]
  question: string
  history?: RecommendationChatTurn[]
}

export interface RecommendationChatResult {
  answer: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  latency_ms: number | null
}
export interface PipelineRun {
  run_id: string; triggered_by: string; status: string;
  steps: PipelineStep[]; total_libraries: number;
  started_at: string; finished_at: string | null; error: string | null;
}
export interface PipelineStep {
  step: string; status: string; message: string;
  items_processed: number; duration_seconds: number;
  started_at: string; finished_at: string | null;
}
export interface NotifyChannelResult {
  channel: 'email' | 'teams' | string
  status: 'sent' | 'failed' | 'skipped' | string
  message: string
  sent_at: string
}
export interface NotifyResult {
  channels_attempted: string[]
  results: NotifyChannelResult[]
  dedup_hash: string
  skipped_by_dedup: boolean
  generated_at: string
}
export interface RetryRunResponse {
  request_status: 'queued' | 'rejected' | string
  message: string
  run_id: string | null
  source_run_id: string | null
  step: string | null
}
export interface Lifecycle {
  id: number; lifecycle_id?: number; library_id: number; status: string;
  target_version: string | null; target_sprint: string | null;
  target_date: string | null; completed_version: string | null;
  skip_reason: string | null; actioned_by: string | null;
  created_at: string; updated_at: string;
  package?: string; sdk_name?: string; platform?: string;
  current_version?: string; latest_version?: string;
  update_needed?: string; priority?: string;
  ai_recommendation?: string; ai_summary?: string;
  business_critical?: boolean;
  confidence_score?: number;
  confidence_band?: 'High' | 'Medium' | 'Low';
}
export interface User {
  id: number; username: string; email: string; full_name: string | null;
  role: string; is_active: boolean; created_at: string; last_login: string | null;
}
export interface SlaStats {
  total_libraries: number; with_deadline: number; overdue: number;
  due_within_7_days: number; due_within_30_days: number;
  sla_compliance_pct: number; needs_upgrade: number;
  risk_score?: number;
  priority_counts?: {
    critical?: number;
    high?: number;
    moderate?: number;
    low?: number;
    mandatory?: number;
    up_to_date?: number;
  };
  sla_forecast?: {
    throughput_per_day?: number;
    d7?: number;
    d14?: number;
    d30?: number;
    model?: string;
  };
  deprecated?: number;
  pending_review_high_risk?: number;
  pie_distribution?: {
    critical?: number;
    high?: number;
    moderate?: number;
    up_to_date?: number;
  };
  platform_distribution?: Array<{
    platform: string;
    critical: number;
    high: number;
    moderate: number;
    up_to_date: number;
  }>;
  at_risk_summary?: {
    by_platform?: Array<{ name: string; count: number }>;
    by_owner?: Array<{ name: string; count: number }>;
  };
  owner_workload?: Array<{
    owner: string;
    critical: number;
    overdue: number;
    dueSoon: number;
    total: number;
  }>;
  rebalance_suggestion?: string;
  backend_rules?: {
    enabled?: boolean;
    source?: string;
  };
}

export interface WeeklyDigestSummary {
  generated_at: string;
  portfolio_risk_trend_pct: number;
  approvals_processed_7d: number;
  overdue_now: number;
  due_7d: number;
  due_30d: number;
  pipeline_reliability_7d_pct: number;
  notification_health_pct: number;
  notification_retry_count: number;
  sla_compliance_pct: number;
  pipeline_by_status_7d: { completed: number; failed: number; partial: number };
  approvals_by_status_7d: { completed: number; acknowledged: number; inProgress: number };
  channel_summary: Array<{ channel: string; sent: number; failed: number; retries: number; deliveryPct: number }>;
  top_failure_reasons: Array<{ reason: string; count: number }>;
  platform_risk: Array<{ platform: string; total: number; critical: number; overdue: number }>;
  top_overdue_libraries: Array<{
    id: number;
    package: string;
    platform: string;
    priority?: string | null;
    owner: string;
    daysOverdue: number;
  }>;
}
export interface LlmStats {
  total_calls: number; total_tokens: number; total_cost_usd: number;
  avg_latency_ms: number | null; calls_this_month: number; cost_this_month: number;
  models_used: string[];
}
export interface AuditLogEntry {
  id: number
  library_id: number
  package?: string | null
  sdk_name?: string | null
  field_changed?: string | null
  old_value?: string | null
  new_value?: string | null
  updated_by?: string | null
  update_type?: string | null
  reason?: string | null
  updated_at?: string | null
}
export interface ApiResponse<T> { success: boolean; data: T; error: unknown; }
