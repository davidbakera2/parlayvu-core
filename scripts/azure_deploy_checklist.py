from textwrap import dedent

DEFAULT_LOCATION = "eastus2"
DEFAULT_RESOURCE_GROUP = "rg-parlayvu-demo"
DEFAULT_REGISTRY = "parlayvucore"
DEFAULT_ENVIRONMENT = "parlayvu-container-env"
DEFAULT_APP = "parlayvu-api"
DEFAULT_IMAGE_TAG = "demo"


def build_azure_steps(
    location: str = DEFAULT_LOCATION,
    resource_group: str = DEFAULT_RESOURCE_GROUP,
    registry: str = DEFAULT_REGISTRY,
    environment: str = DEFAULT_ENVIRONMENT,
    app: str = DEFAULT_APP,
    image_tag: str = DEFAULT_IMAGE_TAG,
) -> list[dict[str, str]]:
    image = f"{registry}.azurecr.io/{app}:{image_tag}"
    return [
        {
            "title": "Set Deployment Variables",
            "command": dedent(
                f"""\
                $env:AZURE_LOCATION="{location}"
                $env:AZURE_RESOURCE_GROUP="{resource_group}"
                $env:AZURE_REGISTRY="{registry}"
                $env:AZURE_CONTAINER_ENV="{environment}"
                $env:AZURE_CONTAINER_APP="{app}"
                $env:IMAGE_TAG="{image_tag}"
                """
            ).strip(),
        },
        {
            "title": "Confirm Azure Account",
            "command": "az account show --output table",
        },
        {
            "title": "Install Container Apps Extension",
            "command": "az extension add --name containerapp --upgrade",
        },
        {
            "title": "Register Required Providers",
            "command": dedent(
                """\
                az provider register --namespace Microsoft.App
                az provider register --namespace Microsoft.OperationalInsights
                az provider register --namespace Microsoft.ContainerRegistry
                """
            ).strip(),
        },
        {
            "title": "Create Resource Group",
            "command": 'az group create --name "$env:AZURE_RESOURCE_GROUP" --location "$env:AZURE_LOCATION"',
        },
        {
            "title": "Create Azure Container Registry",
            "command": (
                'az acr create --resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--name "$env:AZURE_REGISTRY" --sku Basic --admin-enabled true'
            ),
        },
        {
            "title": "Build And Push Image In Azure",
            "command": (
                'az acr build --registry "$env:AZURE_REGISTRY" '
                '--image "$env:AZURE_CONTAINER_APP:$env:IMAGE_TAG" .'
            ),
        },
        {
            "title": "Create Log Analytics Workspace",
            "command": (
                'az monitor log-analytics workspace create '
                '--resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--workspace-name parlayvu-logs '
                '--location "$env:AZURE_LOCATION"'
            ),
        },
        {
            "title": "Create Container Apps Environment",
            "command": (
                'az containerapp env create '
                '--name "$env:AZURE_CONTAINER_ENV" '
                '--resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--location "$env:AZURE_LOCATION" '
                '--logs-workspace-id "$(az monitor log-analytics workspace show '
                '--resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--workspace-name parlayvu-logs --query customerId -o tsv)" '
                '--logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys '
                '--resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--workspace-name parlayvu-logs --query primarySharedKey -o tsv)"'
            ),
        },
        {
            "title": "Create Container App",
            "command": dedent(
                f"""\
                az containerapp create \\
                  --name "$env:AZURE_CONTAINER_APP" \\
                  --resource-group "$env:AZURE_RESOURCE_GROUP" \\
                  --environment "$env:AZURE_CONTAINER_ENV" \\
                  --image "{image}" \\
                  --target-port 8000 \\
                  --ingress external \\
                  --min-replicas 1 \\
                  --max-replicas 3 \\
                  --cpu 0.5 \\
                  --memory 1.0Gi \\
                  --env-vars PROJECT_MEMORY_ENABLED=true MICROSOFT_GRAPH_ALLOW_SEND=false
                """
            ).strip(),
        },
        {
            "title": "Set Container App Secrets",
            "command": (
                "# Add secrets from infra/azure/secrets.env.example with "
                "`az containerapp secret set --secrets NAME=value`."
            ),
        },
        {
            "title": "Check Health",
            "command": (
                '$host = az containerapp show --name "$env:AZURE_CONTAINER_APP" '
                '--resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--query properties.configuration.ingress.fqdn -o tsv; '
                'Invoke-RestMethod -Uri "https://$host/health" | ConvertTo-Json -Depth 20'
            ),
        },
        {
            "title": "Check Readiness",
            "command": (
                '$host = az containerapp show --name "$env:AZURE_CONTAINER_APP" '
                '--resource-group "$env:AZURE_RESOURCE_GROUP" '
                '--query properties.configuration.ingress.fqdn -o tsv; '
                'Invoke-RestMethod -Uri "https://$host/readiness" | ConvertTo-Json -Depth 20'
            ),
        },
    ]


def render_azure_checklist(
    location: str = DEFAULT_LOCATION,
    resource_group: str = DEFAULT_RESOURCE_GROUP,
    registry: str = DEFAULT_REGISTRY,
) -> str:
    lines = [
        "# ParlayVU Azure Container Apps Deployment Checklist",
        "",
        f"Location: {location}",
        f"Resource group: {resource_group}",
        f"Container registry: {registry}",
        "",
        "This path keeps Neon Postgres as the database through `DATABASE_URL`.",
        "Replace placeholder values before running these commands.",
        "",
        "Required files:",
        "- `Dockerfile`",
        "- `infra/azure/secrets.env.example`",
        "",
    ]
    for index, step in enumerate(
        build_azure_steps(location=location, resource_group=resource_group, registry=registry),
        start=1,
    ):
        lines.extend(
            [
                f"## {index}. {step['title']}",
                "",
                "```powershell",
                step["command"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Teams Endpoint",
            "",
            dedent(
                """\
                After deployment, set the Azure Bot messaging endpoint to:
                `https://<container-app-fqdn>/teams/messages`
                """
            ).strip(),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    print(render_azure_checklist())


if __name__ == "__main__":
    main()
