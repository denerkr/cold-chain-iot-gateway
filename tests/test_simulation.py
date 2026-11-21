import json
import tempfile
import unittest
from pathlib import Path

from simulation.run_simulation import run_simulation


class SimulationTests(unittest.TestCase):
    def test_simulation_emits_alarm_events_and_performance_artifacts(self):
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
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = run_simulation(Path(first_dir), seed=12)
            second = run_simulation(Path(second_dir), seed=12)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
