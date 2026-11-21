# Offline Simulation

`run_simulation.py` produces a deterministic synthetic trial and a multi-seed experiment without a broker, Docker, Wokwi, or hardware. It uses `matplotlib` for chart generation; install dependencies from the repository root with `python -m pip install -r requirements.txt`.

## Commands

```powershell
python -m simulation.run_simulation
python -m simulation.run_simulation --seed 410103 --runs 100
python -m simulation.run_simulation --seed 20 --runs 5 --output-dir reports\trial-20
```

The trial seed is `base_seed + index`, starting from index zero. One trial generates all detailed data files. Additional trials use temporary directories, and their measurements contribute to the seed-sweep JSON/PNG summary. A positive `--runs` count is required.

Each trial models 300 potential samples at 10-second intervals up to an abrupt disconnect at 3,000 simulated seconds. It applies a seeded 1% message-drop probability, samples network latency, injects a thermal excursion and a prolonged door-open event, and estimates LWT detection at 1.5 times the 30-second keep-alive. Its 3,600-second observation window includes the final offline period.

The 95% interval is a normal approximation around the multi-run mean using the sample standard deviation. It is not an exact interval for small samples. It is omitted for a single run. `percentile` uses the nearest-rank definition.

## Function responsibilities

- `percentile`: calculate a nearest-rank percentile from latency samples.
- `run_simulation`: generate one seeded trial, update state-transition alarms, collect metrics, and write its detailed outputs.
- `_write_performance_chart`: chart first-trial temperature, door markers, alarms, and message latency.
- `_write_system_performance_chart`: chart latency, delivery counts, and estimated keep-alive/LWT timing.
- `run_experiment`: execute sequential independent seeds, keep detailed first-trial files, aggregate metrics, and write summary outputs.
- `_write_seed_sweep_chart`: chart delivery and latency distributions across the requested seeds.
- `main`: validate CLI arguments, run the experiment, and print its JSON summary.

## Change history

- Initial prototype: implemented seeded synthetic data, stateful alarms, single-run JSON/CSV outputs, and two charts.
- Multi-seed analysis: added sequential seed runs, aggregate statistics, approximate confidence intervals, and distribution charts.
- English documentation pass: translated CLI help, plotted labels, and metric descriptions.
