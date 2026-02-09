# VEL Rust Gateway Dockerfile
# High-performance WebSocket gateway for real-time trading data

# Build stage
FROM rust:1.75-bookworm as builder

WORKDIR /app

# Copy Cargo files first for dependency caching
COPY Cargo.toml Cargo.lock ./

# Create dummy src to cache dependencies
RUN mkdir src && \
    echo "fn main() {}" > src/main.rs && \
    cargo build --release && \
    rm -rf src

# Copy actual source code
COPY src ./src

# Build the actual application
RUN touch src/main.rs && cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the compiled binary
COPY --from=builder /app/target/release/vel_gateway /app/vel_gateway

# Create non-root user
RUN useradd -r -s /bin/false veluser && \
    chown -R veluser:veluser /app

USER veluser

# Expose WebSocket port
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

# Environment variables
ENV RUST_LOG=info
ENV VEL_GATEWAY_PORT=8081
ENV VEL_GATEWAY_HOST=0.0.0.0

# Run the gateway
CMD ["/app/vel_gateway"]
