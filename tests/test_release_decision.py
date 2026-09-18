import importlib.util
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "release_decision.py"
SPEC = importlib.util.spec_from_file_location("release_decision", SCRIPT)
release_decision = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(release_decision)


class ReleaseDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Release test"], cwd=self.repo, check=True)
        self.output = self.repo / "model/framework/examples/run_output.csv"
        self.columns = self.repo / "model/framework/columns/run_columns.csv"
        self.output.parent.mkdir(parents=True)
        self.columns.parent.mkdir(parents=True)
        self.output.write_text("input,value\nCC,1\n", encoding="utf-8")
        self.columns.write_text("name,type\nvalue,float\n", encoding="utf-8")
        self._commit("initial model")
        subprocess.run(["git", "tag", "v1.0.0"], cwd=self.repo, check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _commit(self, message):
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=self.repo, check=True)

    def _target(self):
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_unchanged_model_does_not_release(self):
        decision = release_decision.decide_release(self.repo, "v1.0.0", self._target())
        self.assertFalse(decision["release"])
        self.assertEqual(decision["tag"], "v1.0.0")

    def test_output_change_creates_next_major_release(self):
        self.output.write_text("input,value\nCC,2\n", encoding="utf-8")
        self._commit("change prediction output")

        decision = release_decision.decide_release(self.repo, "v1.0.0", self._target())
        self.assertTrue(decision["release"])
        self.assertEqual(decision["tag"], "v2.0.0")
        self.assertIn("run_output.csv", decision["changed_paths"])

    def test_schema_change_creates_next_major_release(self):
        self.columns.write_text("name,type\nvalue,float\nextra,float\n", encoding="utf-8")
        self._commit("change output schema")

        decision = release_decision.decide_release(self.repo, "v1.0.0", self._target())
        self.assertTrue(decision["release"])
        self.assertEqual(decision["tag"], "v2.0.0")
        self.assertIn("run_columns.csv", decision["changed_paths"])

    def test_missing_base_tag_creates_initial_release(self):
        decision = release_decision.decide_release(self.repo, None, self._target())
        self.assertTrue(decision["release"])
        self.assertEqual(decision["tag"], "v1.0.0")


if __name__ == "__main__":
    unittest.main()
