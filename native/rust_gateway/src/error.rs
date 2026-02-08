//! Error handling module for VEL Gateway
//!
//! Provides unified error types and responses.

use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tracing::error;

/// API error response
#[derive(Debug, Serialize, Deserialize)]
pub struct ApiError {
    pub code: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
    pub request_id: Option<String>,
}

/// Gateway error types
#[derive(Debug, Error)]
pub enum GatewayError {
    #[error("Rate limit exceeded")]
    RateLimitExceeded,

    #[error("Invalid request: {0}")]
    InvalidRequest(String),

    #[error("Intent not found: {0}")]
    IntentNotFound(String),

    #[error("Backend unavailable: {0}")]
    BackendUnavailable(String),

    #[error("Backend error: {0}")]
    BackendError(String),

    #[error("Timeout: {0}")]
    Timeout(String),

    #[error("Internal error: {0}")]
    Internal(String),

    #[error("Configuration error: {0}")]
    Config(String),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("Unauthorized: {0}")]
    Unauthorized(String),

    #[error("Forbidden: {0}")]
    Forbidden(String),
}

impl GatewayError {
    pub fn status_code(&self) -> StatusCode {
        match self {
            GatewayError::RateLimitExceeded => StatusCode::TOO_MANY_REQUESTS,
            GatewayError::InvalidRequest(_) => StatusCode::BAD_REQUEST,
            GatewayError::IntentNotFound(_) => StatusCode::NOT_FOUND,
            GatewayError::BackendUnavailable(_) => StatusCode::SERVICE_UNAVAILABLE,
            GatewayError::BackendError(_) => StatusCode::BAD_GATEWAY,
            GatewayError::Timeout(_) => StatusCode::GATEWAY_TIMEOUT,
            GatewayError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
            GatewayError::Config(_) => StatusCode::INTERNAL_SERVER_ERROR,
            GatewayError::Serialization(_) => StatusCode::INTERNAL_SERVER_ERROR,
            GatewayError::Unauthorized(_) => StatusCode::UNAUTHORIZED,
            GatewayError::Forbidden(_) => StatusCode::FORBIDDEN,
        }
    }

    pub fn error_code(&self) -> &'static str {
        match self {
            GatewayError::RateLimitExceeded => "RATE_LIMIT_EXCEEDED",
            GatewayError::InvalidRequest(_) => "INVALID_REQUEST",
            GatewayError::IntentNotFound(_) => "INTENT_NOT_FOUND",
            GatewayError::BackendUnavailable(_) => "BACKEND_UNAVAILABLE",
            GatewayError::BackendError(_) => "BACKEND_ERROR",
            GatewayError::Timeout(_) => "TIMEOUT",
            GatewayError::Internal(_) => "INTERNAL_ERROR",
            GatewayError::Config(_) => "CONFIG_ERROR",
            GatewayError::Serialization(_) => "SERIALIZATION_ERROR",
            GatewayError::Unauthorized(_) => "UNAUTHORIZED",
            GatewayError::Forbidden(_) => "FORBIDDEN",
        }
    }
}

impl IntoResponse for GatewayError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let error_code = self.error_code();
        let message = self.to_string();

        // Log internal errors
        if status == StatusCode::INTERNAL_SERVER_ERROR {
            error!("Internal error: {}", message);
        }

        let body = Json(ApiError {
            code: error_code.to_string(),
            message,
            details: None,
            request_id: None,
        });

        (status, body).into_response()
    }
}

// Implement From for common error types
impl From<serde_json::Error> for GatewayError {
    fn from(err: serde_json::Error) -> Self {
        GatewayError::Serialization(err.to_string())
    }
}

impl From<reqwest::Error> for GatewayError {
    fn from(err: reqwest::Error) -> Self {
        if err.is_timeout() {
            GatewayError::Timeout(err.to_string())
        } else if err.is_connect() {
            GatewayError::BackendUnavailable(err.to_string())
        } else {
            GatewayError::BackendError(err.to_string())
        }
    }
}

impl From<anyhow::Error> for GatewayError {
    fn from(err: anyhow::Error) -> Self {
        GatewayError::Internal(err.to_string())
    }
}

/// Result type for gateway operations
pub type GatewayResult<T> = Result<T, GatewayError>;
