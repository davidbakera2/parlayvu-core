from textwrap import dedent

DEFAULT_REGION = "us-east-2"
DEFAULT_REPOSITORY = "parlayvu-core"


def build_aws_steps(region: str = DEFAULT_REGION, repository: str = DEFAULT_REPOSITORY) -> list[dict[str, str]]:
    account_id = "<account-id>"
    image = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repository}:<image-tag>"
    return [
        {
            "title": "Authenticate Docker To ECR",
            "command": (
                f"aws ecr get-login-password --region {region} | "
                f"docker login --username AWS --password-stdin {account_id}.dkr.ecr.{region}.amazonaws.com"
            ),
        },
        {
            "title": "Create ECR Repository",
            "command": f"aws ecr create-repository --repository-name {repository} --region {region}",
        },
        {
            "title": "Build Docker Image",
            "command": f"docker build -t {repository}:<image-tag> .",
        },
        {
            "title": "Tag Docker Image",
            "command": f"docker tag {repository}:<image-tag> {image}",
        },
        {
            "title": "Push Docker Image",
            "command": f"docker push {image}",
        },
        {
            "title": "Create CloudWatch Log Group",
            "command": f"aws logs create-log-group --log-group-name /ecs/{repository} --region {region}",
        },
        {
            "title": "Register ECS Task Definition",
            "command": (
                "aws ecs register-task-definition "
                "--cli-input-json file://infra/aws/ecs-task-definition.rendered.json "
                f"--region {region}"
            ),
        },
        {
            "title": "Update ECS Service",
            "command": (
                "aws ecs update-service "
                "--cluster <cluster-name> "
                "--service <service-name> "
                "--task-definition parlayvu-core "
                f"--region {region}"
            ),
        },
        {
            "title": "Check Health",
            "command": "Invoke-RestMethod -Uri https://<api-hostname>/health | ConvertTo-Json -Depth 20",
        },
        {
            "title": "Check Readiness",
            "command": "Invoke-RestMethod -Uri https://<api-hostname>/readiness | ConvertTo-Json -Depth 20",
        },
    ]


def render_aws_checklist(region: str = DEFAULT_REGION, repository: str = DEFAULT_REPOSITORY) -> str:
    lines = [
        "# ParlayVU AWS Fargate Deployment Checklist",
        "",
        f"Region: {region}",
        f"ECR repository: {repository}",
        "",
        "Replace placeholder values before running these commands.",
        "",
        "Required template files:",
        "- `infra/aws/ecs-task-definition.template.json`",
        "- `infra/aws/secrets.env.example`",
        "",
    ]
    for index, step in enumerate(build_aws_steps(region, repository), start=1):
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
            "## Secrets",
            "",
            dedent(
                """\
                Store production secrets under `/parlayvu/prod/<NAME>` in AWS Secrets Manager.
                Use `infra/aws/secrets.env.example` as the inventory, but never store real values in the repo.
                """
            ).strip(),
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    print(render_aws_checklist())


if __name__ == "__main__":
    main()
