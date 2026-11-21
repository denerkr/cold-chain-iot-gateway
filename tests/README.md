# Simulation Tests

`test_simulation.py` uses Python's built-in `unittest` framework and temporary directories. The focused tests verify:

- A trial detects thermal excursion, prolonged door-open, and offline LWT events.
- A trial writes all detailed CSV, JSON, and PNG artifacts.
- Repeating the same seed produces the same metrics.
- Multiple sequential seeds create a valid aggregate and seed-sweep chart.
- A zero-run experiment fails explicitly instead of emitting misleading statistics.

Run the suite from the repository root with `python -m unittest discover -s tests -v`.

## Change history

- Initial prototype: checked single-seed event generation, reproducibility, and core artifacts.
- Multi-seed analysis: checked seed selection, aggregate calculations, chart output, and invalid run counts.
- English documentation pass: documented each test's behavior and kept assertions aligned with the English report schema.
