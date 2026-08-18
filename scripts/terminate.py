#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TERRAFORM_DIR = PROJECT_ROOT / "terraform"

PROJECT_TAG = "NameGen"
CLUSTER_NAME = "namegen-eks"
ECR_REPOSITORY = "namegen"
IAM_ROLE_PREFIX = "namegen-"
DEPLOYMENT_BRANCH = "main"
STATE_KEY = "namegen/terraform.tfstate"

REQUIRED_TOOLS = (
    "aws",
    "terraform",
    "git",
    "kubectl",
    "helm",
)

REQUIRED_FILES = (
    "terraform/backend.tf",
    "terraform/main.tf",
    "terraform/outputs.tf",
    "terraform/providers.tf",
    "terraform/variables.tf",
    "terraform/versions.tf",
    "scripts/launch.py",
    "k8s/kustomization.yaml",
    "monitoring/values.yaml",
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
            "Preview and eventually remove the NameGen AWS deployment."
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
            "Remove the NameGen deployment. Temporarily disabled until "
            "all cleanup and post-destroy checks are implemented."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive destroy confirmation.",
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


def verify_git_status(apply):
    heading("Git working tree")

    status = run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
    ).stdout.strip()

    if status and apply:
        print(status)
        fail("Destroy mode requires a clean Git working tree.")

    if status:
        print("WARNING: The working tree contains uncommitted changes.")
        print(status)
    else:
        print("PASS: Working tree is clean.")

    branch = run(
        ["git", "branch", "--show-current"],
        cwd=PROJECT_ROOT,
    ).stdout.strip()
    print(f"Branch: {branch or 'detached HEAD'}")

    if apply and branch != DEPLOYMENT_BRANCH:
        fail(
            f"Destroy mode requires the {DEPLOYMENT_BRANCH} branch; "
            f"current branch is {branch or 'detached HEAD'}."
        )

    git_sha = run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
    ).stdout.strip()

    if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        fail("Git HEAD is not a full 40-character commit SHA.")

    if apply:
        remote_sha = run(
            ["git", "rev-parse", f"origin/{DEPLOYMENT_BRANCH}"],
            cwd=PROJECT_ROOT,
        ).stdout.strip()

        if remote_sha != git_sha:
            fail(
                "Local HEAD does not match the tracked deployment branch "
                f"origin/{DEPLOYMENT_BRANCH}."
            )

    print(f"Git SHA: {git_sha}")
    return git_sha


def get_aws_identity(region):
    heading("AWS identity")
    identity = aws_json(["sts", "get-caller-identity"], region)
    account_id = identity.get("Account")
    arn = identity.get("Arn")

    if not re.fullmatch(r"[0-9]{12}", account_id or "") or not arn:
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
        return False

    print("PASS: State bucket exists and is accessible.")
    print("PASS: State bucket is intentionally excluded from teardown.")
    return True


def initialize_terraform(bucket, region):
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

    run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "validate",
        ],
        live=True,
    )


def read_terraform_state_addresses():
    heading("Terraform state inventory")

    result = run(
        [
            "terraform",
            f"-chdir={TERRAFORM_DIR}",
            "state",
            "list",
        ],
        allowed_codes=(0, 1),
    )

    if result.returncode == 1:
        message = f"{result.stdout}\n{result.stderr}".lower()
        if (
            "no state file was found" not in message
            and "state snapshot was not found" not in message
        ):
            fail("Terraform state could not be read.")
        addresses = []
    else:
        addresses = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]

    print(f"Managed state addresses: {len(addresses)}")
    for address in addresses:
        print(f"  - {address}")

    if not addresses:
        print("PASS: No Terraform-managed runtime resources exist.")

    return addresses


def read_aws_runtime_inventory(region):
    heading("AWS runtime inventory")

    clusters = aws_json(["eks", "list-clusters"], region).get(
        "clusters", []
    )
    repositories = aws_json(
        ["ecr", "describe-repositories"], region
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
    roles = aws_json(["iam", "list-roles"], region).get("Roles", [])
    oidc_providers = aws_json(
        ["iam", "list-open-id-connect-providers"], region
    ).get("OpenIDConnectProviderList", [])

    inventory = {
        "eks_clusters": [
            name for name in clusters if name == CLUSTER_NAME
        ],
        "ecr_repositories": [
            repository.get("repositoryName")
            for repository in repositories
            if repository.get("repositoryName") == ECR_REPOSITORY
        ],
        "vpc_ids": [vpc.get("VpcId") for vpc in vpcs],
        "iam_roles": [
            role.get("RoleName")
            for role in roles
            if role.get("RoleName", "").startswith(IAM_ROLE_PREFIX)
        ],
        "github_oidc_providers": [
            provider.get("Arn")
            for provider in oidc_providers
            if provider.get("Arn", "").endswith(
                "/token.actions.githubusercontent.com"
            )
        ],
    }

    print(f"EKS clusters: {len(inventory['eks_clusters'])}")
    print(f"ECR repositories: {len(inventory['ecr_repositories'])}")
    print(f"NameGen VPCs: {len(inventory['vpc_ids'])}")
    print(f"NameGen IAM roles: {len(inventory['iam_roles'])}")
    print(
        "GitHub OIDC providers: "
        f"{len(inventory['github_oidc_providers'])}"
    )

    return inventory


def preview_destroy_plan(region, state_addresses):
    heading("Terraform destroy plan")

    with tempfile.NamedTemporaryFile(
        prefix="namegen-destroy-",
        suffix=".tfplan",
        delete=False,
    ) as plan_file:
        plan_path = Path(plan_file.name)

    plan_path.unlink()

    try:
        plan = run(
            [
                "terraform",
                f"-chdir={TERRAFORM_DIR}",
                "plan",
                "-destroy",
                "-input=false",
                "-lock=true",
                "-detailed-exitcode",
                f"-var=aws_region={region}",
                f"-out={plan_path}",
                "-no-color",
            ],
            allowed_codes=(0, 2),
        )

        if plan.stdout:
            print(plan.stdout.rstrip())

        plan_json = run(
            [
                "terraform",
                f"-chdir={TERRAFORM_DIR}",
                "show",
                "-json",
                str(plan_path),
            ]
        )
        resource_changes = json.loads(plan_json.stdout).get(
            "resource_changes", []
        )

        unsafe_changes = []
        delete_addresses = []

        for change in resource_changes:
            actions = change.get("change", {}).get("actions", [])
            address = change.get("address", "<unknown>")

            if "delete" in actions:
                delete_addresses.append(address)

            if any(action in {"create", "update"} for action in actions):
                unsafe_changes.append(address)

        if unsafe_changes:
            fail(
                "Destroy plan contains create or update actions: "
                + ", ".join(unsafe_changes)
            )

        if state_addresses and not delete_addresses:
            fail(
                "Terraform state contains runtime resources but the "
                "destroy plan contains no deletions."
            )

        print(
            "PASS: Saved Terraform destroy plan contains "
            f"{len(delete_addresses)} delete-only resource changes."
        )
    finally:
        plan_path.unlink(missing_ok=True)

    print("PASS: Saved Terraform destroy preview plan was removed.")
    return delete_addresses


def main():
    args = parse_arguments()

    print("NameGen termination foundation")
    print(
        "Mode: "
        + ("DESTROY (currently disabled)" if args.apply else "PREVIEW")
    )

    if args.apply:
        fail(
            "Destroy mode is intentionally disabled until Kubernetes "
            "cleanup and post-destroy validation are implemented."
        )

    verify_tools()
    verify_project_files()
    verify_git_status(args.apply)

    account_id = get_aws_identity(args.region)
    bucket = state_bucket_name(account_id, args.region)

    if not verify_state_bucket(bucket, args.region):
        heading("Preview complete")
        print("No Terraform state bucket was found.")
        print("No AWS or Kubernetes resources were deleted.")
        return

    initialize_terraform(bucket, args.region)
    state_addresses = read_terraform_state_addresses()
    inventory = read_aws_runtime_inventory(args.region)
    delete_addresses = preview_destroy_plan(
        args.region,
        state_addresses,
    )

    runtime_count = sum(
        len(resources)
        for label, resources in inventory.items()
        if label != "github_oidc_providers"
    )

    heading("Preview complete")
    print(f"Terraform delete actions: {len(delete_addresses)}")
    print(f"Detected NameGen AWS runtime resources: {runtime_count}")
    print("No AWS or Kubernetes resources were deleted.")
    print(f"Terraform state bucket retained: {bucket}")


if __name__ == "__main__":
    main()
