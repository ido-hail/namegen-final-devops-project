import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import launch


class RuntimeSecretTests(unittest.TestCase):
    def setUp(self):
        self.expected_keys = {"username", "password"}

    @staticmethod
    def result(returncode, stdout="", stderr=""):
        return SimpleNamespace(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    @patch.object(launch, "run_with_input")
    @patch.object(launch, "run")
    def test_existing_secret_is_preserved(self, run, run_with_input):
        run.return_value = self.result(
            0,
            json.dumps(
                {"data": {key: "redacted" for key in self.expected_keys}}
            ),
        )
        manifest_builder = Mock()

        output = io.StringIO()
        with redirect_stdout(output):
            launch.ensure_runtime_secret(
                "namegen",
                "runtime-credentials",
                self.expected_keys,
                manifest_builder,
                "Runtime",
            )

        manifest_builder.assert_not_called()
        run_with_input.assert_not_called()
        self.assertIn("Existing Runtime Secret was preserved", output.getvalue())

    @patch.object(launch, "run_with_input")
    @patch.object(launch, "run")
    def test_missing_secret_is_created_without_printing_values(
        self,
        run,
        run_with_input,
    ):
        run.return_value = self.result(
            1,
            stderr='Error from server (NotFound): secrets "x" not found',
        )
        manifest = {
            "kind": "Secret",
            "stringData": {
                "username": "runtime-user",
                "password": "do-not-print",
            },
        }

        output = io.StringIO()
        with redirect_stdout(output):
            launch.ensure_runtime_secret(
                "namegen",
                "runtime-credentials",
                self.expected_keys,
                lambda: manifest,
                "Runtime",
            )

        run_with_input.assert_called_once_with(
            ["kubectl", "create", "--filename", "-"],
            json.dumps(manifest),
            "kubectl create --filename - # Runtime Secret redacted",
        )
        self.assertNotIn("runtime-user", output.getvalue())
        self.assertNotIn("do-not-print", output.getvalue())

    @patch.object(launch, "run_with_input")
    @patch.object(launch, "run")
    def test_existing_secret_with_unexpected_keys_is_rejected(
        self,
        run,
        run_with_input,
    ):
        run.return_value = self.result(
            0,
            json.dumps({"data": {"username": "redacted"}}),
        )

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                launch.ensure_runtime_secret(
                    "namegen",
                    "runtime-credentials",
                    self.expected_keys,
                    Mock(),
                    "Runtime",
                )

        run_with_input.assert_not_called()

    @patch.object(launch, "run_with_input")
    @patch.object(launch, "run")
    def test_lookup_failure_is_not_treated_as_missing(
        self,
        run,
        run_with_input,
    ):
        run.return_value = self.result(1, stderr="Unauthorized")

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                launch.ensure_runtime_secret(
                    "namegen",
                    "runtime-credentials",
                    self.expected_keys,
                    Mock(),
                    "Runtime",
                )

        run_with_input.assert_not_called()


if __name__ == "__main__":
    unittest.main()
