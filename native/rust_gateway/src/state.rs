//! Application state module for VEL Gateway
//!
//! Manages shared state across handlers.

use std::sync::Arc;

use reqwest::Client;

use crate::config::GatewayConfig;
use crate::error::{GatewayError, GatewayResult};
use crate::health::HealthChecker;
use crate::intent::IntentRouter;
use crate::metrics::MetricsCollector;
use crate::rate_limiter::RateLimiter;

/// Shared gateway state
pub struct GatewayState {
    /// Configuration
    pub config: GatewayConfig,
    /// Rate limiter
    pub rate_limiter: RateLimiter,
    /// Intent router
    pub intent_router: IntentRouter,
    /// Health checker
    pub health_checker: HealthChecker,
    /// Metrics collector
    pub metrics: MetricsCollector,
}

impl GatewayState {
    /// Create new gateway state
    pub fn new(
        config: GatewayConfig,
        rate_limiter: RateLimiter,
        intent_router: IntentRouter,
        health_checker: HealthChecker,
        metrics: MetricsCollector,
    ) -> GatewayResult<Self> {
        Ok(Self {
            config,
            rate_limiter,
            intent_router,
            health_checker,
            metrics,
        })
    }
}
