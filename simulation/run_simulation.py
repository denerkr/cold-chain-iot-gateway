#!/usr/bin/env python3
"""Generate deterministic synthetic telemetry, performance metrics, and charts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SAMPLE_PERIOD_S = 10
SIMULATION_DURATION_S = 3600
DEVICE_DISCONNECT_S = 3000
MQTT_KEEPALIVE_S = 30
NETWORK_DROP_RATE = 0.01
NETWORK_DROP_RATES = (0.0, 0.01, 0.05, 0.10)
MQTT_KEEPALIVE_SCENARIOS_S = (10, 20, 30, 60)
TEMPERATURE_MIN_C = 2.0
TEMPERATURE_MAX_C = 8.0
TEMPERATURE_EXCURSION_START_S = 120
TEMPERATURE_EXCURSION_END_S = 290
DOOR_OPEN_START_S = 200
DOOR_OPEN_END_S = 260
DOOR_ALARM_AFTER_S = 30


def percentile(values: list[float], quantile: float) -> float:
    """Return one order statistic using the nearest-rank percentile definition.

    The function sorts a copy of the input, then selects rank ``ceil(q * n)``
    using one-based percentile rank. An empty input returns ``0.0`` so chart
    labels remain drawable when no latency samples were received. Callers use
    this for per-trial latency P95 values; it does not calculate a confidence
    interval or mutate the caller's list.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _event_timestamp(events: list[dict[str, object]], event_type: str) -> float | None:
    """Find the first recorded timestamp for one event type.

    ``run_simulation`` supplies the event records assembled while processing
    telemetry, plus the synthetic LWT event. A matching numeric timestamp is
    converted to ``float``; an absent event or nonnumeric timestamp becomes
    ``None`` so the metric layer can report an undetected alarm explicitly.
    """
    for event in events:
        if event["type"] == event_type:
            timestamp = event["timestamp_s"]
            return float(timestamp) if isinstance(timestamp, (int, float)) else None
    return None


def _temperature_excursion_degree_minutes(
    records: list[dict[str, object]],
) -> float | None:
    """Integrate observed temperature excess during the injected excursion.

    Consecutive records are treated as the ends of a linear 10-second segment.
    Trapezoidal integration accumulates degrees outside the 2-8 C range in
    degree-minutes. Intervals spanning a lost sample or outside the modeled
    excursion are excluded rather than reconstructed. ``None`` means there
    were no contiguous observed intervals to integrate.
    """
    exposure = 0.0
    observed_intervals = 0
    for previous, current in zip(records, records[1:]):
        previous_time = float(previous["timestamp_s"])
        current_time = float(current["timestamp_s"])
        interval_s = current_time - previous_time
        if (
            interval_s != SAMPLE_PERIOD_S
            or current_time <= TEMPERATURE_EXCURSION_START_S
            or previous_time >= TEMPERATURE_EXCURSION_END_S
        ):
            continue

        previous_temperature = float(previous["temperature_c"])
        current_temperature = float(current["temperature_c"])
        previous_excess = max(0.0, previous_temperature - TEMPERATURE_MAX_C) + max(
            0.0, TEMPERATURE_MIN_C - previous_temperature
        )
        current_excess = max(0.0, current_temperature - TEMPERATURE_MAX_C) + max(
            0.0, TEMPERATURE_MIN_C - current_temperature
        )
        exposure += (previous_excess + current_excess) / 2 * interval_s / 60
        observed_intervals += 1

    return round(exposure, 4) if observed_intervals else None


def _aggregate_metric(values: list[object]) -> dict[str, object]:
    """Summarize one metric across trials and preserve unobserved values.

    Numeric values produce their mean, sample standard deviation, and
    descriptive normal-approximation 95% interval. Missing detections remain
    ``None`` in the per-run list and are excluded from the observed-run count
    and statistics. Unsupported input types raise ``TypeError`` instead of
    silently producing a partial summary. Used by both seed and sensitivity
    experiments.
    """
    numeric_values: list[float] = []
    formatted_values: list[float | None] = []
    for value in values:
        if value is None:
            formatted_values.append(None)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            numeric = float(value)
            numeric_values.append(numeric)
            formatted_values.append(round(numeric, 4))
        else:
            raise TypeError(f"Expected a numeric metric or None, got {type(value).__name__}")

    average = mean(numeric_values) if numeric_values else None
    standard_deviation = stdev(numeric_values) if len(numeric_values) > 1 else None
    interval = None
    if average is not None and standard_deviation is not None:
        margin = 1.96 * standard_deviation / math.sqrt(len(numeric_values))
        interval = [
            round(max(0.0, average - margin), 4),
            round(average + margin, 4),
        ]

    return {
        "mean": round(average, 4) if average is not None else None,
        "values": formatted_values,
        "observed_run_count": len(numeric_values),
        "sample_standard_deviation": (
            round(standard_deviation, 4)
            if standard_deviation is not None
            else None
        ),
        "approximate_95_percent_confidence_interval": interval,
    }


def run_simulation(
    output_dir: Path,
    seed: int = 410103,
    network_drop_rate: float = NETWORK_DROP_RATE,
    write_reports: bool = True,
) -> dict[str, object]:
    """Generate one deterministic synthetic trial and its optional artifacts.

    Args:
        output_dir: Destination for one-trial CSV, JSON, and PNG reports.
        seed: Seed for the local pseudorandom generator.
        network_drop_rate: Independent per-message drop probability in ``[0, 1)``.
        write_reports: When false, return metrics without creating report files;
            seed and sensitivity sweeps use this for their non-example trials.

    The loop skips dropped messages, synthesizes sensor and latency values for
    delivered samples, and updates temperature/door alarm state. The function
    then derives event-response and thermal metrics; when requested, it writes
    the detailed files and calls the two single-trial chart writers. It always
    returns the metrics dictionary consumed by ``run_experiment`` and
    ``run_sensitivity_analysis``.
    """
    if not 0 <= network_drop_rate < 1:
        raise ValueError("network_drop_rate must be at least 0 and less than 1")

    rng = random.Random(seed)
    records: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    network_latencies_ms: list[float] = []
    temperature_alarm_active = False
    door_open_since_s: int | None = None
    door_alarm_active = False
    generated_messages = DEVICE_DISCONNECT_S // SAMPLE_PERIOD_S
    received_messages = 0

    for sample_index in range(generated_messages):
        timestamp_s = sample_index * SAMPLE_PERIOD_S
        if rng.random() < network_drop_rate:
            continue

        temperature_c = 4.8 + rng.gauss(0, 0.35)
        if TEMPERATURE_EXCURSION_START_S <= timestamp_s < TEMPERATURE_EXCURSION_END_S:
            temperature_c = 9.2 + rng.gauss(0, 0.2)
        humidity_pct = min(75.0, max(30.0, 55 + rng.gauss(0, 2.0)))
        door_open = DOOR_OPEN_START_S <= timestamp_s < DOOR_OPEN_END_S
        latency_ms = rng.uniform(35, 120)
        received_messages += 1
        network_latencies_ms.append(latency_ms)

        temperature_out_of_range = not (
            TEMPERATURE_MIN_C <= temperature_c <= TEMPERATURE_MAX_C
        )
        if temperature_out_of_range and not temperature_alarm_active:
            events.append(
                {
                    "timestamp_s": timestamp_s + latency_ms / 1000,
                    "type": "temperature_excursion",
                    "latency_ms": round(latency_ms, 2),
                    "value": round(temperature_c, 2),
                }
            )
        elif not temperature_out_of_range and temperature_alarm_active:
            events.append(
                {
                    "timestamp_s": timestamp_s + latency_ms / 1000,
                    "type": "temperature_restored",
                    "latency_ms": round(latency_ms, 2),
                    "value": round(temperature_c, 2),
                }
            )
        temperature_alarm_active = temperature_out_of_range

        if door_open:
            if door_open_since_s is None:
                door_open_since_s = timestamp_s
            if (
                not door_alarm_active
                and timestamp_s - door_open_since_s >= DOOR_ALARM_AFTER_S
            ):
                events.append(
                    {
                        "timestamp_s": timestamp_s + latency_ms / 1000,
                        "type": "door_open_too_long",
                        "latency_ms": round(latency_ms, 2),
                        "duration_s": timestamp_s - door_open_since_s,
                    }
                )
                door_alarm_active = True
        else:
            door_open_since_s = None
            door_alarm_active = False

        records.append(
            {
                "timestamp_s": timestamp_s,
                "temperature_c": round(temperature_c, 2),
                "humidity_pct": round(humidity_pct, 2),
                "door_open": door_open,
                "mqtt_latency_ms": round(latency_ms, 2),
            }
        )

    lwt_detection_latency_s = MQTT_KEEPALIVE_S * 1.5
    events.append(
        {
            "timestamp_s": DEVICE_DISCONNECT_S + lwt_detection_latency_s,
            "type": "lwt_offline",
            "latency_ms": None,
            "details": "Broker detects an abrupt disconnect after 1.5x keep-alive",
        }
    )

    latencies = network_latencies_ms
    temperature_alarm_time = _event_timestamp(events, "temperature_excursion")
    door_alarm_time = _event_timestamp(events, "door_open_too_long")
    excursion_sample_count = len(
        range(
            TEMPERATURE_EXCURSION_START_S,
            TEMPERATURE_EXCURSION_END_S,
            SAMPLE_PERIOD_S,
        )
    )
    received_excursion_samples = sum(
        TEMPERATURE_EXCURSION_START_S
        <= int(record["timestamp_s"])
        < TEMPERATURE_EXCURSION_END_S
        for record in records
    )
    metrics: dict[str, object] = {
        "simulation": "synthetic; not measured on physical hardware",
        "seed": seed,
        "network_drop_rate_pct": round(network_drop_rate * 100, 2),
        "simulation_duration_s": SIMULATION_DURATION_S,
        "telemetry_period_s": SAMPLE_PERIOD_S,
        "disconnect_at_s": DEVICE_DISCONNECT_S,
        "mqtt_keepalive_s": MQTT_KEEPALIVE_S,
        "lwt_detection_latency_s": lwt_detection_latency_s,
        "generated_messages": generated_messages,
        "received_messages": received_messages,
        "delivery_ratio_pct": round(received_messages / generated_messages * 100, 2),
        "network_latency_mean_ms": round(mean(latencies), 2) if latencies else None,
        "network_latency_p95_ms": (
            round(percentile(latencies, 0.95), 2) if latencies else None
        ),
        "alarm_count": sum(
            event["type"] in ("temperature_excursion", "door_open_too_long")
            for event in events
        ),
        "temperature_excursions": sum(
            event["type"] == "temperature_excursion" for event in events
        ),
        "door_open_alarms": sum(
            event["type"] == "door_open_too_long" for event in events
        ),
        "observed_temperature_compliance_pct": (
            round(
                sum(
                    TEMPERATURE_MIN_C
                    <= float(record["temperature_c"])
                    <= TEMPERATURE_MAX_C
                    for record in records
                )
                / len(records)
                * 100,
                2,
            )
            if records
            else None
        ),
        "temperature_excursion_degree_minutes": (
            _temperature_excursion_degree_minutes(records)
        ),
        "temperature_alarm_detected_pct": (
            100.0 if temperature_alarm_time is not None else 0.0
        ),
        "temperature_alarm_detection_delay_s": (
            round(temperature_alarm_time - TEMPERATURE_EXCURSION_START_S, 2)
            if temperature_alarm_time is not None
            else None
        ),
        "door_alarm_detected_pct": 100.0 if door_alarm_time is not None else 0.0,
        "door_alarm_time_from_open_s": (
            round(door_alarm_time - DOOR_OPEN_START_S, 2)
            if door_alarm_time is not None
            else None
        ),
        "door_alarm_delay_after_threshold_s": (
            round(
                door_alarm_time
                - DOOR_OPEN_START_S
                - DOOR_ALARM_AFTER_S,
                2,
            )
            if door_alarm_time is not None
            else None
        ),
        "excursion_window_delivery_pct": round(
            received_excursion_samples / excursion_sample_count * 100, 2
        ),
    }

    if write_reports:
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "telemetry.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "timestamp_s",
                    "temperature_c",
                    "humidity_pct",
                    "door_open",
                    "mqtt_latency_ms",
                ],
            )
            writer.writeheader()
            writer.writerows(records)

        (output_dir / "events.json").write_text(
            json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (output_dir / "simulation_metrics.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        _write_performance_chart(
            output_dir / "performance_overview.png", records, events
        )
        _write_system_performance_chart(
            output_dir / "system_performance.png",
            records,
            generated_messages,
            received_messages,
            lwt_detection_latency_s,
        )
    return metrics


def _write_performance_chart(
    output_path: Path,
    records: list[dict[str, object]],
    events: list[dict[str, object]],
) -> None:
    """Render the detailed first-trial temperature and latency timeline.

    ``run_simulation`` passes the delivered telemetry rows and event records.
    The upper panel compares observed temperatures with the 2-8 C compliance
    band and marks samples received while the door was open. The lower panel
    plots per-message latency and overlays detected alarm and disconnect
    times. This function only writes the requested PNG; it does not change
    metrics or simulation state.
    """
    times = [float(row["timestamp_s"]) / 60 for row in records]
    temperatures = [float(row["temperature_c"]) for row in records]
    latencies = [float(row["mqtt_latency_ms"]) for row in records]
    door_open_times = [
        float(row["timestamp_s"]) / 60 for row in records if row["door_open"]
    ]
    door_open_temps = [
        float(row["temperature_c"]) for row in records if row["door_open"]
    ]
    alarm_events = [
        event
        for event in events
        if event["type"] in ("temperature_excursion", "door_open_too_long")
    ]

    figure, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)
    axes[0].plot(times, temperatures, label="Temperature (C)", color="#1565c0")
    axes[0].axhspan(
        TEMPERATURE_MIN_C,
        TEMPERATURE_MAX_C,
        color="#66bb6a",
        alpha=0.16,
        label="Compliance range (2-8 C)",
    )
    axes[0].scatter(
        door_open_times,
        door_open_temps,
        label="Door open",
        color="#ef6c00",
        s=18,
    )
    axes[0].set_ylabel("Temperature (C)")
    axes[0].set_title("Cold-chain telemetry simulation")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.25)

    axes[1].plot(times, latencies, label="MQTT latency (ms)", color="#6a1b9a")
    axes[1].axhline(
        percentile(latencies, 0.95),
        color="#ad1457",
        linestyle="--",
        label=f"P95: {percentile(latencies, 0.95):.1f} ms",
    )
    for index, event in enumerate(alarm_events):
        axes[1].axvline(
            float(event["timestamp_s"]) / 60,
            color="#d32f2f",
            alpha=0.55,
            linestyle=":",
            label="Alarm detected" if index == 0 else None,
        )
    offline_at_min = DEVICE_DISCONNECT_S / 60
    axes[1].axvline(
        offline_at_min, color="#424242", linestyle="--", label="Node disconnect"
    )
    axes[1].set_xlabel("Simulated time (minutes)")
    axes[1].set_ylabel("Latency (ms)")
    axes[1].legend(loc="upper right")
    axes[1].grid(alpha=0.25)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _write_system_performance_chart(
    output_path: Path,
    records: list[dict[str, object]],
    generated_messages: int,
    received_messages: int,
    lwt_detection_latency_s: float,
) -> None:
    """Render first-trial latency, delivery, and availability summaries.

    The chart combines per-message latency with its mean/P95, counts received
    versus lost messages, and compares the configured keep-alive to the
    modeled LWT detection delay. ``run_simulation`` supplies all values after
    the trial; the LWT panel is an estimate, not a live broker observation.
    """
    times = [float(row["timestamp_s"]) / 60 for row in records]
    latencies = [float(row["mqtt_latency_ms"]) for row in records]
    latency_mean = mean(latencies) if latencies else 0.0
    latency_p95 = percentile(latencies, 0.95)
    lost_messages = generated_messages - received_messages

    figure, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    axes[0].plot(times, latencies, color="#6a1b9a", linewidth=1, label="Samples")
    axes[0].axhline(
        latency_mean,
        color="#00838f",
        linestyle="--",
        label=f"Mean: {latency_mean:.1f} ms",
    )
    axes[0].axhline(
        latency_p95,
        color="#ad1457",
        linestyle=":",
        label=f"P95: {latency_p95:.1f} ms",
    )
    axes[0].set_title("Simulated network latency")
    axes[0].set_ylabel("Latency (ms)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.25)

    bars = axes[1].bar(
        ["Received", "Lost"],
        [received_messages, lost_messages],
        color=["#2e7d32", "#c62828"],
    )
    axes[1].bar_label(bars)
    delivery_ratio = received_messages / generated_messages * 100
    axes[1].set_title(f"Simulated MQTT delivery: {delivery_ratio:.2f}%")
    axes[1].set_ylabel("Messages")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].bar(
        ["Keep-alive", "LWT detection"],
        [MQTT_KEEPALIVE_S, lwt_detection_latency_s],
        color=["#546e7a", "#ef6c00"],
    )
    axes[2].set_title("Availability after simulated abrupt disconnect")
    axes[2].set_ylabel("Time (s)")
    axes[2].grid(axis="y", alpha=0.25)

    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def run_experiment(
    output_dir: Path,
    base_seed: int = 410103,
    runs: int = 1,
    network_drop_rate: float = NETWORK_DROP_RATE,
) -> dict[str, object]:
    """Run a sequential seed sweep and write per-seed aggregate reports.

    The first seed calls ``run_simulation`` with report writing enabled to
    preserve a detailed example; later seeds collect metrics only. Each metric
    is passed to ``_aggregate_metric``, then the function writes
    ``seed_sweep_metrics.json`` and invokes the seed-distribution and alarm
    response chart writers. The returned summary is also printed by ``main``
    and becomes the baseline section of an optional CLI sensitivity result.
    """
    if runs < 1:
        raise ValueError("runs must be at least 1")

    seed_values = [base_seed + run_index for run_index in range(runs)]
    trial_metrics: list[dict[str, object]] = []
    for run_index, seed in enumerate(seed_values):
        trial_metrics.append(
            run_simulation(
                output_dir,
                seed=seed,
                network_drop_rate=network_drop_rate,
                write_reports=run_index == 0,
            )
        )

    metric_names = (
        "delivery_ratio_pct",
        "network_latency_mean_ms",
        "network_latency_p95_ms",
        "alarm_count",
        "temperature_excursions",
        "door_open_alarms",
        "observed_temperature_compliance_pct",
        "temperature_excursion_degree_minutes",
        "temperature_alarm_detected_pct",
        "temperature_alarm_detection_delay_s",
        "door_alarm_detected_pct",
        "door_alarm_time_from_open_s",
        "door_alarm_delay_after_threshold_s",
        "excursion_window_delivery_pct",
    )
    aggregated_metrics: dict[str, dict[str, object]] = {}
    for metric_name in metric_names:
        aggregated_metrics[metric_name] = _aggregate_metric(
            [metrics[metric_name] for metrics in trial_metrics]
        )

    summary: dict[str, object] = {
        "simulation": "synthetic; not measured on physical hardware",
        "base_seed": base_seed,
        "run_count": runs,
        "network_drop_rate_pct": round(network_drop_rate * 100, 2),
        "seed_values": seed_values,
        "confidence_interval_method": (
            "Normal approximation: mean +/- 1.96 * sample standard deviation / sqrt(n); "
            "computed from available detections and descriptive only, especially for small "
            "samples."
            if runs > 1
            else "Not estimated for a single run."
        ),
        "metrics": aggregated_metrics,
    }
    (output_dir / "seed_sweep_metrics.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    _write_seed_sweep_chart(
        output_dir / "seed_sweep_performance.png", trial_metrics, runs
    )
    _write_alarm_response_chart(
        output_dir / "alarm_response_analysis.png", trial_metrics, runs
    )
    return summary


def _write_seed_sweep_chart(
    output_path: Path, trial_metrics: list[dict[str, object]], runs: int
) -> None:
    """Compare per-trial delivery and latency distributions across seeds.

    The input list contains one metric dictionary per seed. Each histogram bar
    counts trials rather than messages; the dashed line is the mean across
    seeds and the shaded region is a descriptive confidence interval for that
    mean. This chart is called by ``run_experiment`` after aggregation.
    """
    series = (
        ("delivery_ratio_pct", "Message delivery ratio (%)", "#2e7d32"),
        ("network_latency_mean_ms", "Mean network latency (ms)", "#00838f"),
        ("network_latency_p95_ms", "P95 network latency (ms)", "#6a1b9a"),
    )
    figure, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    for axis, (metric_name, title, color) in zip(axes, series):
        values = [
            float(metrics[metric_name])
            for metrics in trial_metrics
            if isinstance(metrics[metric_name], (int, float))
        ]
        if values:
            axis.hist(values, bins=min(20, max(1, runs)), color=color, alpha=0.8)
            average = mean(values)
            standard_deviation = stdev(values) if len(values) > 1 else None
            if standard_deviation is not None:
                margin = 1.96 * standard_deviation / math.sqrt(len(values))
                axis.axvspan(
                    average - margin,
                    average + margin,
                    color="#212121",
                    alpha=0.12,
                    label="Approx. 95% CI for mean",
                )
            axis.axvline(
                average,
                color="#212121",
                linestyle="--",
                label=f"Mean across seeds: {average:.2f}",
            )
        else:
            axis.text(0.5, 0.5, "No observations", ha="center", va="center")
        axis.set_title(title)
        axis.set_xlabel("One per-trial metric value per seed")
        axis.set_ylabel("Number of seeds")
        axis.legend(loc="upper right")
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle(f"Monte Carlo seed sweep (n={runs})")
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _write_alarm_response_chart(
    output_path: Path, trial_metrics: list[dict[str, object]], runs: int
) -> None:
    """Compare fault-response delays and observed thermal exposure by seed.

    The panels use the per-trial metrics returned by ``run_simulation``:
    temperature alert delay from excursion start, door alert delay after its
    30-second limit, and contiguous-sample degree-minutes. Missing detections
    are omitted from delay histograms and recorded separately in the JSON
    summary. The fixed LWT estimate is displayed for context, not sampled.
    """
    series = (
        (
            "temperature_alarm_detection_delay_s",
            "Temperature alarm: delay after excursion starts",
            "Delay (s)",
            "#c62828",
        ),
        (
            "door_alarm_delay_after_threshold_s",
            "Door alarm: delay after 30-second limit",
            "Additional delay (s)",
            "#ef6c00",
        ),
        (
            "temperature_excursion_degree_minutes",
            "Observed thermal exposure during the excursion",
            "Degree-minutes (C min)",
            "#1565c0",
        ),
    )
    figure, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    for axis, (metric_name, title, x_label, color) in zip(axes, series):
        values = [
            float(metrics[metric_name])
            for metrics in trial_metrics
            if isinstance(metrics[metric_name], (int, float))
        ]
        if values:
            axis.hist(
                values,
                bins=min(20, max(1, len(values))),
                color=color,
                alpha=0.8,
            )
            axis.axvline(
                mean(values),
                color="#212121",
                linestyle="--",
                label=f"Mean: {mean(values):.2f}",
            )
            axis.legend(loc="upper right")
        else:
            axis.text(0.5, 0.5, "No observations", ha="center", va="center")
        axis.set_title(title)
        axis.set_xlabel(x_label)
        axis.set_ylabel("Number of seeds")
        axis.grid(axis="y", alpha=0.25)

    figure.suptitle(
        f"Operational alarm and thermal metrics (n={runs}); LWT estimate: "
        f"{MQTT_KEEPALIVE_S * 1.5:.0f} s"
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def run_sensitivity_analysis(
    output_dir: Path,
    base_seed: int = 410103,
    runs: int = 100,
    drop_rates: tuple[float, ...] = NETWORK_DROP_RATES,
    keepalive_values_s: tuple[int, ...] = MQTT_KEEPALIVE_SCENARIOS_S,
) -> dict[str, object]:
    """Run packet-loss replications and calculate keep-alive/LWT estimates.

    For each configured drop rate, the function calls ``run_simulation`` for
    the same sequential seed values with file output disabled, then aggregates
    delivery, event-window coverage, alarm detection, and response delay.
    Keep-alive points are calculated from the explicit ``1.5 x keep-alive``
    assumption rather than measured by a broker. The function writes separate
    network/LWT JSON reports and charts, and returns both summaries to ``main``.
    """
    if runs < 1:
        raise ValueError("runs must be at least 1")
    if not drop_rates:
        raise ValueError("drop_rates must contain at least one scenario")
    if not keepalive_values_s or any(value < 1 for value in keepalive_values_s):
        raise ValueError("keepalive_values_s must contain positive values")
    if any(not 0 <= rate < 1 for rate in drop_rates):
        raise ValueError("drop rates must be at least 0 and less than 1")

    seed_values = [base_seed + run_index for run_index in range(runs)]
    metric_names = (
        "delivery_ratio_pct",
        "excursion_window_delivery_pct",
        "temperature_alarm_detected_pct",
        "temperature_alarm_detection_delay_s",
        "door_alarm_detected_pct",
        "door_alarm_delay_after_threshold_s",
    )
    network_scenarios: list[dict[str, object]] = []
    for drop_rate in drop_rates:
        scenario_trials = [
            run_simulation(
                output_dir,
                seed=seed,
                network_drop_rate=drop_rate,
                write_reports=False,
            )
            for seed in seed_values
        ]
        network_scenarios.append(
            {
                "network_drop_rate_pct": round(drop_rate * 100, 2),
                "metrics": {
                    metric_name: _aggregate_metric(
                        [trial[metric_name] for trial in scenario_trials]
                    )
                    for metric_name in metric_names
                },
            }
        )

    network_summary: dict[str, object] = {
        "simulation": "synthetic; not measured on physical hardware",
        "base_seed": base_seed,
        "run_count_per_scenario": runs,
        "seed_values": seed_values,
        "seed_method": (
            "The same seed sequence is reused for each scenario; changing drop probability "
            "can alter later random draws within a trial."
        ),
        "confidence_interval_method": (
            "Normal approximation based on the sample standard deviation; descriptive only."
            if runs > 1
            else "Not estimated for a single run."
        ),
        "scenarios": network_scenarios,
    }

    keepalive_scenarios = [
        {
            "mqtt_keepalive_s": keepalive_s,
            "estimated_lwt_detection_latency_s": round(keepalive_s * 1.5, 2),
        }
        for keepalive_s in keepalive_values_s
    ]
    lwt_summary: dict[str, object] = {
        "simulation": "theoretical MQTT estimate; not broker-measured",
        "assumption": "LWT detection is estimated as 1.5 times the configured keep-alive.",
        "scenarios": keepalive_scenarios,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "network_sensitivity_metrics.json").write_text(
        json.dumps(network_summary, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "lwt_keepalive_sensitivity.json").write_text(
        json.dumps(lwt_summary, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    _write_network_sensitivity_chart(
        output_dir / "network_loss_sensitivity.png", network_scenarios
    )
    _write_keepalive_sensitivity_chart(
        output_dir / "lwt_keepalive_sensitivity.png", keepalive_scenarios
    )
    return {"network_loss": network_summary, "lwt_keepalive": lwt_summary}


def _write_network_sensitivity_chart(
    output_path: Path, scenarios: list[dict[str, object]]
) -> None:
    """Plot delivery and alarm-delay means for each packet-loss scenario.

    ``run_sensitivity_analysis`` supplies scenario summaries containing means
    and approximate confidence intervals. The first two panels show total
    delivery and delivery during the injected temperature excursion; the
    final panel compares temperature and door response delays. Error bars
    describe uncertainty in scenario means, not individual-message latency.
    """
    drop_rates = [
        float(scenario["network_drop_rate_pct"]) for scenario in scenarios
    ]
    figure, axes = plt.subplots(3, 1, figsize=(10, 10), constrained_layout=True)
    delivery_series = (
        (
            axes[0],
            "delivery_ratio_pct",
            "Overall telemetry delivery",
            "Received messages (%)",
            "#2e7d32",
        ),
        (
            axes[1],
            "excursion_window_delivery_pct",
            "Telemetry delivery during the temperature excursion",
            "Received excursion samples (%)",
            "#1565c0",
        ),
    )
    for axis, metric_name, title, y_label, color in delivery_series:
        values: list[float] = []
        lower_errors: list[float] = []
        upper_errors: list[float] = []
        valid_drop_rates: list[float] = []
        for drop_rate, scenario in zip(drop_rates, scenarios):
            scenario_metrics = scenario["metrics"]
            if not isinstance(scenario_metrics, dict):
                continue
            summary = scenario_metrics[metric_name]
            if not isinstance(summary, dict) or not isinstance(
                summary.get("mean"), (int, float)
            ):
                continue
            average = float(summary["mean"])
            interval = summary["approximate_95_percent_confidence_interval"]
            values.append(average)
            valid_drop_rates.append(drop_rate)
            if (
                isinstance(interval, list)
                and len(interval) == 2
                and isinstance(interval[0], (int, float))
                and isinstance(interval[1], (int, float))
            ):
                lower_errors.append(max(0.0, average - float(interval[0])))
                upper_errors.append(max(0.0, float(interval[1]) - average))
            else:
                lower_errors.append(0.0)
                upper_errors.append(0.0)

        if values:
            axis.errorbar(
                valid_drop_rates,
                values,
                yerr=[lower_errors, upper_errors],
                marker="o",
                capsize=4,
                color=color,
            )
        axis.set_title(title)
        axis.set_ylabel(y_label)
        axis.grid(alpha=0.25)

    axis = axes[2]
    delay_series = (
        (
            "temperature_alarm_detection_delay_s",
            "Temperature alarm delay",
            "#c62828",
        ),
        (
            "door_alarm_delay_after_threshold_s",
            "Door alarm delay after limit",
            "#ef6c00",
        ),
    )
    for metric_name, label, color in delay_series:
        values = []
        lower_errors = []
        upper_errors = []
        valid_drop_rates = []
        for drop_rate, scenario in zip(drop_rates, scenarios):
            scenario_metrics = scenario["metrics"]
            if not isinstance(scenario_metrics, dict):
                continue
            summary = scenario_metrics[metric_name]
            if not isinstance(summary, dict) or not isinstance(
                summary.get("mean"), (int, float)
            ):
                continue
            average = float(summary["mean"])
            interval = summary["approximate_95_percent_confidence_interval"]
            values.append(average)
            valid_drop_rates.append(drop_rate)
            if (
                isinstance(interval, list)
                and len(interval) == 2
                and isinstance(interval[0], (int, float))
                and isinstance(interval[1], (int, float))
            ):
                lower_errors.append(max(0.0, average - float(interval[0])))
                upper_errors.append(max(0.0, float(interval[1]) - average))
            else:
                lower_errors.append(0.0)
                upper_errors.append(0.0)
        if values:
            axis.errorbar(
                valid_drop_rates,
                values,
                yerr=[lower_errors, upper_errors],
                marker="o",
                capsize=4,
                label=label,
                color=color,
            )
    axis.set_title("Alarm response as packet loss increases")
    axis.set_xlabel("Configured message-drop probability (%)")
    axis.set_ylabel("Delay (s)")
    axis.legend(loc="upper left")
    axis.grid(alpha=0.25)
    figure.suptitle(
        "Synthetic network-loss sensitivity; error bars are approximate 95% CIs"
    )
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def _write_keepalive_sensitivity_chart(
    output_path: Path, scenarios: list[dict[str, object]]
) -> None:
    """Plot formula-derived LWT delay estimates for configured keep-alives.

    The scenario dictionaries are produced by ``run_sensitivity_analysis``.
    The curve applies the model's 1.5 multiplier and highlights the project's
    30-second setting. Saving the figure is the only side effect; it does not
    start a broker or simulate MQTT packet exchange.
    """
    keepalives = [int(scenario["mqtt_keepalive_s"]) for scenario in scenarios]
    detection_delays = [
        float(scenario["estimated_lwt_detection_latency_s"])
        for scenario in scenarios
    ]
    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    axis.plot(keepalives, detection_delays, marker="o", color="#ef6c00")
    axis.scatter(
        [MQTT_KEEPALIVE_S],
        [MQTT_KEEPALIVE_S * 1.5],
        color="#c62828",
        zorder=3,
        label=f"Project setting: {MQTT_KEEPALIVE_S} s → "
        f"{MQTT_KEEPALIVE_S * 1.5:.0f} s estimate",
    )
    axis.set_title("Theoretical MQTT Last Will detection estimate")
    axis.set_xlabel("Configured MQTT keep-alive (s)")
    axis.set_ylabel("Estimated offline detection time (s)")
    axis.text(
        0.03,
        0.95,
        "Estimate = 1.5 x keep-alive; actual broker timing may differ.",
        transform=axis.transAxes,
        va="top",
    )
    axis.legend(loc="lower right")
    axis.grid(alpha=0.25)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> None:
    """Validate CLI options, run requested analyses, and print JSON results.

    Command-line parsing chooses the output directory, seed range, drop rate,
    and whether sensitivity scenarios are included. Invalid run counts and
    drop rates are rejected through ``argparse`` before report generation.
    ``run_experiment`` always runs; ``run_sensitivity_analysis`` runs only
    when the corresponding flag is set.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports",
        help="Directory for metrics, events, telemetry, and charts",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=410103,
        help="Base seed used for the first trial (default: 410103)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of independent sequential seeds (default: 1)",
    )
    parser.add_argument(
        "--drop-rate",
        type=float,
        default=NETWORK_DROP_RATE,
        help="Per-message drop probability from 0 to less than 1 (default: 0.01)",
    )
    parser.add_argument(
        "--sensitivity-analysis",
        action="store_true",
        help="Also compare packet-loss and MQTT keep-alive scenarios",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not 0 <= args.drop_rate < 1:
        parser.error("--drop-rate must be at least 0 and less than 1")
    summary = run_experiment(
        args.output_dir,
        base_seed=args.seed,
        runs=args.runs,
        network_drop_rate=args.drop_rate,
    )
    if args.sensitivity_analysis:
        summary["sensitivity_analysis"] = run_sensitivity_analysis(
            args.output_dir,
            base_seed=args.seed,
            runs=args.runs,
        )
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
