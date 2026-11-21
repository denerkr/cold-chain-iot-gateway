# Offline Simulation

`run_simulation.py` produces deterministic synthetic trials and multi-seed summaries without a broker, Docker, Wokwi, or hardware. It uses `matplotlib` for chart generation; install dependencies from the repository root with `python -m pip install -r requirements.txt`.

## Commands

```powershell
python -m simulation.run_simulation
python -m simulation.run_simulation --seed 410103 --runs 100
python -m simulation.run_simulation --seed 20 --runs 5 --output-dir reports\trial-20
python -m simulation.run_simulation --seed 410103 --runs 100 --sensitivity-analysis
```

The trial seed is `base_seed + index`, starting from index zero. One trial generates detailed CSV, JSON, and PNG artifacts. Additional seeds contribute to summary metrics and charts. A positive `--runs` count is required.

Each trial models 300 potential samples at 10-second intervals up to an abrupt disconnect at 3,000 simulated seconds. It applies a seeded message-drop probability (1% by default), samples network latency, injects a thermal excursion and a prolonged door-open event, and estimates LWT detection at 1.5 times the 30-second keep-alive. Its 3,600-second observation window includes the final offline period.

Use `--drop-rate 0.05` to change the packet-drop probability for the regular seed sweep. It must be at least zero and less than one. `--sensitivity-analysis` additionally compares 0%, 1%, 5%, and 10% drop scenarios, using the same sequential seed set for each scenario, and calculates LWT estimates for 10-, 20-, 30-, and 60-second keep-alives. These scenario values are fixed in the script.

The simulator reports temperature compliance only across delivered samples. Excursion degree-minutes use trapezoidal integration between contiguous 10-second received samples; intervals that contain packet gaps are excluded rather than guessed. Temperature alarm delay is measured from the injected excursion start. Door alarm delay is reported both from door opening and from the 30-second alarm threshold. If an event is not observed, its response delay is `null`, and its detection-rate metric captures the missed event.

The 95% interval is a normal approximation around the multi-run mean using the sample standard deviation. It is not an exact interval for small samples; negative lower endpoints are clipped to zero because the reported metrics are non-negative. It is omitted for a single run. `percentile` uses the nearest-rank definition.

## Function responsibilities

- `percentile`: calculate a nearest-rank percentile from latency samples.
- `_event_timestamp`: find the first detection time for a requested event type.
- `_temperature_excursion_degree_minutes`: estimate observed thermal exposure using contiguous received samples.
- `_aggregate_metric`: summarize numeric replications and preserve missing detections as null values.
- `run_simulation`: generate one seeded trial, update state-transition alarms, collect operational and network metrics, and optionally write detailed outputs.
- `_write_performance_chart`: chart first-trial temperature, door markers, alarms, and message latency.
- `_write_system_performance_chart`: chart latency, delivery counts, and estimated keep-alive/LWT timing.
- `run_experiment`: execute sequential seeds, keep detailed first-trial files, aggregate network and alarm metrics, and write summary charts.
- `_write_seed_sweep_chart`: chart delivery and latency distributions across seeds; histogram bars count trials, not messages.
- `_write_alarm_response_chart`: chart alarm response delays and thermal exposure across seeds.
- `run_sensitivity_analysis`: compare packet-loss scenarios and theoretical LWT timing for several keep-alive settings.
- `_write_network_sensitivity_chart`: chart delivery and alarm-response changes across packet-loss scenarios.
- `_write_keepalive_sensitivity_chart`: chart the formula-based LWT delay estimate.
- `main`: validate CLI arguments, run the seed sweep, and print its JSON summary.

## Change history

- Initial prototype: implemented seeded synthetic data, stateful alarms, single-run JSON/CSV outputs, and two charts.
- Multi-seed analysis: added sequential seed runs, aggregate statistics, approximate confidence intervals, and distribution charts.
- Operational analysis: added sample-based thermal compliance, excursion degree-minutes, and alarm response delays.
- Sensitivity analysis: added configurable packet-loss scenarios and theoretical keep-alive/LWT comparisons.
- English documentation pass: translated CLI help, plotted labels, and metric descriptions.
