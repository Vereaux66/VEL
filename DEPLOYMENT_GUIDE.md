# VEL Trading Platform - Quick Deployment Guide

This is a quick reference guide for deploying VEL to AWS. For the comprehensive checklist, see [AWS_DEPLOYMENT_READINESS.md](AWS_DEPLOYMENT_READINESS.md).

## Pre-Deployment Checklist

Run the automated readiness check:

```bash
./scripts/aws_deployment_readiness_check.sh --verbose
```

## Deployment Methods

### Method 1: Automated Deployment (Recommended)

**Via GitHub Actions** - Push to trigger CI/CD:

```bash
# Deploy to staging
git push origin develop

# Deploy to production
git push origin main
```

Monitor at: https://github.com/Vereaux66/VEL/actions

---

### Method 2: One-Command Deployment

**Prerequisites**: AWS credentials configured, kubectl and helm installed

```bash
# Set environment
export VEL_REGION="us-east-1"
export VEL_EKS_NAME="vel-prod"
export VEL_DNS_ZONE="kessann.bot"
export VEL_ENVIRONMENT="production"

# Deploy everything
cd aws && ./deploy.sh
```

This script will:
- ✅ Validate prerequisites
- ✅ Provision infrastructure (Terraform)
- ✅ Build and push Docker image to ECR
- ✅ Deploy application (Helm)
- ✅ Verify deployment health

---

### Method 3: Manual Step-by-Step

#### Step 1: Provision Infrastructure

```bash
cd aws/terraform

# Initialize Terraform
terraform init

# Review changes
terraform plan

# Apply infrastructure
terraform apply -auto-approve
```

**Created resources:**
- EKS cluster (vel-prod)
- RDS PostgreSQL database
- ElastiCache Redis cluster
- VPC with public/private subnets
- Application Load Balancer
- WAF rules
- CloudWatch log groups
- Secrets Manager secrets

#### Step 2: Configure kubectl

```bash
aws eks update-kubeconfig --name vel-prod --region us-east-1
kubectl get nodes
```

#### Step 3: Build and Push Docker Image

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build image
docker build -t vel-trading:latest -f Dockerfile .

# Tag image
docker tag vel-trading:latest \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading:latest

# Push image
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading:latest
```

#### Step 4: Set Secrets

**⚠️ SECURITY WARNING:**
- The values file approach creates plaintext secrets on disk
- **NEVER** use this method in CI/CD pipelines
- **NEVER** commit values files to version control, even temporarily
- For production, use AWS Secrets Manager (recommended) or `helm --set` with environment variables

```bash
# Generate secure keys
FLASK_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
WEB_PASSWORD="your-secure-password-min-12-chars"

# Get endpoints from Terraform outputs
cd aws/terraform
RDS_ENDPOINT=$(terraform output -raw vel_db_endpoint)
REDIS_ENDPOINT=$(terraform output -raw vel_redis_endpoint)
cd ../..

# Option 1: Use environment variables with helm --set (RECOMMENDED)
# Using "trading" as the release name will create:
# - Deployment: vel-trading-engine
# - Service: vel-trading-endpoint
helm upgrade --install trading ./aws/helm/vel \
  --namespace vel-system \
  --create-namespace \
  --set velConfig.flaskSecretKey="$FLASK_SECRET" \
  --set velConfig.jwtSecretKey="$JWT_SECRET" \
  --set velConfig.webPassword="$WEB_PASSWORD" \
  --set velConfig.dbHost="$RDS_ENDPOINT" \
  --set velConfig.redisHost="$REDIS_ENDPOINT" \
  --set image.repository="<account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading" \
  --set image.tag="latest" \
  --wait --timeout 15m

# Option 2: Use a values file (NOT RECOMMENDED - creates plaintext secrets)
# Only use for development/testing
cat > production-values.yaml <<EOF
global:
  environment: production
  domain: kessann.bot

image:
  repository: <account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading
  tag: latest

velConfig:
  flaskSecretKey: "$FLASK_SECRET"
  jwtSecretKey: "$JWT_SECRET"
  webPassword: "$WEB_PASSWORD"
  dbHost: "$RDS_ENDPOINT"
  redisHost: "$REDIS_ENDPOINT"

autoscaling:
  minReplicas: 6
  maxReplicas: 24
EOF

# IMPORTANT: Add to .gitignore immediately
echo "production-values.yaml" >> .gitignore

# Deploy with values file (using "trading" as release name)
helm upgrade --install trading ./aws/helm/vel \
  --namespace vel-system \
  --values production-values.yaml \
  --wait --timeout 15m

# Remove the file after deployment
rm production-values.yaml
```

#### Step 5: Deploy with Helm

```bash
# Create namespace
kubectl create namespace vel-system

# Note: The Helm chart generates resource names like:
# - Deployment: vel-<release-name>-engine
# - Service: vel-<release-name>-endpoint
# Where <release-name> is "trading" in this example

# Deploy application
helm upgrade --install trading ./aws/helm/vel \
  --namespace vel-system \
  --set image.repository="<ecr-repo>/vel-trading" \
  --set image.tag="latest" \
  --set velConfig.flaskSecretKey="$FLASK_SECRET" \
  --set velConfig.jwtSecretKey="$JWT_SECRET" \
  --set velConfig.webPassword="$WEB_PASSWORD" \
  --set velConfig.dbHost="$RDS_ENDPOINT" \
  --set velConfig.redisHost="$REDIS_ENDPOINT" \
  --wait --timeout 15m

# Verify deployment (using actual generated names)
kubectl rollout status deployment/vel-trading-engine -n vel-system
kubectl get pods -n vel-system -l vel.kessann.bot/app=trading-engine
```

---

## Post-Deployment Verification

### 1. Check Pod Status

```bash
kubectl get pods -n vel-system
kubectl logs -n vel-system -l app=vel-trading --tail=50
```

### 2. Test Health Endpoint

```bash
# Get service URL
kubectl get ingress -n vel-system

# Test health
curl https://kessann.bot/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-08T12:00:00Z",
  "version": "1.0.0"
}
```

### 3. Verify Database Connection

```bash
kubectl exec -it -n vel-system deployment/vel-trading -- \
  python -c "import psycopg2; print('DB OK')"
```

### 4. Check Monitoring

```bash
# CloudWatch logs
aws logs tail /vel/application --follow --region us-east-1

# Prometheus metrics (port forward to the service)
# Note: Service name depends on Helm release name, e.g., "vel-trading-endpoint" for release "trading"
kubectl port-forward -n vel-system svc/vel-trading-endpoint 8080:80
curl http://localhost:8080/metrics
```

### 5. Run Smoke Tests

```bash
# API status
curl https://kessann.bot/api/status

# Frontend loads
curl -I https://kessann.bot

# WebSocket connection
wscat -c wss://kessann.bot/ws
```

---

## Troubleshooting

### Pods not starting

```bash
# Check pod status
kubectl get pods -n vel-system

# Check events
kubectl describe pod <pod-name> -n vel-system

# Check logs
kubectl logs <pod-name> -n vel-system
```

**Common issues:**
- Missing secrets: Check velConfig in Helm values
- Image pull error: Verify ECR permissions
- CrashLoopBackOff: Check application logs for errors

### Database connection fails

```bash
# Test from pod
kubectl exec -it -n vel-system deployment/vel-trading -- \
  pg_isready -h <rds-endpoint>

# Check security groups
aws ec2 describe-security-groups --region us-east-1 | grep vel
```

### Cannot access via domain

```bash
# Check ingress
kubectl get ingress -n vel-system -o yaml

# Check ALB
aws elbv2 describe-load-balancers --region us-east-1 | grep vel

# Check Route 53
aws route53 list-resource-record-sets --hosted-zone-id <zone-id>

# Check certificate
aws acm list-certificates --region us-east-1
```

---

## Rollback

### Quick rollback via Helm

```bash
# List releases
helm list -n vel-system

# View history
helm history vel-trading -n vel-system

# Rollback to previous version
helm rollback vel-trading -n vel-system
```

### Emergency stop

```bash
# Scale down to zero
kubectl scale deployment/vel-trading -n vel-system --replicas=0

# Scale back up after fix
kubectl scale deployment/vel-trading -n vel-system --replicas=6
```

---

## Updating Deployment

### Update application code

```bash
# Build and push new image
docker build -t vel-trading:v2 -f Dockerfile .
docker tag vel-trading:v2 <ecr-repo>/vel-trading:v2
docker push <ecr-repo>/vel-trading:v2

# Update deployment
helm upgrade vel-trading ./aws/helm/vel \
  --namespace vel-system \
  --set image.tag=v2 \
  --reuse-values \
  --wait
```

### Update configuration

```bash
# Update Helm values
helm upgrade vel-trading ./aws/helm/vel \
  --namespace vel-system \
  --values new-values.yaml \
  --wait
```

### Update infrastructure

```bash
cd aws/terraform
terraform plan
terraform apply
```

---

## Scaling

### Manual scaling

```bash
# Scale pods
kubectl scale deployment/vel-trading -n vel-system --replicas=12

# Scale nodes (if not using autoscaling)
aws eks update-nodegroup-config \
  --cluster-name vel-prod \
  --nodegroup-name vel-workers \
  --scaling-config minSize=12,maxSize=50,desiredSize=20
```

### Autoscaling (configured automatically)

- **HPA**: Scales pods based on CPU/memory (6-24 replicas)
- **Cluster Autoscaler**: Scales nodes based on pod demand (6-50 nodes)

---

## Cost Optimization

### Development/Testing

For non-production environments:

```bash
# Use smaller instances
terraform apply -var="vel_node_instance_type=t3.medium"

# Reduce replica count
helm upgrade vel-trading ./aws/helm/vel \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=6
```

### Production Savings

- Enable RDS Reserved Instances for 1-3 year commitment
- Use Savings Plans for EKS nodes
- Configure CloudWatch log retention (7-30 days)
- Enable S3 lifecycle policies for backups

---

## Support & Resources

- **Full Checklist**: [AWS_DEPLOYMENT_READINESS.md](AWS_DEPLOYMENT_READINESS.md)
- **Security Guide**: [SECURITY.md](SECURITY.md)
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Main README**: [README.md](README.md)

---

**Quick Commands Reference:**

```bash
# Check readiness
./scripts/aws_deployment_readiness_check.sh --verbose

# Deploy everything
cd aws && ./deploy.sh

# Check status
kubectl get all -n vel-system

# View logs
kubectl logs -n vel-system -l app=vel-trading --tail=100 -f

# Rollback
helm rollback vel-trading -n vel-system

# Scale
kubectl scale deployment/vel-trading -n vel-system --replicas=10
```

---

**Last Updated**: 2026-02-08  
**Version**: 1.0
