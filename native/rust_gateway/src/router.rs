//! Router module for VEL Gateway
//!
//! Provides routing and quote endpoints for trade routing.

use axum::{extract::State, http::StatusCode, Json};
use serde::{Deserialize, Serialize};
use tracing::{debug, info};

use crate::error::{GatewayError, GatewayResult};
use crate::AppState;

/// Quote request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuoteRequest {
    pub chain_id: u64,
    pub token_in: String,
    pub token_out: String,
    pub amount_in: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub slippage_bps: Option<u32>,
}

/// Quote response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuoteResponse {
    pub quote_id: String,
    pub chain_id: u64,
    pub token_in: String,
    pub token_out: String,
    pub amount_in: String,
    pub amount_out: String,
    pub price_impact_bps: u32,
    pub routes: Vec<RouteInfo>,
    pub estimated_gas: u64,
    pub expires_at: u64,
}

/// Route information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteInfo {
    pub dex: String,
    pub pool_address: String,
    pub amount_in: String,
    pub amount_out: String,
    pub percentage: u32,
}

/// Get routes request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetRoutesRequest {
    pub chain_id: u64,
    pub token_in: String,
    pub token_out: String,
    pub amount_in: String,
    #[serde(default = "default_max_routes")]
    pub max_routes: u32,
}

fn default_max_routes() -> u32 {
    5
}

/// Get routes response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GetRoutesResponse {
    pub chain_id: u64,
    pub routes: Vec<DetailedRoute>,
}

/// Detailed route with full path
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetailedRoute {
    pub route_id: String,
    pub steps: Vec<RouteStep>,
    pub total_amount_out: String,
    pub total_gas: u64,
    pub price_impact_bps: u32,
    pub score: f64,
}

/// Single step in a route
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouteStep {
    pub dex: String,
    pub pool_address: String,
    pub token_in: String,
    pub token_out: String,
    pub amount_in: String,
    pub amount_out: String,
}

/// Get a quote for a swap
pub async fn get_quote(
    State(state): State<AppState>,
    Json(request): Json<QuoteRequest>,
) -> Result<Json<QuoteResponse>, GatewayError> {
    info!(
        "Quote request: chain={}, {} -> {}, amount={}",
        request.chain_id, request.token_in, request.token_out, request.amount_in
    );

    // Validate request
    validate_quote_request(&request)?;

    // Forward to backend for actual quote calculation
    let quote = fetch_quote_from_backend(&state, &request).await?;

    // Record metric
    state.metrics.record_request("/quote", "POST", 0.0);

    Ok(Json(quote))
}

/// Get available routes for a swap
pub async fn get_routes(
    State(state): State<AppState>,
    Json(request): Json<GetRoutesRequest>,
) -> Result<Json<GetRoutesResponse>, GatewayError> {
    info!(
        "Routes request: chain={}, {} -> {}, amount={}",
        request.chain_id, request.token_in, request.token_out, request.amount_in
    );

    // Validate request
    validate_routes_request(&request)?;

    // Forward to backend
    let routes = fetch_routes_from_backend(&state, &request).await?;

    // Record metric
    state.metrics.record_request("/routes", "POST", 0.0);

    Ok(Json(routes))
}

/// Validate quote request
fn validate_quote_request(request: &QuoteRequest) -> GatewayResult<()> {
    if request.chain_id == 0 {
        return Err(GatewayError::InvalidRequest(
            "Chain ID must be non-zero".to_string(),
        ));
    }

    if !request.token_in.starts_with("0x") || request.token_in.len() != 42 {
        return Err(GatewayError::InvalidRequest(
            "Invalid token_in address".to_string(),
        ));
    }

    if !request.token_out.starts_with("0x") || request.token_out.len() != 42 {
        return Err(GatewayError::InvalidRequest(
            "Invalid token_out address".to_string(),
        ));
    }

    // Validate amount is numeric
    if request.amount_in.parse::<u128>().is_err() {
        return Err(GatewayError::InvalidRequest(
            "Invalid amount_in".to_string(),
        ));
    }

    Ok(())
}

/// Validate routes request
fn validate_routes_request(request: &GetRoutesRequest) -> GatewayResult<()> {
    if request.chain_id == 0 {
        return Err(GatewayError::InvalidRequest(
            "Chain ID must be non-zero".to_string(),
        ));
    }

    if !request.token_in.starts_with("0x") || request.token_in.len() != 42 {
        return Err(GatewayError::InvalidRequest(
            "Invalid token_in address".to_string(),
        ));
    }

    if !request.token_out.starts_with("0x") || request.token_out.len() != 42 {
        return Err(GatewayError::InvalidRequest(
            "Invalid token_out address".to_string(),
        ));
    }

    if request.max_routes == 0 || request.max_routes > 10 {
        return Err(GatewayError::InvalidRequest(
            "max_routes must be between 1 and 10".to_string(),
        ));
    }

    Ok(())
}

/// Fetch quote from backend (placeholder for actual implementation)
async fn fetch_quote_from_backend(
    state: &AppState,
    request: &QuoteRequest,
) -> GatewayResult<QuoteResponse> {
    let url = format!(
        "{}/api/quote",
        state.config.routing.execution_backend
    );

    match state
        .intent_router
        .client
        .post(&url)
        .json(request)
        .send()
        .await
    {
        Ok(response) => {
            if response.status().is_success() {
                let quote: QuoteResponse = response.json().await?;
                Ok(quote)
            } else {
                // Backend unavailable, return mock response for development
                debug!("Backend unavailable, returning mock quote");
                Ok(mock_quote_response(request))
            }
        }
        Err(e) => {
            // Backend unavailable, return mock response for development
            debug!("Backend error: {}, returning mock quote", e);
            Ok(mock_quote_response(request))
        }
    }
}

/// Fetch routes from backend (placeholder for actual implementation)
async fn fetch_routes_from_backend(
    state: &AppState,
    request: &GetRoutesRequest,
) -> GatewayResult<GetRoutesResponse> {
    let url = format!(
        "{}/api/routes",
        state.config.routing.execution_backend
    );

    match state
        .intent_router
        .client
        .post(&url)
        .json(request)
        .send()
        .await
    {
        Ok(response) => {
            if response.status().is_success() {
                let routes: GetRoutesResponse = response.json().await?;
                Ok(routes)
            } else {
                debug!("Backend unavailable, returning mock routes");
                Ok(mock_routes_response(request))
            }
        }
        Err(e) => {
            debug!("Backend error: {}, returning mock routes", e);
            Ok(mock_routes_response(request))
        }
    }
}

/// Mock quote response for development/testing
fn mock_quote_response(request: &QuoteRequest) -> QuoteResponse {
    let amount_in: u128 = request.amount_in.parse().unwrap_or(0);
    // Simulate 0.3% fee and 0.5% slippage
    let amount_out = amount_in * 993 / 1000;

    QuoteResponse {
        quote_id: uuid::Uuid::new_v4().to_string(),
        chain_id: request.chain_id,
        token_in: request.token_in.clone(),
        token_out: request.token_out.clone(),
        amount_in: request.amount_in.clone(),
        amount_out: amount_out.to_string(),
        price_impact_bps: 50,
        routes: vec![RouteInfo {
            dex: "uniswap_v3".to_string(),
            pool_address: "0x0000000000000000000000000000000000000001".to_string(),
            amount_in: request.amount_in.clone(),
            amount_out: amount_out.to_string(),
            percentage: 100,
        }],
        estimated_gas: 150000,
        expires_at: chrono::Utc::now().timestamp() as u64 + 60,
    }
}

/// Mock routes response for development/testing
fn mock_routes_response(request: &GetRoutesRequest) -> GetRoutesResponse {
    let amount_in: u128 = request.amount_in.parse().unwrap_or(0);

    GetRoutesResponse {
        chain_id: request.chain_id,
        routes: vec![DetailedRoute {
            route_id: uuid::Uuid::new_v4().to_string(),
            steps: vec![RouteStep {
                dex: "uniswap_v3".to_string(),
                pool_address: "0x0000000000000000000000000000000000000001".to_string(),
                token_in: request.token_in.clone(),
                token_out: request.token_out.clone(),
                amount_in: request.amount_in.clone(),
                amount_out: (amount_in * 993 / 1000).to_string(),
            }],
            total_amount_out: (amount_in * 993 / 1000).to_string(),
            total_gas: 150000,
            price_impact_bps: 50,
            score: 0.95,
        }],
    }
}
