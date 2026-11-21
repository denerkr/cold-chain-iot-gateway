# Generated Reports

Recreate the checked-in 100-seed example from the repository root with:

```powershell
python -m simulation.run_simulation --seed 410103 --runs 100 --sensitivity-analysis
```

The simulator is synthetic. Its latency, packet loss, alarms, and MQTT Last Will timing are model outputs, not measurements from a physical device, broker, or network. Running the command replaces report files with the same names.

## What the results answer

- **Seed sweep:** How much do delivery and latency metrics vary when only the pseudorandom seed changes?
- **Alarm response:** How quickly are the injected temperature excursion and overlong door-open condition detected? How much observed thermal exposure occurred?
- **Network-loss sensitivity:** How do overall delivery, delivery during the excursion, and alarm delays change as the modeled drop probability rises from 0% to 10%?
- **Keep-alive sensitivity:** What Last Will detection delay follows from the model assumption `1.5 x keep-alive`?

## Practical guide to `seed_sweep_performance.png`

The chart has three histograms. Each seed contributes one value to each histogram, so the vertical axis counts **trials**, not MQTT messages:

1. **Message delivery ratio:** Each trial generates 300 telemetry messages before the modeled disconnect. This panel counts how many trials had a given percentage received. The 100-seed example averages **98.9796%**; that is about 297 of 300 messages per trial.
2. **Mean network latency:** Each trial calculates the average latency of its received messages. The histogram shows the variation in those per-trial averages. The example's mean across seeds is **77.5784 ms**.
3. **P95 network latency:** Each trial first calculates the 95th percentile of its message latencies; the histogram then compares that per-trial P95 across seeds. The example averages **115.8451 ms**. P95 is a latency percentile, **not** a 95% confidence interval.

The dashed line is the mean across seeds. The shaded band is an approximate 95% confidence interval for that mean; it describes uncertainty in the estimated average, not the range containing 95% of individual messages or trials. Since these metrics are non-negative, a negative lower endpoint from the normal approximation is clipped to zero. The 100 seeds are repeated runs of the same synthetic assumptions, not 100 different networks. The JSON file retains per-seed values and interval bounds for closer inspection.

## Files

| File | Contents |
| --- | --- |
| `telemetry.csv` | Received samples from the first seed, including temperature, humidity, door state, and modeled message latency |
| `events.json` | First-seed temperature, door, and LWT state events |
| `simulation_metrics.json` | First-seed delivery, latency, thermal compliance, alarm response, and exposure metrics |
| `performance_overview.png` | First-seed temperature, compliance band, door-open samples, alarm times, and MQTT latency |
| `system_performance.png` | First-seed latency, received/lost messages, keep-alive, and estimated LWT timing |
| `seed_sweep_metrics.json` | Per-seed metrics, means, sample deviations, and approximate confidence intervals |
| `seed_sweep_performance.png` | Seed-to-seed histograms for delivery, mean latency, and P95 latency |
| `alarm_response_analysis.png` | Seed-to-seed temperature-alarm delays, door-alarm delay after its limit, and observed excursion exposure |
| `network_sensitivity_metrics.json` | Per-drop-rate metrics and per-seed values for the loss scenarios |
| `network_loss_sensitivity.png` | Delivery and alarm-response changes across packet-loss scenarios |
| `lwt_keepalive_sensitivity.json` | Keep-alive values and their estimated Last Will detection delays |
| `lwt_keepalive_sensitivity.png` | The theoretical keep-alive versus Last Will detection-time relationship |

`observed_temperature_compliance_pct` uses only delivered sensor samples. `temperature_excursion_degree_minutes` integrates observed temperature excess over contiguous 10-second samples and excludes intervals with missing packets; neither metric reconstructs unobserved physical conditions.

The temperature-alarm delay is measured from the injected excursion start. The door-alarm delay in the chart is measured **after** the configured 30-second door-open limit, separating the intentional threshold wait from additional sampling/network delay. LWT results are formula-based estimates and are not broker measurements.

## Example findings (100 seeds)

With base seed `410103`, the regular 1% packet-loss scenario detected both injected alarms in all 100 trials. Mean temperature-alarm delay was **0.0789 s** after the excursion began; mean additional door-alarm delay was **0.1819 s** after the 30-second threshold. Mean observed thermal exposure was **3.2279 degree-minutes**, and delivered samples showed **94.3406%** temperature compliance. Compliance does not account for packets that were lost.

| Configured packet-drop rate | Overall delivery | Delivery during excursion | Temperature alarm delay | Mean door delay after limit | P95 door delay across seeds |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0% | 100.0000% | 100.0000% | 0.0787 s | 0.0810 s | 0.12 s |
| 1% | 98.9796% | 98.8828% | 0.0789 s | 0.1819 s | 0.12 s |
| 5% | 94.8937% | 95.0603% | 0.9810 s | 1.2831 s | 10.09 s |
| 10% | 89.7367% | 88.9429% | 1.9798 s | 2.4803 s | 10.11 s |

The door-delay P95 is the nearest-rank 95th percentile of the 100 per-seed delays, not a confidence interval. It reveals a useful tail effect: at 5-10% drop rates, some trials miss the first eligible 10-second telemetry sample and wait for the next one. These are averages and percentiles from the synthetic model. At the configured 30-second keep-alive, the assumed LWT delay is 45 seconds; the other plotted keep-alives produce estimates of 15, 30, and 90 seconds for 10, 20, and 60 seconds respectively.

## Change history

- Initial prototype: added one-seed telemetry, event, metric, and chart artifacts.
- Multi-seed analysis: added per-seed delivery and latency distributions with descriptive intervals.
- Operational analysis: added thermal exposure and alarm-response metrics over multiple seeds.
- Sensitivity analysis: added packet-loss scenarios and a theoretical keep-alive/LWT comparison.
