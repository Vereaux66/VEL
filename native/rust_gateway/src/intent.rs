//! Intent routing module for VEL Gateway
//!
//! Routes trading intents to appropriate backend services for execution.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    Json,
};
use chrono::{DateTime, Utc};
use dashmap::DashMap;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::{debug, error, info, warn};
use uuid::Uuid;

use crate::config::RoutingConfig;
use crate::error::{GatewayError, GatewayResult};
use crate::AppState;

/// Intent type for routing decisions
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentType {
    Swap,
    AddLiquidity,
    RemoveLiquidity,
    Stake,
    Unstake,
    Bridge,
    AtomicSwap,
}

/// Intent status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentStatus {
    Pending,
    Validating,
    Routing,
    Executing,
    Completed,
    Failed,
    Cancelled,
}

/// Trading intent structure
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradingIntent {
    pub intent_id: String,
    pub intent_type: IntentType,
    pub wallet_address: String,
    pub chain_id: u64,
    pub parameters: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub status: IntentStatus,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub execution_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tx_hash: Option<String>,
}

/// Submit intent request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubmitIntentRequest {
    pub intent_type: IntentType,
    pub wallet_address: String,
    pub chain_id: u64,
    pub parameters: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<String>,
}

/// Submit intent response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubmitIntentResponse {
    pub intent_id: String,
    pub status: IntentStatus,
    pub estimated_gas: Option<u64>,
    pub estimated_execution_time_ms: Option<u64>,
}

/// Intent router for directing intents to appropriate backends
pub struct IntentRouter {
    /// HTTP client for backend communication
    pub client: Client,
    /// Configuration
    config: RoutingConfig,
    /// Intent cache for status tracking
    intent_cache: Arc<DashMap<String, TradingIntent>>,
}

impl IntentRouter {
    /// Create new intent router
    pub fn new(config: &RoutingConfig) -> GatewayResult<Self> {
        let client = Client::builder()
            .timeout(Duration::from_millis(config.timeout_ms))
            .pool_max_idle_per_host(10)
            .build()
            .map_err(|e| GatewayError::Config(format!("Failed to create HTTP client: {}", e)))?;

        Ok(Self {
            client,
            config: config.clone(),
            intent_cache: Arc::new(DashMap::new()),
        })
    }

    /// Route an intent to the appropriate backend
    pub async fn route_intent(&self, request: SubmitIntentRequest) -> GatewayResult<TradingIntent> {
        // Generate intent ID
        let intent_id = Uuid::new_v4().to_string();

        // Create intent record
        let intent = TradingIntent {
            intent_id: intent_id.clone(),
            intent_type: request.intent_type,
            wallet_address: request.wallet_address.clone(),
            chain_id: request.chain_id,
            parameters: request.parameters.clone(),
            created_at: Utc::now(),
            status: IntentStatus::Pending,
            error: None,
            execution_id: None,
            tx_hash: None,
        };

        // Store in cache
        self.intent_cache.insert(intent_id.clone(), intent.clone());

        // Determine backend based on intent type
        let backend_url = self.get_backend_for_intent(&request.intent_type);

        // Forward to backend
        let response = self.forward_to_backend(backend_url, &intent).await?;

        // Update cache with backend response
        if let Some(mut cached) = self.intent_cache.get_mut(&intent_id) {
            cached.status = IntentStatus::Validating;
            if let Some(exec_id) = response.get("execution_id").and_then(|v| v.as_str()) {
                cached.execution_id = Some(exec_id.to_string());
            }
        }

        Ok(intent)
    }

    /// Get intent by ID
    pub fn get_intent(&self, intent_id: &str) -> Option<TradingIntent> {
        self.intent_cache.get(intent_id).map(|r| r.clone())
    }

    /// Cancel an intent
    pub async fn cancel_intent(&self, intent_id: &str) -> GatewayResult<TradingIntent> {
        let mut intent = self
            .intent_cache
            .get_mut(intent_id)
            .ok_or_else(|| GatewayError::IntentNotFound(intent_id.to_string()))?;

        // Only pending/validating intents can be cancelled
        match intent.status {
            IntentStatus::Pending | IntentStatus::Validating => {
                intent.status = IntentStatus::Cancelled;
                Ok(intent.clone())
            }
            _ => Err(GatewayError::InvalidRequest(format!(
                "Cannot cancel intent in status {:?}",
                intent.status
            ))),
        }
    }

    /// Get backend URL for intent type
    fn get_backend_for_intent(&self, intent_type: &IntentType) -> &str {
        match intent_type {
            IntentType::Swap | IntentType::AtomicSwap => &self.config.execution_backend,
            IntentType::AddLiquidity
            | IntentType::RemoveLiquidity
            | IntentType::Stake
            | IntentType::Unstake => &self.config.execution_backend,
            IntentType::Bridge => &self.config.execution_backend,
        }
    }

    /// Forward intent to backend with retries
    async fn forward_to_backend(
        &self,
        backend_url: &str,
        intent: &TradingIntent,
    ) -> GatewayResult<serde_json::Value> {
        let url = format!("{}/api/intent", backend_url);
        let mut last_error = None;

        for attempt in 0..self.config.max_retries {
            if attempt > 0 {
                tokio::time::sleep(Duration::from_millis(
                    self.config.retry_delay_ms * (2_u64.pow(attempt as u32)),
                ))
                .await;
            }

            match self
                .client
                .post(&url)
                .json(intent)
                .send()
                .await
            {
                Ok(response) => {
                    if response.status().is_success() {
                        let body: serde_json::Value = response.json().await?;
                        debug!("Backend response: {:?}", body);
                        return Ok(body);
                    } else {
                        let status = response.status();
                        let error_body = response.text().await.unwrap_or_default();
                        warn!(
                            "Backend returned error: {} - {}",
                            status, error_body
                        );
                        last_error = Some(GatewayError::BackendError(format!(
                            "{}: {}",
                            status, error_body
                        )));
                    }
                }
                Err(e) => {
                    warn!("Backend request failed: {}", e);
                    last_error = Some(e.into());
                }
            }
        }

        Err(last_error.unwrap_or_else(|| {
            GatewayError::BackendUnavailable("All retries exhausted".to_string())
        }))
    }
}

// HTTP Handlers

/// Submit a new trading intent
pub async fn submit_intent(
    State(state): State<AppState>,
    Json(request): Json<SubmitIntentRequest>,
) -> Result<(StatusCode, Json<SubmitIntentResponse>), GatewayError> {
    info!(
        "Received intent: type={:?}, wallet={}, chain={}",
        request.intent_type, request.wallet_address, request.chain_id
    );

    // Validate request
    validate_intent_request(&request)?;

    // Route intent
    let intent = state.intent_router.route_intent(request).await?;

    // Record metric
    state.metrics.record_intent_submitted();

    Ok((
        StatusCode::ACCEPTED,
        Json(SubmitIntentResponse {
            intent_id: intent.intent_id,
            status: intent.status,
            estimated_gas: None,
            estimated_execution_time_ms: Some(5000),
        }),
    ))
}

/// Get intent status
pub async fn get_intent_status(
    State(state): State<AppState>,
    Path(intent_id): Path<String>,
) -> Result<Json<TradingIntent>, GatewayError> {
    let intent = state
        .intent_router
        .get_intent(&intent_id)
        .ok_or_else(|| GatewayError::IntentNotFound(intent_id.clone()))?;

    Ok(Json(intent))
}

/// Cancel an intent
pub async fn cancel_intent(
    State(state): State<AppState>,
    Path(intent_id): Path<String>,
) -> Result<Json<TradingIntent>, GatewayError> {
    let intent = state.intent_router.cancel_intent(&intent_id).await?;
    state.metrics.record_intent_cancelled();
    Ok(Json(intent))
}

/// Validate intent request
fn validate_intent_request(request: &SubmitIntentRequest) -> GatewayResult<()> {
    // Validate wallet address format (basic check)
    if !request.wallet_address.starts_with("0x") || request.wallet_address.len() != 42 {
        return Err(GatewayError::InvalidRequest(
            "Invalid wallet address format".to_string(),
        ));
    }

    // Validate chain ID (must be non-zero)
    if request.chain_id == 0 {
        return Err(GatewayError::InvalidRequest(
            "Chain ID must be non-zero".to_string(),
        ));
    }

    // Validate parameters based on intent type
    match request.intent_type {
        IntentType::Swap => validate_swap_params(&request.parameters)?,
        IntentType::AddLiquidity | IntentType::RemoveLiquidity => {
            validate_liquidity_params(&request.parameters)?
        }
        IntentType::Bridge => validate_bridge_params(&request.parameters)?,
        _ => {} // Other types have more flexible parameters
    }

    Ok(())
}

fn validate_swap_params(params: &serde_json::Value) -> GatewayResult<()> {
    if params.get("token_in").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing token_in parameter".to_string(),
        ));
    }
    if params.get("token_out").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing token_out parameter".to_string(),
        ));
    }
    if params.get("amount_in").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing amount_in parameter".to_string(),
        ));
    }
    Ok(())
}

fn validate_liquidity_params(params: &serde_json::Value) -> GatewayResult<()> {
    if params.get("pool_address").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing pool_address parameter".to_string(),
        ));
    }
    Ok(())
}

fn validate_bridge_params(params: &serde_json::Value) -> GatewayResult<()> {
    if params.get("destination_chain").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing destination_chain parameter".to_string(),
        ));
    }
    if params.get("token").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing token parameter".to_string(),
        ));
    }
    if params.get("amount").is_none() {
        return Err(GatewayError::InvalidRequest(
            "Missing amount parameter".to_string(),
        ));
    }
    Ok(())
}
