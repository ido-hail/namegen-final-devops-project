#!/usr/bin/env python3

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = PROJECT_ROOT / "terraform"
BOOTSTRAP_DIR = TERRAFORM_DIR / "bootstrap"
KUBERNETES_DIR = PROJECT_ROOT / "k8s"
MONITORING_DIR = PROJECT_ROOT / "monitoring"

PROJECT_TAG = "NameGen"
CLUSTER_NAME = "namegen-eks"
ECR_REPOSITORY = "namegen"
STATE_KEY = "namegen/terraform.tfstate"
KUBERNETES_NAMESPACE = "namegen"
MONGODB_SECRET_NAME = "mongodb-credentials"
IMAGE_PLACEHOLDER = "namegen-image:git-sha"

MONITORING_NAMESPACE = "monitoring"
MONITORING_RELEASE = "namegen-monitoring"
MONITORING_CHART = "prometheus-community/kube-prometheus-stack"
MONITORING_CHART_VERSION = "87.21.0"
PROMETHEUS_HELM_REPOSITORY_URL = (
    "https://prometheus-community.github.io/helm-charts"
)
GRAFANA_SECRET_NAME = "grafana-admin-credentials"

REQUIRED_TOOLS = (
    "aws",
    "terraform",
    "git",
    "docker",
    "kubectl",
    "helm",
)

REQUIRED_FILES = (
    "Dockerfile",
    "package.json",
    "package-lock.json",
    "terraform/backend.tf",
    "terraform/main.tf",
    "terraform/providers.tf",
    "terraform/variables.tf",
    "terraform/versions.tf",
    "terraform/bootstrap/main.tf",
    "terraform/bootstrap/outputs.tf",
    "terraform/bootstrap/providers.tf",
    "terraform/bootstrap/variables.tf",
    "terraform/bootstrap/versions.tf",
    "terraform/modules/network/main.tf",
    "terraform/modules/ecr/main.tf",
    "terraform/modules/eks/main.tf",
    "terraform/modules/github_oidc/main.tf",
    "k8s/kustomization.yaml",
    "k8s/namespace.yaml",
    "k8s/storage-class.yaml",
    "k8s/mongodb-init-configmap.yaml",
    "k8s/mongodb-service.yaml",
    "k8s/mongodb-statefulset.yaml",
    "k8s/namegen-deployment.yaml",
    "k8s/namegen-service.yaml",
    "monitoring/values.yaml",
    "monitoring/kustomization.yaml",
    "monitoring/namegen-dashboard-configmap.yaml",
)


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def heading(title):
    print(f"\n== {title} ==")


def run(command, cwd=None, allowed_codes=(0,), live=False):
    command_text = " ".join(str(part) for part in command)
    print(f"+ {command_text}")

    if live:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            check=False,
        )
    else:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            check=False,
            capture_output=True,
        )

    if result.returncode not in allowed_codes:
        if not live:
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)

        fail(
            f"Command failed with exit code {result.returncode}: "
            f"{command_text}"
        )

    return result


def run_with_input(command, input_text, display_command):
    print(f"+ {display_command}")

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        input=input_text,
        check=False,
        capture_output=True,
    )

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)

        fail(
            f"Command failed with exit code {result.returncode}: "
            f"{display_command}"
        )

    if result.stdout:
        print(result.stdout.rstrip())

    return result


def aws_json(arguments, region):
    result = run(
        [
            "aws",
            *arguments,
            "--region",
            region,
            "--output",
            "json",
            "--no-cli-pager",
        ]
    )

    output = result.stdout.strip()
    return json.loads(output) if output else {}


def parse_arguments():
    default_region = (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )

    parser = argparse.ArgumentParser(
        description=(
            "Preview and eventually deploy the NameGen DevOps project."
        )
    )
    parser.add_argument(
        "--region",
        default=default_region,
        help=f"AWS Region to use (default: {default_region}).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Create infrastructure and deploy NameGen. "
            "Temporarily disabled until deployment stages are complete."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive Apply confirmation.",
    )
    return parser.parse_args()


def verify_tools():
    heading("Prerequisite validation")

    missing = []

    for tool in REQUIRED_TOOLS:
        path = shutil.which(tool)
        if path:
            print(f"PASS: {tool} -> {path}")
        else:
            print(f"FAIL: {tool} was not found")
            missing.append(tool)

    if missing:
        fail(f"Missing required tools: {', '.join(missing)}")


def verify_project_files():
    heading("Project file validation")

    missing = []

    for relative_path in REQUIRED_FILES:
        path = PROJECT_ROOT / relative_path
        if path.is_file():
            print(f"PASS: {relative_path}")
        else:
            print(f"FAIL: {relative_path}")
            missing.append(relative_path)

    if missing:
        fail(f"Missing required project files: {', '.join(missing)}")


def render_kubernetes_manifests(image_reference=None):
    result = run(
        ["kubectl", "kustomize", str(KUBERNETES_DIR)],
        cwd=PROJECT_ROOT,
    )
    rendered = result.stdout

    placeholder_count = rendered.count(IMAGE_PLACEHOLDER)
    if placeholder_count != 1:
        fail(
            "Expected exactly one NameGen image placeholder in the "
            f"Kubernetes render; found {placeholder_count}."
        )

    if image_reference is None:
        return rendered

    if re.search(r"\s", image_reference):
        fail("The runtime image reference contains whitespace.")

    if not re.search(r":[0-9a-f]{40}$", image_reference):
        fail("The runtime image must use a full 40-character Git SHA tag.")

    return rendered.replace(IMAGE_PLACEHOLDER, image_reference, 1)


def validate_kubernetes_manifests():
    heading("Kubernetes manifest validation")

    rendered = render_kubernetes_manifests()

    required_fragments = (
        "kind: Namespace",
        "kind: StorageClass",
        "kind: StatefulSet",
        "kind: Deployment",
        "kind: Service",
        "replicas: 2",
        "image: mongo:3.6",
        "storageClassName: namegen-gp3",
        "loadBalancerClass: eks.amazonaws.com/nlb",
        "service.beta.kubernetes.io/aws-load-balancer-scheme: "
        "internet-facing",
    )

    missing = [
        fragment for fragment in required_fragments
        if fragment not in rendered
    ]
    if missing:
        fail(
            "Kubernetes render is missing required content: "
            + ", ".join(missing)
        )

    if "kind: Secret" in rendered:
        fail("A Kubernetes Secret must not be stored in the repository.")

    if re.search(r"image:\s*\S+:latest(?:\s|$)", rendered):
        fail("A mutable latest image tag was found in Kubernetes manifests.")

    if re.search(r"\b\d{12}\b", rendered):
        fail("A hardcoded 12-digit account identifier was found in Kubernetes.")

    if rendered.count(f"name: {MONGODB_SECRET_NAME}") != 5:
        fail(
            "Expected five MongoDB Secret references across the workloads."
        )

    print("PASS: Kubernetes manifests render successfully.")
    print("PASS: MongoDB Secret values are not stored in Git.")
    print("PASS: The NameGen image placeholder occurs exactly once.")


def build_mongodb_secret_manifest():
    root_username = "root"
    app_username = "genuser"
    root_password = secrets.token_urlsafe(32)
    app_password = secrets.token_urlsafe(32)

    mongodb_url = (
        "mongodb://"
        f"{quote(app_username, safe='')}:"
        f"{quote(app_password, safe='')}"
        "@mongodb:27017/namegen"
    )

    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": MONGODB_SECRET_NAME,
            "namespace": KUBERNETES_NAMESPACE,
        },
        "type": "Opaque",
        "stringData": {
            "MONGO_INITDB_ROOT_USERNAME": root_username,
            "MONGO_INITDB_ROOT_PASSWORD": root_password,
            "MONGO_APP_USERNAME": app_username,
            "MONGO_APP_PASSWORD": app_password,
            "MONGODB_URL": mongodb_url,
        },
    }


def apply_runtime_manifests(image_reference):
    run(
        [
            "kubectl",
            "apply",
            "--filename",
            str(KUBERNETES_DIR / "namespace.yaml"),
        ],
        live=True,
    )

    secret_manifest = build_mongodb_secret_manifest()
    run_with_input(
        ["kubectl", "apply", "--filename", "-"],
        json.dumps(secret_manifest),
        "kubectl apply --filename - # MongoDB Secret redacted",
    )

    rendered = render_kubernetes_manifests(image_reference)
    run_with_input(
        ["kubectl", "apply", "--filename", "-"],
        rendered,
        "kubectl apply --filename - # rendered Kubernetes manifests",
    )


def validate_monitoring_configuration():
    heading("Monitoring configuration validation")

    chart = run(
        [
            "helm",
            "template",
            MONITORING_RELEASE,
            MONITORING_CHART,
            "--version",
            MONITORING_CHART_VERSION,
            "--namespace",
            MONITORING_NAMESPACE,
            "--values",
            str(MONITORING_DIR / "values.yaml"),
        ],
        cwd=PROJECT_ROOT,
    ).stdout

    required_chart_fragments = (
        "kind: Prometheus",
        "name: namegen-monitoring-grafana",
        "name: namegen-monitoring-kube-state-metrics",
        "name: namegen-monitoring-kube-pr-operator",
        "uid: prometheus",
    )

    missing_chart_fragments = [
        fragment
        for fragment in required_chart_fragments
        if fragment not in chart
    ]

    if missing_chart_fragments:
        fail(
            "Monitoring Helm render is missing required content: "
            + ", ".join(missing_chart_fragments)
        )

    dashboard = run(
        ["kubectl", "kustomize", str(MONITORING_DIR)],
        cwd=PROJECT_ROOT,
    ).stdout

    required_dashboard_fragments = (
        "kind: ConfigMap",
        "name: namegen-grafana-dashboard",
        "NameGen Kubernetes Runtime",
        "Ready Pods",
        "Pod Restarts",
        "CPU Usage by Pod",
        "Memory Usage by Pod",
        "kube_pod_status_ready",
        "kube_pod_container_status_restarts_total",
        "container_cpu_usage_seconds_total",
        "container_memory_working_set_bytes",
    )

    missing_dashboard_fragments = [
        fragment
        for fragment in required_dashboard_fragments
        if fragment not in dashboard
    ]

    if missing_dashboard_fragments:
        fail(
            "Grafana dashboard render is missing required content: "
            + ", ".join(missing_dashboard_fragments)
        )

    forbidden_fragments = (
        "type: LoadBalancer",
        "kind: Ingress",
        "kind: PersistentVolumeClaim",
    )

    for label, rendered in (
        ("Helm chart", chart),
        ("dashboard", dashboard),
    ):
        found = [
            fragment
            for fragment in forbidden_fragments
            if fragment in rendered
        ]
        if found:
            fail(
                f"Monitoring {label} contains forbidden public exposure "
                f"or persistent storage: {', '.join(found)}"
            )

    if "kind: Secret" in dashboard:
        fail("A monitoring Secret must not be stored in the repository.")

    print(
        f"PASS: kube-prometheus-stack {MONITORING_CHART_VERSION} "
        "renders successfully."
    )
    print("PASS: The custom Grafana dashboard renders successfully.")
    print("PASS: Monitoring remains internal and uses ephemeral storage.")
    print("PASS: Grafana credentials are not stored in Git.")


def build_grafana_secret_manifest():
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": GRAFANA_SECRET_NAME,
            "namespace": MONITORING_NAMESPACE,
        },
        "type": "Opaque",
        "stringData": {
            "admin-user": "admin",
            "admin-password": secrets.token_urlsafe(32),
        },
    }


def apply_monitoring_stack():
    heading("Monitoring deployment")

    namespace_manifest = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": MONITORING_NAMESPACE,
            "labels": {
                "app.kubernetes.io/part-of": "namegen",
            },
        },
    }

    run_with_input(
        ["kubectl", "apply", "--filename", "-"],
        json.dumps(namespace_manifest),
        "kubectl apply --filename - # monitoring Namespace",
    )

    grafana_secret = build_grafana_secret_manifest()
    run_with_input(
        ["kubectl", "apply", "--filename", "-"],
        json.dumps(grafana_secret),
        "kubectl apply --filename - # Grafana Secret redacted",
    )

    run(
        [
            "helm",
            "repo",
            "add",
            "prometheus-community",
            PROMETHEUS_HELM_REPOSITORY_URL,
            "--force-update",
        ],
        live=True,
    )

    run(
        ["helm", "repo", "update"],
        live=True,
    )

    run(
        [
            "helm",
            "upgrade",
            "--install",
            MONITORING_RELEASE,
            MONITORING_CHART,
            "--version",
            MONITORING_CHART_VERSION,
            "--namespace",
            MONITORING_NAMESPACE,
            "--values",
            str(MONITORING_DIR / "values.yaml"),
            "--atomic",
            "--wait",
            "--wait-for-jobs",
            "--timeout",
            "15m",
        ],
        live=True,
    )

    dashboard = run(
        ["kubectl", "kustomize", str(MONITORING_DIR)],
        cwd=PROJECT_ROOT,
    ).stdout

    run_with_input(
        ["kubectl", "apply", "--filename", "-"],
        dashboard,
        "kubectl apply --filename - # Grafana dashboard",
    )

    print("PASS: Prometheus and Grafana were deployed.")
    print("PASS: The NameGen dashboard ConfigMap was applied.")
    print(
        "Grafana access: kubectl --namespace monitoring "
        "port-forward service/namegen-monitoring-grafana 3000:80"
    )


def verify_git_status():
    heading("Git working tree")

    result = run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
    )

    if result.stdout.strip():
        print("WARNING: The working tree contains uncommitted changes.")
        print(result.stdout.rstrip())
    else:
        print("PASS: Working tree is clean.")

    branch = run(
        ["git", "branch", "--show-current"],
        cwd=PROJECT_ROOT,
    ).stdout.strip()

    print(f"Branch: {branch or 'detached HEAD'}")


def get_aws_identity(region):
    heading("AWS identity")

    identity = aws_json(
        ["sts", "get-caller-identity"],
        region,
    )

    account_id = identity.get("Account")
    arn = identity.get("Arn")

    if not account_id or not arn:
        fail("AWS STS did not return a complete caller identity.")

    print(f"Account: {account_id}")
    print(f"Caller: {arn}")
    print(f"Region: {region}")

    return account_id


def state_bucket_name(account_id, region):
    return f"namegen-terraform-state-{account_id}-{region}"


def validate_state_bootstrap_configuration():
    heading("Terraform state bootstrap validation")

    run(
        [
            "terraform",
            f"-chdir={BOOTSTRAP_DIR}",
            "init",
            "-backend=false",
            "-input=false",
        ],
        live=True,
    )

    run(
        [
            "terraform",
            f"-chdir={BOOTSTRAP_DIR}",
            "fmt",
            "-check",
            "-recursive",
        ],
        live=True,
    )

    run(
        [
            "terraform",
            f"-chdir={BOOTSTRAP_DIR}",
            "validate",
        ],
        live=True,
    )

    print("PASS: Terraform state bootstrap configuration is valid.")


def state_bucket_exists(bucket, region):
    result = run(
        [
            "aws",
            "s3api",
            "head-bucket",
            "--bucket",
            bucket,
            "--region",
            region,
            "--no-cli-pager",
        ],
        allowed_codes=(0, 254, 255),
    )
    return result.returncode == 0


def bootstrap_state_bucket(bucket, region):
    heading("Terraform state bucket bootstrap")

    with tempfile.NamedTemporaryFile(
        prefix="namegen-bootstrap-",
        suffix=".tfplan",
        delete=False,
    ) as plan_file:
        plan_path = Path(plan_file.name)

    plan_path.unlink()

    try:
        run(
            [
                "terraform",
                f"-chdir={BOOTSTRAP_DIR}",
                "plan",
                "-input=false",
                "-lock=false",
                f"-var=aws_region={region}",
                f"-out={plan_path}",
            ],
            live=True,
        )

        run(
            [
                "terraform",
                f"-chdir={BOOTSTRAP_DIR}",
                "apply",
                "-input=false",
                str(plan_path),
            ],
            live=True,
        )

        created_bucket = run(
            [
                "terraform",
                f"-chdir={BOOTSTRAP_DIR}",
                "output",
                "-raw",
                "state_bucket_name",
            ]
        ).stdout.strip()
    finally:
        plan_path.unlink(missing_ok=True)

    if created_bucket != bucket:
        fail(
            "Terraform bootstrap returned an unexpected state bucket: "
            f"{created_bucket or '<empty>'}"
        )

    print(f"PASS: Terraform state bucket created: {created_bucket}")


def verify_state_bucket(bucket, region):
    heading("Terraform state bucket")

    print(f"Bucket: {bucket}")
    print(f"State key: {STATE_KEY}")

    if not state_bucket_exists(bucket, region):
        print("Status: absent or inaccessible")
        print(
            "PREVIEW: Apply mode would create the bucket with versioning, "
            "AES256 encryption and blocked public access."
        )
        return False

    print("PASS: Bucket exists and is accessible.")

    versioning = aws_json(
        [
            "s3api",
            "get-bucket-versioning",
            "--bucket",
            bucket,
        ],
        region,
    )

    if versioning.get("Status") != "Enabled":
        fail("Terraform state bucket versioning is not enabled.")

    print("PASS: Versioning is enabled.")

    encryption = aws_json(
        [
            "s3api",
            "get-bucket-encryption",
            "--bucket",
            bucket,
        ],
        region,
    )

    algorithms = [
        rule.get("ApplyServerSideEncryptionByDefault", {}).get(
            "SSEAlgorithm"
        )
        for rule in encryption.get(
            "ServerSideEncryptionConfiguration", {}
        ).get("Rules", [])
    ]

    if "AES256" not in algorithms:
        fail("Terraform state bucket is not encrypted with AES256.")

    print("PASS: AES256 server-side encryption is enabled.")

    public_access = aws_json(
        [
            "s3api",
            "get-public-access-block",
            "--bucket",
            bucket,
        ],
        region,
    ).get("PublicAccessBlockConfiguration", {})

    required_public_blocks = (
        "BlockPublicAcls",
        "IgnorePublicAcls",
        "BlockPublicPolicy",
        "RestrictPublicBuckets",
    )

    if not all(public_access.get(setting) is True
               for setting in required_public_blocks):
        fail("Terraform state bucket public access is not fully blocked.")

    print("PASS: Public access is fully blocked.")

    tags = aws_json(
        [
            "s3api",
            "get-bucket-tagging",
            "--bucket",
            bucket,
        ],
        region,
    )

    tag_map = {
        item.get("Key"): item.get("Value")
        for item in tags.get("TagSet", [])
    }

    if tag_map.get("Project") != PROJECT_TAG:
        fail("Terraform state bucket is missing the NameGen project tag.")

    print("PASS: Project tag is present.")
    return True


def ensure_state_bucket(bucket, region, apply):
    bucket_ready = verify_state_bucket(bucket, region)

    if bucket_ready:
        return True

    if not apply:
        return False

    bootstrap_state_bucket(bucket, region)

    if not verify_state_bucket(bucket, region):
        fail("Terraform state bucket bootstrap did not complete.")

    return True


def verify_no_runtime_collisions(region):
    heading("AWS runtime collision check")

    clusters = aws_json(
        ["eks", "list-clusters"],
        region,
    ).get("clusters", [])

    repositories = aws_json(
        ["ecr", "describe-repositories"],
        region,
    ).get("repositories", [])

    vpcs = aws_json(
        [
            "ec2",
            "describe-vpcs",
            "--filters",
            f"Name=tag:Project,Values={PROJECT_TAG}",
        ],
        region,
    ).get("Vpcs", [])

    roles = aws_json(
        ["iam", "list-roles"],
        region,
    ).get("Roles", [])

    oidc_providers = aws_json(
        ["iam", "list-open-id-connect-providers"],
        region,
    ).get("OpenIDConnectProviderList", [])

    matching_clusters = [
        name for name in clusters if name == CLUSTER_NAME
    ]
    matching_repositories = [
        repository
        for repository in repositories
        if repository.get("repositoryName") == ECR_REPOSITORY
    ]
    matching_roles = [
        role
        for role in roles
        if role.get("RoleName", "").startswith("namegen-")
    ]
    github_oidc_providers = [
        provider
        for provider in oidc_providers
        if "token.actions.githubusercontent.com"
        in provider.get("Arn", "")
    ]

    if len(github_oidc_providers) > 1:
        fail(
            "Multiple GitHub Actions OIDC providers were detected. "
            "Inspect the account before continuing."
        )

    github_oidc_provider_arn = None

    if github_oidc_providers:
        github_oidc_provider_arn = github_oidc_providers[0].get("Arn")

        provider = aws_json(
            [
                "iam",
                "get-open-id-connect-provider",
                "--open-id-connect-provider-arn",
                github_oidc_provider_arn,
            ],
            region,
        )

        if provider.get("Url") != "token.actions.githubusercontent.com":
            fail("The existing GitHub OIDC provider has an unexpected URL.")

        if "sts.amazonaws.com" not in provider.get("ClientIDList", []):
            fail(
                "The existing GitHub OIDC provider does not allow "
                "the sts.amazonaws.com audience."
            )

        print(
            "GitHub OIDC providers: 1 "
            f"(reusable: {github_oidc_provider_arn})"
        )
    else:
        print("GitHub OIDC providers: 0 (Terraform will create one)")

    checks = {
        "EKS clusters": matching_clusters,
        "ECR repositories": matching_repositories,
        "NameGen VPCs": vpcs,
        "NameGen IAM roles": matching_roles,
    }

    collisions = False

    for label, resources in checks.items():
        count = len(resources)
        print(f"{label}: {count}")
        collisions = collisions or count > 0

    if collisions:
        fail(
            "Existing runtime resources were detected. "
            "Inspect them before attempting a new deployment."
        )

    print("PASS: No existing NameGen runtime resources were detected.")
    return github_oidc_provider_arn


def confirm_runtime_apply(skip_confirmation):
    heading("Apply confirmation")

    if skip_confirmation:
        print("Confirmation skipped because --yes was supplied.")
        return

    print(
        "Terraform will now create billable AWS resources, including "
        "EKS, EC2 compute, EBS and an internet-facing NLB."
    )
    confirmation = input("Type APPLY to continue: ").strip()

    if confirmation != "APPLY":
        fail("Apply confirmation was not provided.")

    print("PASS: Apply confirmation received.")


def apply_terraform_plan(plan_path):
    heading("Terraform apply")

    run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "apply",
            "-input=false",
            str(plan_path),
        ],
        live=True,
    )

    print("PASS: Saved Terraform plan applied successfully.")


def read_runtime_outputs(expected_account_id, expected_region):
    heading("Terraform runtime outputs")

    result = run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "output",
            "-json",
        ]
    )

    raw_outputs = json.loads(result.stdout)
    required_outputs = (
        "aws_account_id",
        "aws_region",
        "ecr_repository_name",
        "ecr_repository_url",
        "eks_cluster_name",
    )
    missing_outputs = [
        name for name in required_outputs if name not in raw_outputs
    ]

    if missing_outputs:
        fail(
            "Terraform did not return required outputs: "
            + ", ".join(missing_outputs)
        )

    outputs = {
        name: raw_outputs[name].get("value")
        for name in required_outputs
    }

    if outputs["aws_account_id"] != expected_account_id:
        fail("Terraform output AWS Account ID does not match STS identity.")

    if outputs["aws_region"] != expected_region:
        fail("Terraform output AWS Region does not match launch region.")

    if outputs["ecr_repository_name"] != ECR_REPOSITORY:
        fail("Terraform returned an unexpected ECR repository name.")

    if outputs["eks_cluster_name"] != CLUSTER_NAME:
        fail("Terraform returned an unexpected EKS cluster name.")

    expected_ecr_prefix = (
        f"{expected_account_id}.dkr.ecr.{expected_region}."
    )
    expected_ecr_suffix = f"/{ECR_REPOSITORY}"
    ecr_repository_url = outputs["ecr_repository_url"] or ""

    if not (
        ecr_repository_url.startswith(expected_ecr_prefix)
        and ecr_repository_url.endswith(expected_ecr_suffix)
    ):
        fail("Terraform returned an unexpected ECR repository URL.")

    print(f"EKS cluster: {outputs['eks_cluster_name']}")
    print(f"ECR repository: {outputs['ecr_repository_url']}")
    print("PASS: Terraform runtime outputs match the launch identity.")
    return outputs


def configure_eks_access(cluster_name, region):
    heading("EKS access configuration")

    run(
        [
            "aws",
            "eks",
            "wait",
            "cluster-active",
            "--name",
            cluster_name,
            "--region",
            region,
            "--no-cli-pager",
        ],
        live=True,
    )

    cluster = aws_json(
        [
            "eks",
            "describe-cluster",
            "--name",
            cluster_name,
        ],
        region,
    ).get("cluster", {})

    if cluster.get("status") != "ACTIVE":
        fail("EKS cluster did not reach ACTIVE status.")

    if not cluster.get("endpoint"):
        fail("EKS cluster does not expose a Kubernetes API endpoint.")

    run(
        [
            "aws",
            "eks",
            "update-kubeconfig",
            "--name",
            cluster_name,
            "--region",
            region,
            "--alias",
            cluster_name,
            "--no-cli-pager",
        ],
        live=True,
    )

    ready = run(["kubectl", "get", "--raw=/readyz"])

    if ready.stdout.strip() != "ok":
        fail("Kubernetes API readiness endpoint did not return ok.")

    print("PASS: EKS cluster is ACTIVE and Kubernetes API access works.")


def terraform_preview(
    bucket,
    region,
    expected_account_id,
    github_oidc_provider_arn,
    apply=False,
    skip_confirmation=False,
):
    heading("Terraform initialization")

    run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "init",
            "-reconfigure",
            "-input=false",
            f"-backend-config=bucket={bucket}",
            f"-backend-config=region={region}",
        ],
        live=True,
    )

    heading("Terraform validation")

    run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "fmt",
            "-check",
            "-recursive",
        ],
        live=True,
    )

    run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "validate",
        ],
        live=True,
    )

    heading("Terraform state check")

    state = run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "state",
            "list",
        ],
        allowed_codes=(0, 1),
    )

    state_output = state.stdout.strip()
    state_error = state.stderr.strip()
    combined_output = f"{state_output}\n{state_error}"

    if state.returncode == 1:
        if "No state file was found!" not in combined_output:
            if state_output:
                print(state_output)
            if state_error:
                print(state_error, file=sys.stderr)
            fail("Terraform state inspection failed.")

        print(
            "PASS: Terraform state has not been created yet; "
            "this is a clean deployment."
        )
    elif state_output:
        print(state_output)
        fail(
            "Terraform state is not empty. "
            "This foundation preview expects a clean deployment."
        )
    else:
        print("PASS: Terraform state contains no runtime resources.")

    heading("Terraform plan")
    runtime_outputs = None

    with tempfile.NamedTemporaryFile(
        prefix="namegen-runtime-",
        suffix=".tfplan",
        delete=False,
    ) as plan_file:
        plan_path = Path(plan_file.name)

    plan_path.unlink()

    try:
        plan_command = [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "plan",
            "-input=false",
            "-lock=true",
            "-detailed-exitcode",
            f"-var=aws_region={region}",
            f"-out={plan_path}",
            "-no-color",
        ]

        if github_oidc_provider_arn:
            plan_command.append(
                "-var=github_oidc_provider_arn="
                f"{github_oidc_provider_arn}"
            )

        plan = run(
            plan_command,
            allowed_codes=(0, 2),
        )

        if plan.stdout:
            print(plan.stdout.rstrip())

        if plan.stderr:
            print(plan.stderr.rstrip(), file=sys.stderr)

        summary = re.search(
            r"Plan:\s+\d+\s+to add,\s+\d+\s+to change,"
            r"\s+\d+\s+to destroy\.",
            plan.stdout,
        )

        if summary:
            print(f"\nTerraform summary: {summary.group(0)}")
        elif plan.returncode == 0:
            print("\nTerraform summary: No infrastructure changes.")
        else:
            fail(
                "Terraform plan changed resources but no summary was found."
            )

        plan_json = run(
            [
                "terraform",
                f"-chdir={TERRAFORM_DIR}",
                "show",
                "-json",
                str(plan_path),
            ]
        )

        resource_changes = json.loads(
            plan_json.stdout
        ).get("resource_changes", [])

        unsafe_changes = [
            change.get("address", "<unknown>")
            for change in resource_changes
            if any(
                action in {"update", "delete"}
                for action in change.get("change", {}).get("actions", [])
            )
        ]

        if unsafe_changes:
            fail(
                "Terraform plan contains update, replacement or destroy "
                "actions: "
                + ", ".join(unsafe_changes)
            )

        create_count = sum(
            change.get("change", {}).get("actions") == ["create"]
            for change in resource_changes
        )

        print(
            "PASS: Saved Terraform plan contains "
            f"{create_count} create-only resource changes."
        )

        if apply:
            confirm_runtime_apply(skip_confirmation)
            apply_terraform_plan(plan_path)
            runtime_outputs = read_runtime_outputs(
                expected_account_id,
                region,
            )
            configure_eks_access(
                runtime_outputs["eks_cluster_name"],
                region,
            )
    finally:
        plan_path.unlink(missing_ok=True)

    print("PASS: Saved Terraform plan was removed.")
    return runtime_outputs


def main():
    args = parse_arguments()

    print("NameGen launch foundation")
    print(
        "Mode: "
        + ("APPLY (currently disabled)" if args.apply else "PREVIEW")
    )

    if args.apply:
        fail(
            "Apply mode is intentionally disabled until the Kubernetes, "
            "monitoring and runtime-validation stages are implemented."
        )

    verify_tools()
    verify_project_files()
    validate_state_bootstrap_configuration()
    verify_git_status()
    validate_kubernetes_manifests()
    validate_monitoring_configuration()

    account_id = get_aws_identity(args.region)
    bucket = state_bucket_name(account_id, args.region)

    bucket_ready = ensure_state_bucket(
        bucket,
        args.region,
        args.apply,
    )

    github_oidc_provider_arn = verify_no_runtime_collisions(
        args.region
    )

    if not bucket_ready:
        print(
            "\nPreview stopped before backend initialization because the "
            "state bucket does not yet exist."
        )
        print("No AWS resources were created.")
        return

    runtime_outputs = terraform_preview(
        bucket,
        args.region,
        account_id,
        github_oidc_provider_arn,
        apply=args.apply,
        skip_confirmation=args.yes,
    )

    if args.apply and not runtime_outputs:
        fail("Terraform apply completed without runtime outputs.")

    heading("Preview complete")
    print("PASS: Prerequisites and project files are available.")
    print("PASS: Kubernetes manifests rendered and passed policy checks.")
    print("PASS: Monitoring configuration rendered and passed policy checks.")
    print("PASS: AWS identity and state bucket were validated.")
    print("PASS: No runtime resource collisions were found.")
    print("PASS: Terraform validation and plan completed.")
    print("No VPC, ECR, IAM or EKS runtime resources were created.")


if __name__ == "__main__":
    main()
