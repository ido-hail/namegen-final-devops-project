import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "deploy.yml"
RBAC_MANIFEST = PROJECT_ROOT / "k8s" / "namegen-ci-rbac.yaml"
OIDC_MODULE = PROJECT_ROOT / "terraform" / "modules" / "github_oidc" / "main.tf"


class DeploymentWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.rbac = RBAC_MANIFEST.read_text(encoding="utf-8")
        cls.oidc_module = OIDC_MODULE.read_text(encoding="utf-8")

    def test_uses_oidc_without_static_aws_credentials(self):
        self.assertIn("id-token: write", self.workflow)
        self.assertIn("role-to-assume: ${{ env.AWS_ROLE_ARN }}", self.workflow)
        self.assertNotIn("${{ secrets.", self.workflow)
        self.assertNotIn("aws-access-key-id", self.workflow)
        self.assertNotIn("aws-secret-access-key", self.workflow)

    def test_actions_are_pinned_to_commit_shas(self):
        action_references = re.findall(r"^\s*uses:\s*(\S+)", self.workflow, re.M)
        self.assertGreaterEqual(len(action_references), 5)

        for reference in action_references:
            self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")

    def test_deployment_is_immutable_and_branch_restricted(self):
        self.assertIn("refs/heads/main", self.workflow)
        self.assertIn("^[0-9a-f]{40}$", self.workflow)
        self.assertIn("imageTag=${GITHUB_SHA}", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^\s*image:\s*\S+:latest\s*$")
        self.assertNotIn("auto-approve", self.workflow)

    def test_workflow_preserves_runtime_secrets_and_storage(self):
        self.assertNotIn("get secret mongodb-credentials", self.workflow)
        self.assertNotRegex(self.workflow, r"kubectl\s+.*\bdelete\b")
        self.assertNotIn("kubectl apply --filename k8s/kustomization", self.workflow)
        self.assertNotIn("mongodb-statefulset.yaml", self.workflow)
        self.assertNotIn("storage-class.yaml", self.workflow)

    def test_eks_access_is_bound_to_a_least_privilege_group(self):
        self.assertIn(
            'kubernetes_groups = ["namegen-github-deployer"]',
            self.oidc_module,
        )
        self.assertNotIn("aws_eks_access_policy_association", self.oidc_module)
        self.assertNotIn("AmazonEKSClusterAdminPolicy", self.oidc_module)

    def test_rbac_allows_only_required_named_runtime_resources(self):
        for fragment in (
            "kind: Role",
            "kind: RoleBinding",
            "name: namegen-github-deployer",
            "resourceNames:\n      - namegen",
            "resourceNames:\n      - mongodb",
        ):
            self.assertIn(fragment, self.rbac)

        for forbidden in (
            "secrets",
            "persistentvolumeclaims",
            "storageclasses",
            "clusterroles",
            "delete",
            'verbs:\n      - "*"',
        ):
            self.assertNotIn(forbidden, self.rbac.lower())

    def test_runtime_validation_is_required(self):
        for required_fragment in (
            "rollout status deployment/namegen",
            "ready_replicas",
            "mongodb_ready",
            "/api/connection",
            "/api/random_name",
            "GITHUB_STEP_SUMMARY",
        ):
            self.assertIn(required_fragment, self.workflow)


if __name__ == "__main__":
    unittest.main()
