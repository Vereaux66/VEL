# 🚀 VEL Trading Platform - AWS Deployment Guide

## Quick Start (One-Click Deploy)

```bash
# Prerequisites: AWS CLI configured, Docker running, Terraform installed

# 1. Bootstrap Terraform state (first time only)
cd aws/terraform/bootstrap
terraform init && terraform apply -auto-approve
cd ../../..

# 2. Deploy everything
export AWS_REGION=us-east-1
export ANVEL_WEB_PASSWORD=$(openssl rand -base64 32)
./scripts/one_click_deploy.sh production
```

---

## Complete Deployment Steps

### Phase 1: Prerequisites

#### Required Tools
```bash
# Check versions
aws --version        # >= 2.0
terraform --version  # >= 1.5
kubectl version      # >= 1.28
helm version         # >= 3.0
docker --version     # >= 24.0
```

#### AWS Configuration
```bash
# Configure AWS CLI with production credentials
aws configure --profile vel-production
export AWS_PROFILE=vel-production
export AWS_REGION=us-east-1
```

### Phase 2: Terraform State Bootstrap

```bash
cd aws/terraform/bootstrap
terraform init
terraform apply

# Note the output and update providers.tf with backend config
```

### Phase 3: Infrastructure Deployment

```bash
cd aws/terraform

# Initialize with backend
terraform init

# Review plan
terraform plan -out=velplan

# Apply infrastructure
terraform apply velplan
```

This creates:
- ✅ VPC with public/private subnets
- ✅ EKS Kubernetes cluster
- ✅ RDS PostgreSQL database
- ✅ ElastiCache Redis cluster
- ✅ Application Load Balancer
- ✅ WAF security rules
- ✅ ECR container registry
- ✅ IAM roles and policies
- ✅ Secrets Manager secrets
- ✅ CloudWatch monitoring

### Phase 4: Container Build & Push

```bash
# Get ECR login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t vel-trading:latest .
docker tag vel-trading:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading:latest
```

### Phase 5: Kubernetes Deployment

```bash
# Configure kubectl
aws eks update-kubeconfig --region us-east-1 --name vel-prod

# Create namespace
kubectl create namespace vel-system

# Deploy with Helm
helm upgrade --install vel-trading ./aws/helm/vel-trading \
  --namespace vel-system \
  --set image.repository=<account-id>.dkr.ecr.us-east-1.amazonaws.com/vel-trading \
  --set image.tag=latest \
  --set global.environment=production \
  --wait --timeout 10m

# Verify deployment
kubectl get pods -n vel-system
kubectl get services -n vel-system
```

### Phase 6: Database Migration

```bash
# Get database endpoint from Terraform output
DB_HOST=$(terraform output -raw rds_endpoint)

# Run migrations
kubectl exec -it deploy/vel-trading -n vel-system -- \
  python scripts/db_migrate.py --apply
```

### Phase 7: DNS & SSL

```bash
# Get ALB DNS name
ALB_DNS=$(kubectl get ingress -n vel-system -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}')

# Create Route53 record (or update manually)
aws route53 change-resource-record-sets --hosted-zone-id <zone-id> \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "vel.kessann.bot",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "'$ALB_DNS'"}]
      }
    }]
  }'
```

---

## Environment Configuration

### Required Secrets (AWS Secrets Manager)

| Secret Name | Description |
|-------------|-------------|
| `vel/database/password` | RDS master password |
| `vel/redis/password` | ElastiCache auth token |
| `vel/wallet/private-key` | Trading wallet private key |
| `vel/web/password` | Web UI admin password |
| `vel/flask/secret-key` | Flask session secret |

### Environment Variables

Copy `.env.production.template` to `.env.production` and configure:

```bash
cp .env.production.template .env.production
# Edit with your values
```

---

## Monitoring & Observability

### CloudWatch Dashboards
- **VEL-Trading-Overview**: Main system metrics
- **VEL-Trading-Performance**: Trading latency and throughput
- **VEL-Infrastructure**: EKS, RDS, Redis metrics

### Prometheus Metrics
```bash
# Port-forward Prometheus
kubectl port-forward svc/vel-metrics -n vel-system 9090:9090

# Access at http://localhost:9090
```

### Log Groups
- `/vel/production/application`
- `/vel/production/trading`
- `/vel/production/security`

---

## Scaling Configuration

### Horizontal Pod Autoscaling
```yaml
# Configured in Helm values
autoscaling:
  minReplicas: 3
  maxReplicas: 50
  targetCPUPercent: 70
  targetMemoryPercent: 80
```

### EKS Node Scaling
```hcl
# Configured in Terraform
vel_node_scaling = {
  min_nodes     = 6
  max_nodes     = 50
  desired_nodes = 12
}
```

---

## Security Checklist

- [x] WAF enabled with rate limiting
- [x] Private subnets for EKS nodes
- [x] Secrets in AWS Secrets Manager
- [x] RDS encryption at rest
- [x] Redis encryption in transit
- [x] Container image scanning
- [x] Network policies in Kubernetes
- [x] IAM least-privilege roles
- [ ] Enable trading (set `TRADING_ENABLED=true`)
- [ ] Configure wallet private key
- [ ] Set up alerting contacts

---

## Troubleshooting

### Common Issues

**Pods not starting:**
```bash
kubectl describe pod <pod-name> -n vel-system
kubectl logs <pod-name> -n vel-system
```

**Database connection failed:**
```bash
# Check security group allows EKS -> RDS
aws ec2 describe-security-groups --group-ids <sg-id>
```

**Image pull errors:**
```bash
# Verify ECR permissions
aws ecr get-login-password --region us-east-1 | docker login ...
```

### Rollback

```bash
# Rollback Helm release
helm rollback vel-trading -n vel-system

# Or rollback via script
./scripts/one_click_deploy.sh production --rollback
```

---

## Cost Optimization

### Estimated Monthly Cost (Production)
| Service | Estimated Cost |
|---------|----------------|
| EKS Cluster | $73 |
| EC2 Nodes (6x m6i.large) | $550 |
| RDS PostgreSQL | $200 |
| ElastiCache Redis | $150 |
| ALB | $25 |
| Data Transfer | $50 |
| **Total** | **~$1,050/month** |

### Cost Reduction Tips
- Use Spot instances for non-critical workloads
- Right-size RDS based on actual usage
- Enable S3 intelligent tiering for logs

---

## Support

- Documentation: `/docs/`
- Issues: GitHub Issues
- Monitoring: CloudWatch Dashboards

**VEL Trading Platform - Fully Automated AWS Deployment**
