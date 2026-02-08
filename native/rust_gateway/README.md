# VEL High-Performance Rust Gateway

Production-grade gateway service providing:

- **Rate Limiting**: Per-user and global rate limiting with burst support
- **Intent Routing**: Routes trading intents to appropriate backend services
- **REST API**: RESTful endpoints for all gateway operations
- **Health Checks**: Kubernetes-compatible liveness and readiness probes
- **Metrics**: Prometheus-compatible metrics for monitoring
- **High Performance**: Built with Tokio async runtime for maximum throughput

## Building

```bash
cd native/rust_gateway
cargo build --release
```

## Running

```bash
# With defaults
./target/release/vel_gateway

# With environment configuration
VEL_GATEWAY__SERVER__PORT=8080 ./target/release/vel_gateway

# With config file
cp gateway_config.example.toml gateway_config.toml
./target/release/vel_gateway
```

## API Endpoints

### Public Endpoints

- `GET /health` - Comprehensive health status
- `GET /health/live` - Kubernetes liveness probe
- `GET /health/ready` - Kubernetes readiness probe
- `GET /metrics` - Prometheus metrics

### API Endpoints (Rate Limited)

- `POST /api/v1/intent` - Submit a trading intent
- `GET /api/v1/intent/:id` - Get intent status
- `POST /api/v1/intent/:id/cancel` - Cancel an intent
- `POST /api/v1/quote` - Get a quote for a swap
- `POST /api/v1/routes` - Get available routes for a swap

### Admin Endpoints

- `GET /admin/config` - Get current configuration
- `GET /admin/stats` - Get gateway statistics

## Configuration

Configuration can be provided via:
1. Default values
2. `gateway_config.toml` file
3. Environment variables (prefixed with `VEL_GATEWAY__`)

### Environment Variables

```bash
VEL_GATEWAY__SERVER__HOST=0.0.0.0
VEL_GATEWAY__SERVER__PORT=8080
VEL_GATEWAY__RATE_LIMIT__GLOBAL_RPS=10000
VEL_GATEWAY__RATE_LIMIT__USER_RPS=100
VEL_GATEWAY__RATE_LIMIT__USER_BURST=200
VEL_GATEWAY__ROUTING__DEFAULT_BACKEND=http://localhost:5000
VEL_GATEWAY__ROUTING__EXECUTION_BACKEND=http://localhost:5001
```

## Testing

```bash
cargo test
```

## Docker

```bash
docker build -t vel-gateway -f Dockerfile.gateway .
docker run -p 8080:8080 vel-gateway
```
