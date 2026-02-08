//! Metrics collection module for VEL Gateway
//!
//! Provides Prometheus-compatible metrics for monitoring.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use axum::{extract::State, response::IntoResponse};
use parking_lot::RwLock;
use prometheus::{
    register_counter, register_counter_vec, register_gauge, register_histogram,
    register_histogram_vec, Counter, CounterVec, Gauge, Histogram, HistogramVec, TextEncoder,
};
use serde::{Deserialize, Serialize};
use tracing::error;

use crate::error::{GatewayError, GatewayResult};
use crate::rate_limiter::RateLimitReason;
use crate::AppState;

/// Gateway statistics
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct GatewayStats {
    pub total_requests: u64,
    pub total_intents_submitted: u64,
    pub total_intents_completed: u64,
    pub total_intents_failed: u64,
    pub total_intents_cancelled: u64,
    pub total_rate_limited: u64,
    pub active_connections: u64,
    pub average_latency_ms: f64,
}

/// Metrics collector for gateway observability
pub struct MetricsCollector {
    // Counters
    requests_total: Counter,
    intents_submitted: Counter,
    intents_completed: Counter,
    intents_failed: Counter,
    intents_cancelled: Counter,
    rate_limited_total: CounterVec,

    // Histograms
    request_latency: HistogramVec,
    intent_processing_time: Histogram,

    // Gauges
    active_connections: Gauge,

    // Internal stats
    stats: Arc<RwLock<GatewayStats>>,
}

impl MetricsCollector {
    /// Create a new metrics collector
    pub fn new() -> GatewayResult<Self> {
        let requests_total = register_counter!(
            "vel_gateway_requests_total",
            "Total number of requests processed"
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let intents_submitted = register_counter!(
            "vel_gateway_intents_submitted_total",
            "Total number of intents submitted"
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let intents_completed = register_counter!(
            "vel_gateway_intents_completed_total",
            "Total number of intents completed successfully"
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let intents_failed = register_counter!(
            "vel_gateway_intents_failed_total",
            "Total number of intents that failed"
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let intents_cancelled = register_counter!(
            "vel_gateway_intents_cancelled_total",
            "Total number of intents cancelled"
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let rate_limited_total = register_counter_vec!(
            "vel_gateway_rate_limited_total",
            "Total number of rate-limited requests",
            &["reason"]
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let request_latency = register_histogram_vec!(
            "vel_gateway_request_latency_seconds",
            "Request latency in seconds",
            &["endpoint", "method"],
            vec![0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let intent_processing_time = register_histogram!(
            "vel_gateway_intent_processing_seconds",
            "Intent processing time in seconds",
            vec![0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        let active_connections = register_gauge!(
            "vel_gateway_active_connections",
            "Number of active connections"
        )
        .map_err(|e| GatewayError::Config(format!("Failed to register metric: {}", e)))?;

        Ok(Self {
            requests_total,
            intents_submitted,
            intents_completed,
            intents_failed,
            intents_cancelled,
            rate_limited_total,
            request_latency,
            intent_processing_time,
            active_connections,
            stats: Arc::new(RwLock::new(GatewayStats::default())),
        })
    }

    /// Record a request
    pub fn record_request(&self, endpoint: &str, method: &str, latency_secs: f64) {
        self.requests_total.inc();
        self.request_latency
            .with_label_values(&[endpoint, method])
            .observe(latency_secs);

        let mut stats = self.stats.write();
        stats.total_requests += 1;
    }

    /// Record intent submitted
    pub fn record_intent_submitted(&self) {
        self.intents_submitted.inc();

        let mut stats = self.stats.write();
        stats.total_intents_submitted += 1;
    }

    /// Record intent completed
    pub fn record_intent_completed(&self, processing_time_secs: f64) {
        self.intents_completed.inc();
        self.intent_processing_time.observe(processing_time_secs);

        let mut stats = self.stats.write();
        stats.total_intents_completed += 1;
    }

    /// Record intent failed
    pub fn record_intent_failed(&self) {
        self.intents_failed.inc();

        let mut stats = self.stats.write();
        stats.total_intents_failed += 1;
    }

    /// Record intent cancelled
    pub fn record_intent_cancelled(&self) {
        self.intents_cancelled.inc();

        let mut stats = self.stats.write();
        stats.total_intents_cancelled += 1;
    }

    /// Record rate limit
    pub fn record_rate_limit(&self, reason: RateLimitReason) {
        let reason_str = match reason {
            RateLimitReason::GlobalLimit => "global",
            RateLimitReason::UserLimit => "user",
            RateLimitReason::IpLimit => "ip",
        };
        self.rate_limited_total.with_label_values(&[reason_str]).inc();

        let mut stats = self.stats.write();
        stats.total_rate_limited += 1;
    }

    /// Update active connections
    pub fn set_active_connections(&self, count: u64) {
        self.active_connections.set(count as f64);

        let mut stats = self.stats.write();
        stats.active_connections = count;
    }

    /// Get current statistics
    pub fn get_stats(&self) -> GatewayStats {
        self.stats.read().clone()
    }
}

/// Prometheus metrics endpoint
pub async fn metrics_handler() -> impl IntoResponse {
    let encoder = TextEncoder::new();
    let metric_families = prometheus::gather();

    match encoder.encode_to_string(&metric_families) {
        Ok(output) => (
            axum::http::StatusCode::OK,
            [("Content-Type", "text/plain; charset=utf-8")],
            output,
        )
            .into_response(),
        Err(e) => {
            error!("Failed to encode metrics: {}", e);
            (
                axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                "Failed to encode metrics",
            )
                .into_response()
        }
    }
}

/// Get gateway statistics
pub async fn get_stats(State(state): State<AppState>) -> axum::Json<GatewayStats> {
    axum::Json(state.metrics.get_stats())
}
