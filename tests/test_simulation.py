import json
import tempfile
import unittest
from pathlib import Path

from simulation.run_simulation import (
    _aggregate_metric,
    run_experiment,
    run_sensitivity_analysis,
    run_simulation,
)


class SimulationTests(unittest.TestCase):
    """Exercise reproducibility, validation, metrics, and report integration.

    Tests that generate reports use temporary output directories so artifacts
    are isolated and removed automatically after assertions complete.
    """

    def test_simulation_emits_alarm_events_and_performance_artifacts(self):
        """Check the baseline trial's events, metrics, CSV, and performance plots.

        Calls ``run_simulation`` with its default seed, reads the serialized
        event log, and asserts that temperature, door, and LWT events are
        present alongside valid delivery counts and all single-run artifacts.
        """
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
            self.assertEqual(metrics["temperature_alarm_detected_pct"], 100.0)
            self.assertEqual(metrics["door_alarm_detected_pct"], 100.0)
            self.assertGreater(metrics["temperature_excursion_degree_minutes"], 0)
            self.assertGreaterEqual(metrics["temperature_alarm_detection_delay_s"], 0)
            self.assertGreaterEqual(metrics["door_alarm_delay_after_threshold_s"], 0)
            self.assertGreaterEqual(metrics["excursion_window_delivery_pct"], 0)

    def test_simulation_is_reproducible_with_same_seed(self):
        """Prove that a seed fixes all reported metrics despite separate outputs.

        Runs the same trial in two independent temporary directories and
        compares the returned dictionaries, excluding file contents from the
        comparison so the assertion targets the simulation's public result.
        """
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = run_simulation(Path(first_dir), seed=12)
            second = run_simulation(Path(second_dir), seed=12)

        self.assertEqual(first, second)

    def test_seed_sweep_aggregates_independent_runs(self):
        """Check seed enumeration, metric aggregation, and sweep artifacts.

        Calls ``run_experiment`` for seeds 20-22, recomputes the delivery mean
        from its per-seed values, verifies the interval exists for multiple
        runs, and checks that both aggregate charts and JSON were written.
        """
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
            self.assertTrue((output_dir / "alarm_response_analysis.png").is_file())
            self.assertIn(
                "temperature_alarm_detection_delay_s", summary["metrics"]
            )

    def test_seed_sweep_rejects_non_positive_run_count(self):
        """Ensure an empty experiment is rejected before output generation.

        Calls ``run_experiment`` with zero runs and checks its public validation
        error rather than accepting an empty or misleading aggregate.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "at least 1"):
                run_experiment(Path(temporary_directory), runs=0)

    def test_single_seed_sweep_omits_confidence_interval(self):
        """Ensure one observation is not presented with inferential statistics.

        Runs a one-seed experiment and confirms the aggregate reports neither
        sample standard deviation nor a confidence interval.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            summary = run_experiment(Path(temporary_directory), runs=1)

        delivery_metrics = summary["metrics"]["delivery_ratio_pct"]
        self.assertIsNone(delivery_metrics["sample_standard_deviation"])
        self.assertIsNone(delivery_metrics["approximate_95_percent_confidence_interval"])

    def test_zero_drop_rate_delivers_all_generated_messages(self):
        """Verify the no-loss boundary case preserves every generated sample.

        Runs the trial with a zero drop probability and checks both overall and
        excursion-window delivery, including the reported configured rate.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            metrics = run_simulation(
                Path(temporary_directory),
                seed=12,
                network_drop_rate=0,
            )

        self.assertEqual(metrics["network_drop_rate_pct"], 0)
        self.assertEqual(metrics["received_messages"], metrics["generated_messages"])
        self.assertEqual(metrics["delivery_ratio_pct"], 100)
        self.assertEqual(metrics["excursion_window_delivery_pct"], 100)

    def test_simulation_rejects_invalid_drop_rates(self):
        """Reject out-of-range drop probabilities through both public runners.

        Tests the upper boundary on ``run_simulation`` and a negative rate on
        ``run_experiment`` to ensure validation is consistent at each entry
        point before invalid scenarios can produce reports.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "less than 1"):
                run_simulation(Path(temporary_directory), network_drop_rate=1)
            with self.assertRaisesRegex(ValueError, "less than 1"):
                run_experiment(Path(temporary_directory), network_drop_rate=-0.1)

    def test_non_negative_metric_confidence_interval_does_not_cross_zero(self):
        """Clamp a descriptive interval's lower endpoint to the metric domain.

        Supplies nonnegative observations whose normal-approximation interval
        would otherwise extend below zero, then checks the aggregate boundary.
        """
        summary = _aggregate_metric([0.08, 0.08, 10.08])

        self.assertEqual(
            summary["approximate_95_percent_confidence_interval"][0],
            0,
        )

    def test_sensitivity_analysis_writes_network_and_lwt_results(self):
        """Check sensitivity scenario metrics, formula estimates, and artifacts.

        Runs two packet-loss scenarios and two keep-alive settings over three
        seeds. It verifies the zero-loss baseline, the 1.5x LWT estimate, and
        all JSON/PNG outputs returned by ``run_sensitivity_analysis``.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            summary = run_sensitivity_analysis(
                output_dir,
                base_seed=12,
                runs=3,
                drop_rates=(0, 0.1),
                keepalive_values_s=(10, 30),
            )

            network = summary["network_loss"]
            self.assertEqual(len(network["scenarios"]), 2)
            self.assertEqual(
                network["scenarios"][0]["metrics"]["delivery_ratio_pct"]["mean"],
                100,
            )
            self.assertEqual(
                network["scenarios"][0]["metrics"][
                    "excursion_window_delivery_pct"
                ]["mean"],
                100,
            )
            self.assertEqual(
                summary["lwt_keepalive"]["scenarios"][0][
                    "estimated_lwt_detection_latency_s"
                ],
                15,
            )
            self.assertTrue((output_dir / "network_sensitivity_metrics.json").is_file())
            self.assertTrue((output_dir / "lwt_keepalive_sensitivity.json").is_file())
            self.assertTrue((output_dir / "network_loss_sensitivity.png").is_file())
            self.assertTrue((output_dir / "lwt_keepalive_sensitivity.png").is_file())


if __name__ == "__main__":
    unittest.main()
