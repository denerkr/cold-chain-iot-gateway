# Generated Reports

This directory contains a checked-in example report from the default synthetic seed. Recreate it from the repository root with:

```powershell
python -m simulation.run_simulation --seed 410103 --runs 100 --output-dir reports
```

`telemetry.csv`, `events.json`, `simulation_metrics.json`, `performance_overview.png`, and `system_performance.png` describe the first seed in an experiment. `seed_sweep_metrics.json` and `seed_sweep_performance.png` summarize all requested seeds. The command above reproduces the checked-in 100-seed example.

These are synthetic estimates, not physical measurements. The two PNG charts show sensor behavior and performance statistics; JSON and CSV files provide data for re-analysis. Running the command replaces report files with the same names.

## Change history

- Initial prototype: added one-seed telemetry, event, metric, and chart artifacts.
- Multi-seed analysis: added seed-sweep aggregates and histograms for delivery and latency.
- English documentation pass: standardized generated chart labels and documented the checked-in 100-seed example.
