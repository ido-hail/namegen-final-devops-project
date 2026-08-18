#!/usr/bin/env python3

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = PROJECT_ROOT / "terraform"
KUBERNETES_DIR = PROJECT_ROOT / "k8s"

PROJECT_TAG = "NameGen"
CLUSTER_NAME = "namegen-eks"
ECR_REPOSITORY = "namegen"
STATE_KEY = "namegen/terraform.tfstate"
KUBERNETES_NAMESPACE = "namegen"
MONGODB_SECRET_NAME = "mongodb-credentials"
IMAGE_PLACEHOLDER = "namegen-image:git-sha"

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
        help="Skip the future interactive Apply confirmation.",
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

    checks = {
        "EKS clusters": matching_clusters,
        "ECR repositories": matching_repositories,
        "NameGen VPCs": vpcs,
        "NameGen IAM roles": matching_roles,
        "GitHub OIDC providers": github_oidc_providers,
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


def terraform_preview(bucket, region):
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

    plan = run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "plan",
            "-input=false",
            "-lock=true",
            "-detailed-exitcode",
            f"-var=aws_region={region}",
            "-no-color",
        ],
        allowed_codes=(0, 2),
    )

    if plan.stdout:
        print(plan.stdout.rstrip())

    if plan.stderr:
        print(plan.stderr.rstrip(), file=sys.stderr)

    summary = re.search(
        r"Plan:\s+\d+\s+to add,\s+\d+\s+to change,\s+\d+\s+to destroy\.",
        plan.stdout,
    )

    if summary:
        print(f"\nTerraform summary: {summary.group(0)}")
    elif plan.returncode == 0:
        print("\nTerraform summary: No infrastructure changes.")
    else:
        fail("Terraform plan changed resources but no summary was found.")


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
    verify_git_status()
    validate_kubernetes_manifests()

    account_id = get_aws_identity(args.region)
    bucket = state_bucket_name(account_id, args.region)

    bucket_ready = verify_state_bucket(bucket, args.region)

    verify_no_runtime_collisions(args.region)

    if not bucket_ready:
        print(
            "\nPreview stopped before backend initialization because the "
            "state bucket does not yet exist."
        )
        print("No AWS resources were created.")
        return

    terraform_preview(bucket, args.region)

    heading("Preview complete")
    print("PASS: Prerequisites and project files are available.")
    print("PASS: Kubernetes manifests rendered and passed policy checks.")
    print("PASS: AWS identity and state bucket were validated.")
    print("PASS: No runtime resource collisions were found.")
    print("PASS: Terraform validation and plan completed.")
    print("No VPC, ECR, IAM or EKS runtime resources were created.")


if __name__ == "__main__":
    main()
