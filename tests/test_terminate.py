import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import terminate


class StateBucketCleanupTests(unittest.TestCase):
    @staticmethod
    def result(returncode=0, stdout="", stderr=""):
        return SimpleNamespace(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    @patch.object(terminate, "run")
    @patch.object(terminate, "aws_json")
    @patch.object(terminate, "state_bucket_exists")
    def test_all_versions_are_deleted_before_the_bucket(
        self,
        state_bucket_exists,
        aws_json,
        run,
    ):
        state_bucket_exists.side_effect = [True, False]
        aws_json.side_effect = [
            {
                "Versions": [
                    {"Key": "namegen/terraform.tfstate", "VersionId": "v1"}
                ],
                "DeleteMarkers": [
                    {"Key": "namegen/terraform.tfstate", "VersionId": "d1"}
                ],
            },
            {},
            {},
        ]
        run.return_value = self.result()

        with redirect_stdout(io.StringIO()):
            deleted = terminate.delete_state_bucket(
                "namegen-state-test",
                "us-east-1",
            )

        self.assertEqual(deleted, 2)
        delete_payload = json.loads(aws_json.call_args_list[1].args[0][5])
        self.assertEqual(len(delete_payload["Objects"]), 2)
        self.assertEqual(
            run.call_args.args[0][:3],
            ["aws", "s3api", "delete-bucket"],
        )

    @patch.object(terminate, "run")
    @patch.object(terminate, "aws_json")
    @patch.object(terminate, "state_bucket_exists")
    def test_s3_delete_errors_stop_bucket_deletion(
        self,
        state_bucket_exists,
        aws_json,
        run,
    ):
        state_bucket_exists.return_value = True
        aws_json.side_effect = [
            {
                "Versions": [
                    {"Key": "namegen/terraform.tfstate", "VersionId": "v1"}
                ]
            },
            {"Errors": [{"Code": "AccessDenied"}]},
        ]

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                terminate.delete_state_bucket(
                    "namegen-state-test",
                    "us-east-1",
                )

        run.assert_not_called()

    @patch.object(terminate, "delete_state_bucket")
    @patch.object(terminate, "build_destroy_plan")
    def test_preview_never_deletes_the_state_bucket(
        self,
        build_destroy_plan,
        delete_state_bucket,
    ):
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "destroy.tfplan"
            plan_path.touch()
            build_destroy_plan.return_value = (plan_path, [])

            terminate.run_destroy_workflow(
                "us-east-1",
                "namegen-state-test",
                [],
                {
                    "eks_clusters": [],
                    "ecr_repositories": [],
                    "vpc_ids": [],
                    "iam_roles": [],
                    "github_oidc_providers": [],
                },
                apply=False,
                skip_confirmation=False,
            )

        delete_state_bucket.assert_not_called()

    @patch.object(terminate, "delete_state_bucket")
    @patch.object(terminate, "validate_post_destroy")
    @patch.object(terminate, "confirm_destroy")
    @patch.object(terminate, "build_destroy_plan")
    def test_interrupted_teardown_can_resume_bucket_cleanup(
        self,
        build_destroy_plan,
        confirm_destroy,
        validate_post_destroy,
        delete_state_bucket,
    ):
        inventory = {
            "eks_clusters": [],
            "ecr_repositories": [],
            "vpc_ids": [],
            "iam_roles": [],
            "github_oidc_providers": [],
        }

        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "destroy.tfplan"
            plan_path.touch()
            build_destroy_plan.return_value = (plan_path, [])

            terminate.run_destroy_workflow(
                "us-east-1",
                "namegen-state-test",
                [],
                inventory,
                apply=True,
                skip_confirmation=True,
            )

        confirm_destroy.assert_called_once_with(True)
        validate_post_destroy.assert_called_once()
        delete_state_bucket.assert_called_once_with(
            "namegen-state-test",
            "us-east-1",
        )


if __name__ == "__main__":
    unittest.main()
