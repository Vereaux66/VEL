//! Health check module for VEL Gateway
//!
//! Provides comprehensive health checking for Kubernetes liveness and readiness probes.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use axum::{extract::State, http::StatusCode, Json};
use chrono::{DateTime, Utc};
use parking_lot::RwLock;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::time::Instant;
use tracing::{debug, error, info, warn};

use crate::config::HealthConfig;
use crate::error::{GatewayError, GatewayResult};
use crate::AppState;

/// Health status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum HealthStatus {
    Healthy,
    Degraded,
    Unhealthy,
}

/// Component health check result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComponentHealth {
    pub name: String,
    pub status: HealthStatus,
    pub latency_ms: Option<u64>,
    pub message: Option<String>,
    pub last_checked: DateTime<Utc>,
}

/// Overall health response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    pub status: HealthStatus,
    pub version: String,
    pub uptime_seconds: u64,
    pub timestamp: DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub components: Option<Vec<ComponentHealth>>,
}

/// Liveness probe response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivenessResponse {
    pub status: HealthStatus,
    pub timestamp: DateTime<Utc>,
}

/// Readiness probe response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadinessResponse {
    pub ready: bool,
    pub status: HealthStatus,
    pub timestamp: DateTime<Utc>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub missing_dependencies: Option<Vec<String>>,
}

/// Health checker for backend services
pub struct HealthChecker {
    /// HTTP client
    client: Client,
    /// Configuration
    config: HealthConfig,
    /// Start time for uptime calculation
    start_time: Instant,
    /// Cached health status
    cached_health: Arc<RwLock<Option<HealthResponse>>>,
    /// Backend endpoints to check
    backends: HashMap<String, String>,
}

impl HealthChecker {
    /// Create a new health checker
    pub fn new(config: &HealthConfig) -> GatewayResult<Self> {
        let client = Client::builder()
            .timeout(Duration::from_millis(config.timeout_ms))
            .build()
            .map_err(|e| GatewayError::Config(format!("Failed to create HTTP client: {}", e)))?;

        let mut backends = HashMap::new();
        backends.insert(
            "execution".to_string(),
            "http://localhost:5001/health".to_string(),
        );
        backends.insert(
            "strategy".to_string(),
            "http://localhost:5002/health".to_string(),
        );

        Ok(Self {
            client,
            config: config.clone(),
            start_time: Instant::now(),
            cached_health: Arc::new(RwLock::new(None)),
            backends,
        })
    }

    /// Get uptime in seconds
    pub fn uptime_seconds(&self) -> u64 {
        self.start_time.elapsed().as_secs()
    }

    /// Check all backends and return comprehensive health status
    pub async fn check_all(&self) -> HealthResponse {
        let mut components = Vec::new();
        let mut overall_status = HealthStatus::Healthy;

        // Check each backend
        for (name, url) in &self.backends {
            let component_health = self.check_backend(name, url).await;

            match component_health.status {
                HealthStatus::Unhealthy => {
                    if self.config.required_backends.contains(name) {
                        overall_status = HealthStatus::Unhealthy;
                    } else if overall_status == HealthStatus::Healthy {
                        overall_status = HealthStatus::Degraded;
                    }
                }
                HealthStatus::Degraded => {
                    if overall_status == HealthStatus::Healthy {
                        overall_status = HealthStatus::Degraded;
                    }
                }
                HealthStatus::Healthy => {}
            }

            components.push(component_health);
        }

        let response = HealthResponse {
            status: overall_status,
            version: env!("CARGO_PKG_VERSION").to_string(),
            uptime_seconds: self.uptime_seconds(),
            timestamp: Utc::now(),
            components: if self.config.detailed {
                Some(components)
            } else {
                None
            },
        };

        // Cache the response
        *self.cached_health.write() = Some(response.clone());

        response
    }

    /// Check a single backend
    async fn check_backend(&self, name: &str, url: &str) -> ComponentHealth {
        let start = Instant::now();

        match self.client.get(url).send().await {
            Ok(response) => {
                let latency = start.elapsed().as_millis() as u64;

                if response.status().is_success() {
                    ComponentHealth {
                        name: name.to_string(),
                        status: HealthStatus::Healthy,
                        latency_ms: Some(latency),
                        message: None,
                        last_checked: Utc::now(),
                    }
                } else {
                    ComponentHealth {
                        name: name.to_string(),
                        status: HealthStatus::Degraded,
                        latency_ms: Some(latency),
                        message: Some(format!("Status: {}", response.status())),
                        last_checked: Utc::now(),
                    }
                }
            }
            Err(e) => {
                let latency = start.elapsed().as_millis() as u64;
                warn!("Health check failed for {}: {}", name, e);

                ComponentHealth {
                    name: name.to_string(),
                    status: HealthStatus::Unhealthy,
                    latency_ms: Some(latency),
                    message: Some(e.to_string()),
                    last_checked: Utc::now(),
                }
            }
        }
    }

    /// Check liveness (is the process alive?)
    pub fn check_liveness(&self) -> LivenessResponse {
        // Gateway is alive if this code is running
        LivenessResponse {
            status: HealthStatus::Healthy,
            timestamp: Utc::now(),
        }
    }

    /// Check readiness (is the gateway ready to serve traffic?)
    pub async fn check_readiness(&self) -> ReadinessResponse {
        let health = self.check_all().await;

        let mut missing = Vec::new();

        if let Some(components) = &health.components {
            for required in &self.config.required_backends {
                let found = components
                    .iter()
                    .find(|c| &c.name == required && c.status != HealthStatus::Unhealthy);

                if found.is_none() {
                    missing.push(required.clone());
                }
            }
        }

        let ready = missing.is_empty() && health.status != HealthStatus::Unhealthy;

        ReadinessResponse {
            ready,
            status: health.status,
            timestamp: Utc::now(),
            missing_dependencies: if missing.is_empty() {
                None
            } else {
                Some(missing)
            },
        }
    }
}

// HTTP Handlers

/// Health endpoint - comprehensive health check
pub async fn health_handler(State(state): State<AppState>) -> Json<HealthResponse> {
    let health = state.health_checker.check_all().await;
    Json(health)
}

/// Liveness probe - for Kubernetes liveness checks
pub async fn liveness_handler(State(state): State<AppState>) -> (StatusCode, Json<LivenessResponse>) {
    let liveness = state.health_checker.check_liveness();
    let status = match liveness.status {
        HealthStatus::Healthy => StatusCode::OK,
        _ => StatusCode::SERVICE_UNAVAILABLE,
    };
    (status, Json(liveness))
}

/// Readiness probe - for Kubernetes readiness checks
pub async fn readiness_handler(
    State(state): State<AppState>,
) -> (StatusCode, Json<ReadinessResponse>) {
    let readiness = state.health_checker.check_readiness().await;
    let status = if readiness.ready {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };
    (status, Json(readiness))
}
