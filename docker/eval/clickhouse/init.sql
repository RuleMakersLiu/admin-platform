CREATE DATABASE IF NOT EXISTS evaluation;

CREATE TABLE IF NOT EXISTS evaluation.eval_spans
(
    tenant_id Int64,
    experiment_id UUID,
    trial_id UUID,
    agent_version_id UUID,
    trace_id FixedString(32),
    span_id FixedString(16),
    parent_span_id FixedString(16),
    span_type LowCardinality(String),
    name String,
    status LowCardinality(String),
    started_at DateTime64(6, 'UTC'),
    duration_ms Float64,
    attributes_json String CODEC(ZSTD(3)),
    ingested_at DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(started_at)
ORDER BY (tenant_id, experiment_id, agent_version_id, started_at, trial_id, span_id)
TTL started_at + INTERVAL 365 DAY;

CREATE TABLE IF NOT EXISTS evaluation.eval_tool_calls
(
    tenant_id Int64,
    experiment_id UUID,
    trial_id UUID,
    agent_version_id UUID,
    tool_id LowCardinality(String),
    action String,
    side_effect_mode LowCardinality(String),
    policy_result LowCardinality(String),
    latency_ms Float64,
    input_hash FixedString(64),
    output_hash FixedString(64),
    occurred_at DateTime64(6, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, experiment_id, agent_version_id, occurred_at, trial_id);

CREATE TABLE IF NOT EXISTS evaluation.eval_cost_events
(
    tenant_id Int64,
    experiment_id UUID,
    trial_id UUID,
    agent_version_id UUID,
    idempotency_key String,
    resource_type LowCardinality(String),
    provider LowCardinality(String),
    model String,
    input_units UInt64,
    output_units UInt64,
    amount Decimal(18, 8),
    currency FixedString(3),
    usage_quality LowCardinality(String),
    occurred_at DateTime64(6, 'UTC')
)
ENGINE = ReplacingMergeTree(occurred_at)
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, idempotency_key);

CREATE TABLE IF NOT EXISTS evaluation.eval_score_facts
(
    tenant_id Int64,
    experiment_id UUID,
    trial_id UUID,
    agent_version_id UUID,
    evaluator_id UUID,
    evaluator_version String,
    score Nullable(Float64),
    passed Nullable(Bool),
    security_violation Bool,
    occurred_at DateTime64(6, 'UTC')
)
ENGINE = ReplacingMergeTree(occurred_at)
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, experiment_id, agent_version_id, trial_id, evaluator_id, evaluator_version);

CREATE TABLE IF NOT EXISTS evaluation.eval_trial_resource_usage
(
    tenant_id Int64,
    experiment_id UUID,
    trial_id UUID,
    agent_version_id UUID,
    cpu_seconds Float64,
    peak_memory_bytes UInt64,
    ephemeral_storage_bytes UInt64,
    network_egress_bytes UInt64,
    sandbox_compute_cost Decimal(18, 8),
    occurred_at DateTime64(6, 'UTC')
)
ENGINE = ReplacingMergeTree(occurred_at)
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, experiment_id, agent_version_id, trial_id);

CREATE TABLE IF NOT EXISTS evaluation.eval_security_events
(
    tenant_id Int64,
    experiment_id UUID,
    trial_id UUID,
    event_id UUID,
    severity LowCardinality(String),
    category LowCardinality(String),
    action LowCardinality(String),
    evidence_ref String,
    occurred_at DateTime64(6, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (tenant_id, experiment_id, occurred_at, trial_id, event_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS evaluation.eval_daily_agent_summary
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(day)
ORDER BY (tenant_id, experiment_id, agent_version_id, day)
AS SELECT
    tenant_id,
    experiment_id,
    agent_version_id,
    toDate(occurred_at) AS day,
    count() AS score_count,
    countIf(passed = true AND security_violation = false) AS passed_count,
    countIf(security_violation) AS security_violation_count,
    sum(ifNull(score, 0)) AS score_sum
FROM evaluation.eval_score_facts
GROUP BY tenant_id, experiment_id, agent_version_id, day;
