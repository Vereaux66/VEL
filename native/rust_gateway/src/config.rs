//! Configuration module for VEL Gateway
//!
//! Loads and validates configuration from environment variables and config files.

use std::time::Duration;

use axum::{extract::State, Json};
use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::AppState;

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("Configuration load failed: {0}")]
    LoadError(#[from] config::ConfigError),
    #[error("Invalid configuration: {0}")]
    ValidationError(String),
}

/// Main gateway configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GatewayConfig {
    pub server: ServerConfig,
    pub rate_limit: RateLimitConfig,
    pub routing: RoutingConfig,
    pub health: HealthConfig,
    pub redis: Option<RedisConfig>,
}

/// Server configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ServerConfig {
    pub host: String,
    pub port: u16,
    pub worker_threads: usize,
    pub request_timeout_ms: u64,
    pub max_body_size: usize,
}

/// Rate limiting configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RateLimitConfig {
    /// Global requests per second limit
    pub global_rps: u32,
    /// Per-user requests per second limit
    pub user_rps: u32,
    /// Per-user burst capacity
    pub user_burst: u32,
    /// Window duration in seconds
    pub window_secs: u64,
    /// Enable distributed rate limiting via Redis
    pub distributed: bool,
}

/// Intent routing configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RoutingConfig {
    /// Default backend URL
    pub default_backend: String,
    /// Execution backend URL
    pub execution_backend: String,
    /// Strategy backend URL
    pub strategy_backend: String,
    /// Request timeout in milliseconds
    pub timeout_ms: u64,
    /// Maximum retries
    pub max_retries: u32,
    /// Retry delay in milliseconds
    pub retry_delay_ms: u64,
}

/// Health check configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct HealthConfig {
    /// Enable detailed health checks
    pub detailed: bool,
    /// Health check interval in seconds
    pub check_interval_secs: u64,
    /// Timeout for health checks in milliseconds
    pub timeout_ms: u64,
    /// Required backends for readiness
    pub required_backends: Vec<String>,
}

/// Redis configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RedisConfig {
    pub url: String,
    pub pool_size: u32,
    pub connection_timeout_ms: u64,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            server: ServerConfig::default(),
            rate_limit: RateLimitConfig::default(),
            routing: RoutingConfig::default(),
            health: HealthConfig::default(),
            redis: None,
        }
    }
}

impl Default for ServerConfig {
    fn default() -> Self {
        Self {
            host: "0.0.0.0".to_string(),
            port: 8080,
            worker_threads: num_cpus::get(),
            request_timeout_ms: 30000,
            max_body_size: 10 * 1024 * 1024, // 10MB
        }
    }
}

impl Default for RateLimitConfig {
    fn default() -> Self {
        Self {
            global_rps: 10000,
            user_rps: 100,
            user_burst: 200,
            window_secs: 60,
            distributed: false,
        }
    }
}

impl Default for RoutingConfig {
    fn default() -> Self {
        Self {
            default_backend: "http://localhost:5000".to_string(),
            execution_backend: "http://localhost:5001".to_string(),
            strategy_backend: "http://localhost:5002".to_string(),
            timeout_ms: 30000,
            max_retries: 3,
            retry_delay_ms: 100,
        }
    }
}

impl Default for HealthConfig {
    fn default() -> Self {
        Self {
            detailed: true,
            check_interval_secs: 30,
            timeout_ms: 5000,
            required_backends: vec!["execution".to_string()],
        }
    }
}

impl GatewayConfig {
    /// Load configuration from environment and config files
    pub fn load() -> Result<Self, ConfigError> {
        // Try to load .env file
        let _ = dotenvy::dotenv();

        // Build configuration from multiple sources
        let config = config::Config::builder()
            // Start with defaults
            .set_default("server.host", "0.0.0.0")?
            .set_default("server.port", 8080)?
            .set_default("server.worker_threads", num_cpus::get() as i64)?
            .set_default("server.request_timeout_ms", 30000)?
            .set_default("server.max_body_size", 10 * 1024 * 1024)?
            .set_default("rate_limit.global_rps", 10000)?
            .set_default("rate_limit.user_rps", 100)?
            .set_default("rate_limit.user_burst", 200)?
            .set_default("rate_limit.window_secs", 60)?
            .set_default("rate_limit.distributed", false)?
            .set_default("routing.default_backend", "http://localhost:5000")?
            .set_default("routing.execution_backend", "http://localhost:5001")?
            .set_default("routing.strategy_backend", "http://localhost:5002")?
            .set_default("routing.timeout_ms", 30000)?
            .set_default("routing.max_retries", 3)?
            .set_default("routing.retry_delay_ms", 100)?
            .set_default("health.detailed", true)?
            .set_default("health.check_interval_secs", 30)?
            .set_default("health.timeout_ms", 5000)?
            // Add config file if exists
            .add_source(config::File::with_name("gateway_config").required(false))
            // Override with environment variables
            .add_source(
                config::Environment::with_prefix("VEL_GATEWAY")
                    .separator("__")
                    .try_parsing(true),
            )
            .build()?;

        let gateway_config: GatewayConfig = config.try_deserialize()?;
        gateway_config.validate()?;

        Ok(gateway_config)
    }

    /// Validate configuration values
    fn validate(&self) -> Result<(), ConfigError> {
        if self.server.port == 0 {
            return Err(ConfigError::ValidationError("Port cannot be 0".to_string()));
        }
        if self.rate_limit.global_rps == 0 {
            return Err(ConfigError::ValidationError(
                "Global RPS cannot be 0".to_string(),
            ));
        }
        if self.rate_limit.user_rps == 0 {
            return Err(ConfigError::ValidationError(
                "User RPS cannot be 0".to_string(),
            ));
        }
        Ok(())
    }
}

/// Get current configuration (sanitized)
pub async fn get_config(State(state): State<AppState>) -> Json<serde_json::Value> {
    // Return sanitized config (no secrets)
    Json(serde_json::json!({
        "server": {
            "host": state.config.server.host,
            "port": state.config.server.port,
            "worker_threads": state.config.server.worker_threads,
        },
        "rate_limit": {
            "global_rps": state.config.rate_limit.global_rps,
            "user_rps": state.config.rate_limit.user_rps,
            "user_burst": state.config.rate_limit.user_burst,
        },
        "health": {
            "detailed": state.config.health.detailed,
            "check_interval_secs": state.config.health.check_interval_secs,
        },
    }))
}
