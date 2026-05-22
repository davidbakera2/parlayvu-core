# AWS Fargate Deployment Checklist

This checklist moves the ParlayVU FastAPI/LangGraph backend from local demo readiness to a hosted Fargate service.

## Target Shape

- Docker image in Amazon ECR.
- ECS Fargate service running `app.main:app` on port `8000`.
- Application Load Balancer forwarding HTTPS traffic to the ECS service.
- AWS Secrets Manager for production secrets.
- CloudWatch Logs under `/ecs/parlayvu-core`.
- Neon remains the database unless/until we move to RDS.
- Cloudflare Pages remains the home for generated static sites.

## Files

- `Dockerfile`: builds the backend container.
- `infra/aws/ecs-task-definition.template.json`: ECS task definition template.
- `infra/aws/secrets.env.example`: production secret inventory.
- `scripts/aws_deploy_checklist.py`: prints deployment steps and AWS CLI command templates.

## Required AWS Resources

1. ECR repository: `parlayvu-core`.
2. ECS cluster.
3. ECS task execution role with ECR pull, CloudWatch Logs, and Secrets Manager read access.
4. ECS task role for application-level AWS access.
5. CloudWatch log group: `/ecs/parlayvu-core`.
6. VPC, private subnets, security groups, and NAT or VPC endpoints for outbound API calls.
7. Application Load Balancer and target group.
8. Secrets Manager values under `/parlayvu/prod/<NAME>`.

## Deployment Flow

1. Rotate local secrets and store production values in AWS Secrets Manager.
2. Build and tag the Docker image.
3. Push the image to ECR.
4. Replace placeholders in `ecs-task-definition.template.json`.
5. Register the ECS task definition.
6. Create or update the ECS service.
7. Confirm `/health` returns `healthy`.
8. Confirm `/readiness` shows expected configured sections.
9. Run `python scripts/seed_demo.py` from a secure operator environment if demo data should exist in production memory.

## Security Notes

- Keep `MICROSOFT_GRAPH_ALLOW_SEND=false` until approval-card flow is fully tested in Teams.
- Do not put secrets in ECS `environment`; use ECS `secrets`.
- Keep generated Astro site deployment on Cloudflare Pages.
- Restrict production `ALLOWED_ORIGINS`.
- Rotate any credentials that were ever stored in local `.env` before investor sharing or production deployment.
