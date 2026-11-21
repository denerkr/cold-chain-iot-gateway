import json
import tempfile
import unittest
from pathlib import Path

from simulation.run_simulation import run_experiment, run_simulation


class SimulationTests(unittest.TestCase):
    def test_simulation_emits_alarm_events_and_performance_artifacts(self):
        """Verify one trial writes reports and detects each required scenario."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            metrics = run_simulation(output_dir)

            event_types = {
                event["type"]
                for event in json.loads((output_dir / "events.json").read_text())
            }
            self.assertIn("temperature_excursion", event_types)
            self.assertIn("door_open_too_long", event_types)
            self.assertIn("lwt_offline", event_types)
            self.assertGreater(metrics["received_messages"], 0)
            self.assertLessEqual(metrics["received_messages"], metrics["generated_messages"])
            self.assertTrue((output_dir / "telemetry.csv").is_file())
            self.assertTrue((output_dir / "performance_overview.png").is_file())
            self.assertTrue((output_dir / "system_performance.png").is_file())

    def test_simulation_is_reproducible_with_same_seed(self):
        """Verify identical seeds produce identical aggregate trial metrics."""
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = run_simulation(Path(first_dir), seed=12)
            second = run_simulation(Path(second_dir), seed=12)

        self.assertEqual(first, second)

    def test_seed_sweep_aggregates_independent_runs(self):
        """Verify a multi-seed experiment writes aggregate metrics and its chart."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            summary = run_experiment(output_dir, base_seed=20, runs=3)

            self.assertEqual(summary["seed_values"], [20, 21, 22])
            self.assertEqual(summary["run_count"], 3)
            self.assertEqual(
                summary["metrics"]["delivery_ratio_pct"]["mean"],
                round(
                    sum(summary["metrics"]["delivery_ratio_pct"]["values"]) / 3, 4
                ),
            )
            self.assertIsNotNone(
                summary["metrics"]["delivery_ratio_pct"][
                    "approximate_95_percent_confidence_interval"
                ]
            )
            self.assertTrue((output_dir / "seed_sweep_metrics.json").is_file())
            self.assertTrue((output_dir / "seed_sweep_performance.png").is_file())

    def test_seed_sweep_rejects_non_positive_run_count(self):
        """Reject empty seed sweeps instead of returning misleading statistics."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "at least 1"):
                run_experiment(Path(temporary_directory), runs=0)

    def test_single_seed_sweep_omits_confidence_interval(self):
        """Avoid presenting a confidence interval when only one seed was measured."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            summary = run_experiment(Path(temporary_directory), runs=1)

        delivery_metrics = summary["metrics"]["delivery_ratio_pct"]
        self.assertIsNone(delivery_metrics["sample_standard_deviation"])
        self.assertIsNone(delivery_metrics["approximate_95_percent_confidence_interval"])


if __name__ == "__main__":
    unittest.main()
