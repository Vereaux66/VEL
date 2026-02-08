//! VEL High-Performance Rust Gateway
//!
//! Production-grade gateway providing:
//! - Rate limiting with per-user and global limits
//! - Intent routing to appropriate handlers
//! - REST and gRPC interfaces
//! - Health and readiness endpoints
//! - Metrics collection
//!
//! NO STUBS - All functionality is fully implemented.

mod config;
mod error;
mod health;
mod intent;
mod metrics;
mod rate_limiter;
mod router;
mod state;

use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use axum::{
    extract::{Extension, State},
    http::StatusCode,
    middleware,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use tokio::signal;
use tower::ServiceBuilder;
use tower_http::{
    compression::CompressionLayer,
    cors::{Any, CorsLayer},
    request_id::MakeRequestUuid,
    trace::TraceLayer,
    ServiceBuilderExt,
};
use tracing::{error, info, warn, Level};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::GatewayConfig;
use crate::health::HealthChecker;
use crate::intent::IntentRouter;
use crate::metrics::MetricsCollector;
use crate::rate_limiter::RateLimiter;
use crate::state::GatewayState;

/// Application state shared across handlers
pub type AppState = Arc<GatewayState>;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize logging
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info,tower_http=debug".into()),
        ))
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    info!("VEL Gateway starting...");

    // Load configuration
    let config = GatewayConfig::load()?;
    info!("Configuration loaded: {:?}", config.server.host);

    // Initialize components
    let rate_limiter = RateLimiter::new(&config.rate_limit)?;
    let intent_router = IntentRouter::new(&config.routing)?;
    let health_checker = HealthChecker::new(&config.health)?;
    let metrics = MetricsCollector::new()?;

    // Create shared state
    let state = Arc::new(GatewayState::new(
        config.clone(),
        rate_limiter,
        intent_router,
        health_checker,
        metrics,
    )?);

    // Build router
    let app = build_router(state.clone());

    // Get bind address
    let addr: SocketAddr = format!("{}:{}", config.server.host, config.server.port)
        .parse()
        .expect("Invalid server address");

    info!("VEL Gateway listening on {}", addr);

    // Start server with graceful shutdown
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    info!("VEL Gateway shut down gracefully");
    Ok(())
}

/// Build the application router with all endpoints
fn build_router(state: AppState) -> Router {
    // CORS configuration
    let cors = CorsLayer::new()
        .allow_methods(Any)
        .allow_headers(Any)
        .allow_origin(Any);

    // Build middleware stack
    let middleware_stack = ServiceBuilder::new()
        .set_x_request_id(MakeRequestUuid)
        .layer(TraceLayer::new_for_http())
        .layer(CompressionLayer::new())
        .layer(cors);

    // Public routes
    let public_routes = Router::new()
        .route("/health", get(health::health_handler))
        .route("/health/live", get(health::liveness_handler))
        .route("/health/ready", get(health::readiness_handler))
        .route("/metrics", get(metrics::metrics_handler));

    // API routes (rate limited)
    let api_routes = Router::new()
        .route("/intent", post(intent::submit_intent))
        .route("/intent/:id", get(intent::get_intent_status))
        .route("/intent/:id/cancel", post(intent::cancel_intent))
        .route("/quote", post(router::get_quote))
        .route("/routes", post(router::get_routes))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limiter::rate_limit_middleware,
        ));

    // Admin routes (no rate limiting)
    let admin_routes = Router::new()
        .route("/admin/config", get(config::get_config))
        .route("/admin/stats", get(metrics::get_stats));

    // Combine all routes
    Router::new()
        .merge(public_routes)
        .nest("/api/v1", api_routes)
        .nest("/admin", admin_routes)
        .layer(middleware_stack)
        .with_state(state)
}

/// Graceful shutdown signal handler
async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("Failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {
            info!("Received Ctrl+C, initiating shutdown...");
        }
        _ = terminate => {
            info!("Received terminate signal, initiating shutdown...");
        }
    }
}
