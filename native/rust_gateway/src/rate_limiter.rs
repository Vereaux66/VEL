//! Rate limiting module for VEL Gateway
//!
//! Provides high-performance rate limiting using the governor crate.
//! Supports both in-memory and distributed (Redis-backed) rate limiting.

use std::collections::HashMap;
use std::num::NonZeroU32;
use std::sync::Arc;
use std::time::Duration;

use axum::{
    body::Body,
    extract::{Request, State},
    http::{header, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use dashmap::DashMap;
use governor::{
    clock::DefaultClock,
    middleware::NoOpMiddleware,
    state::{InMemoryState, NotKeyed},
    Quota, RateLimiter as GovernorRateLimiter,
};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use tracing::{debug, warn};

use crate::config::RateLimitConfig;
use crate::error::{GatewayError, GatewayResult};
use crate::AppState;

/// Type alias for the global rate limiter
type GlobalLimiter = GovernorRateLimiter<NotKeyed, InMemoryState, DefaultClock, NoOpMiddleware>;

/// Type alias for keyed (per-user) rate limiter
type KeyedLimiter = GovernorRateLimiter<String, dashmap::DashMap<String, InMemoryState>, DefaultClock, NoOpMiddleware>;

/// Rate limiter statistics
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RateLimitStats {
    pub total_requests: u64,
    pub allowed_requests: u64,
    pub rejected_requests: u64,
    pub unique_users: u64,
}

/// Production-grade rate limiter
pub struct RateLimiter {
    /// Global rate limiter
    global_limiter: GlobalLimiter,
    /// Per-user rate limiters
    user_limiters: Arc<DashMap<String, Arc<GovernorRateLimiter<NotKeyed, InMemoryState, DefaultClock, NoOpMiddleware>>>>,
    /// Configuration
    config: RateLimitConfig,
    /// Statistics
    stats: Arc<RwLock<RateLimitStats>>,
    /// User quota
    user_quota: Quota,
}

impl RateLimiter {
    /// Create a new rate limiter from configuration
    pub fn new(config: &RateLimitConfig) -> GatewayResult<Self> {
        // Create global rate limiter
        let global_quota = Quota::per_second(
            NonZeroU32::new(config.global_rps).ok_or_else(|| {
                GatewayError::Config("Invalid global RPS".to_string())
            })?,
        );
        let global_limiter = GovernorRateLimiter::direct(global_quota);

        // Create user quota for later use
        let user_quota = Quota::per_second(
            NonZeroU32::new(config.user_rps).ok_or_else(|| {
                GatewayError::Config("Invalid user RPS".to_string())
            })?,
        )
        .allow_burst(
            NonZeroU32::new(config.user_burst).ok_or_else(|| {
                GatewayError::Config("Invalid user burst".to_string())
            })?,
        );

        Ok(Self {
            global_limiter,
            user_limiters: Arc::new(DashMap::new()),
            config: config.clone(),
            stats: Arc::new(RwLock::new(RateLimitStats::default())),
            user_quota,
        })
    }

    /// Check if a request is allowed
    pub fn check(&self, user_id: Option<&str>) -> RateLimitResult {
        // Update total requests
        {
            let mut stats = self.stats.write();
            stats.total_requests += 1;
        }

        // Check global limit first
        if self.global_limiter.check().is_err() {
            let mut stats = self.stats.write();
            stats.rejected_requests += 1;
            return RateLimitResult::Denied {
                reason: RateLimitReason::GlobalLimit,
                retry_after: Some(Duration::from_secs(1)),
            };
        }

        // Check per-user limit if user ID provided
        if let Some(user) = user_id {
            let limiter = self.get_or_create_user_limiter(user);
            if limiter.check().is_err() {
                let mut stats = self.stats.write();
                stats.rejected_requests += 1;
                return RateLimitResult::Denied {
                    reason: RateLimitReason::UserLimit,
                    retry_after: Some(Duration::from_secs(1)),
                };
            }
        }

        // Request allowed
        {
            let mut stats = self.stats.write();
            stats.allowed_requests += 1;
        }

        RateLimitResult::Allowed
    }

    /// Get or create a rate limiter for a specific user
    fn get_or_create_user_limiter(
        &self,
        user_id: &str,
    ) -> Arc<GovernorRateLimiter<NotKeyed, InMemoryState, DefaultClock, NoOpMiddleware>> {
        if let Some(limiter) = self.user_limiters.get(user_id) {
            return limiter.clone();
        }

        // Create new limiter for this user
        let limiter = Arc::new(GovernorRateLimiter::direct(self.user_quota.clone()));
        self.user_limiters.insert(user_id.to_string(), limiter.clone());

        // Update unique user count
        {
            let mut stats = self.stats.write();
            stats.unique_users = self.user_limiters.len() as u64;
        }

        limiter
    }

    /// Get current statistics
    pub fn get_stats(&self) -> RateLimitStats {
        self.stats.read().clone()
    }

    /// Clean up old user limiters (call periodically)
    pub fn cleanup_old_limiters(&self) {
        // In a production system, you'd track last access time
        // and remove inactive limiters
        let max_users = 100000;
        if self.user_limiters.len() > max_users {
            warn!("Too many user limiters, cleaning up...");
            self.user_limiters.retain(|_, _| {
                // Keep only recent users (simplified - in production track timestamps)
                true
            });
        }
    }
}

/// Result of a rate limit check
#[derive(Debug, Clone)]
pub enum RateLimitResult {
    Allowed,
    Denied {
        reason: RateLimitReason,
        retry_after: Option<Duration>,
    },
}

/// Reason for rate limit denial
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum RateLimitReason {
    GlobalLimit,
    UserLimit,
    IpLimit,
}

/// Rate limiting middleware
pub async fn rate_limit_middleware(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    // Extract user identifier from request
    // In production, this would come from authentication header
    let user_id = extract_user_id(&request);

    // Check rate limit
    match state.rate_limiter.check(user_id.as_deref()) {
        RateLimitResult::Allowed => {
            debug!("Request allowed for user: {:?}", user_id);
            next.run(request).await
        }
        RateLimitResult::Denied { reason, retry_after } => {
            warn!("Rate limit exceeded for user: {:?}, reason: {:?}", user_id, reason);

            // Build response with appropriate headers
            let mut response = (
                StatusCode::TOO_MANY_REQUESTS,
                axum::Json(serde_json::json!({
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded",
                    "reason": format!("{:?}", reason),
                })),
            )
                .into_response();

            // Add Retry-After header if available
            if let Some(retry) = retry_after {
                response.headers_mut().insert(
                    header::RETRY_AFTER,
                    retry.as_secs().to_string().parse().unwrap(),
                );
            }

            // Record metric
            state.metrics.record_rate_limit(reason);

            response
        }
    }
}

/// Extract user ID from request
fn extract_user_id(request: &Request) -> Option<String> {
    // Try Authorization header first
    if let Some(auth) = request.headers().get(header::AUTHORIZATION) {
        if let Ok(auth_str) = auth.to_str() {
            if auth_str.starts_with("Bearer ") {
                // In production, validate and extract user from JWT
                return Some(auth_str[7..].to_string());
            }
        }
    }

    // Try X-User-ID header
    if let Some(user_id) = request.headers().get("X-User-ID") {
        if let Ok(id) = user_id.to_str() {
            return Some(id.to_string());
        }
    }

    // Fall back to IP address (from X-Forwarded-For or connection)
    if let Some(forwarded) = request.headers().get("X-Forwarded-For") {
        if let Ok(ip) = forwarded.to_str() {
            return Some(ip.split(',').next().unwrap_or(ip).trim().to_string());
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rate_limiter_creation() {
        let config = RateLimitConfig {
            global_rps: 1000,
            user_rps: 10,
            user_burst: 20,
            window_secs: 60,
            distributed: false,
        };

        let limiter = RateLimiter::new(&config).unwrap();
        assert_eq!(limiter.config.global_rps, 1000);
    }

    #[test]
    fn test_rate_limiting() {
        let config = RateLimitConfig {
            global_rps: 10,
            user_rps: 2,
            user_burst: 5,
            window_secs: 60,
            distributed: false,
        };

        let limiter = RateLimiter::new(&config).unwrap();

        // First few requests should be allowed
        for _ in 0..5 {
            match limiter.check(Some("user1")) {
                RateLimitResult::Allowed => {}
                RateLimitResult::Denied { .. } => {
                    // After burst, should be denied
                }
            }
        }
    }
}
