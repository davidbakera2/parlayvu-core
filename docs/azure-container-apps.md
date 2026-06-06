# Azure Container Apps Deployment Checklist

This checklist moves the ParlayVU FastAPI/LangGraph backend to Azure while keeping Neon Postgres as the project-memory database.

## Target Shape

- Docker image in Azure Container Registry.
- Azure Container Apps service running `app.main:app` on port `8000`.
- Public HTTPS ingress for the API.
- Container App secrets for runtime values.
- Neon remains the database via `DATABASE_URL`.
- Log Analytics for application logs.
- Azure Bot messaging endpoint points to `/teams/messages`.

## Files

- `Dockerfile`: builds the backend container.
- `infra/azure/secrets.env.example`: production secret inventory.
- `scripts/azure_deploy_checklist.py`: prints Azure CLI command templates.

## Required Azure Resources

1. Resource group: `rg-parlayvu-demo` or `rg-parlayvu-prod`.
2. Azure Container Registry: globally unique name such as `parlayvucore`.
3. Log Analytics workspace.
4. Azure Container Apps environment.
5. Azure Container App with external ingress on port `8000`.
6. Container App secrets for all production runtime values.
7. Azure Bot messaging endpoint set to `https://<container-app-host>/teams/messages`.

## Deployment Flow

1. Rotate local secrets before investor-facing deployment.
2. Store production values as Container App secrets or Key Vault-backed secrets.
3. Build and push the Docker image to Azure Container Registry.
4. Create the Container Apps environment.
5. Deploy the API container with ingress enabled.
6. Confirm `/health` returns `healthy`.
7. Confirm `/readiness` returns `ready`.
8. Update the Azure Bot messaging endpoint to the hosted `/teams/messages` URL.

## Security Notes

- Keep `MICROSOFT_GRAPH_ALLOW_SEND=false` until Teams approval flow is fully rehearsed.
- Keep `PROJECT_MEMORY_ENABLED=true` only in configured demo/prod environments.
- Do not commit real `.env` values.
- Restrict production `ALLOWED_ORIGINS`.
- Prefer Key Vault once the first Container Apps deployment is stable.
- Add an Exchange Application Access Policy before production to limit app-only Graph mail access to ParlayVU agent mailboxes.
