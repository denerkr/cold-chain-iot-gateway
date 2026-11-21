#!/usr/bin/env python3
"""Generate deterministic synthetic telemetry, performance metrics, and charts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import tempfile
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
TEMPERATURE_MIN_C = 2.0
TEMPERATURE_MAX_C = 8.0
DOOR_ALARM_AFTER_S = 30


def percentile(values: list[float], quantile: float) -> float:
    """Return the nearest-rank percentile of the supplied values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def run_simulation(output_dir: Path, seed: int = 410103) -> dict[str, object]:
    """Run one synthetic trial and write its telemetry, events, metrics, and charts."""
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
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
        if rng.random() < NETWORK_DROP_RATE:
            continue

        temperature_c = 4.8 + rng.gauss(0, 0.35)
        if 120 <= timestamp_s < 290:
            temperature_c = 9.2 + rng.gauss(0, 0.2)
        humidity_pct = min(75.0, max(30.0, 55 + rng.gauss(0, 2.0)))
        door_open = 200 <= timestamp_s < 260
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
    metrics: dict[str, object] = {
        "simulation": "synthetic; not measured on physical hardware",
        "seed": seed,
        "simulation_duration_s": SIMULATION_DURATION_S,
        "telemetry_period_s": SAMPLE_PERIOD_S,
        "disconnect_at_s": DEVICE_DISCONNECT_S,
        "mqtt_keepalive_s": MQTT_KEEPALIVE_S,
        "lwt_detection_latency_s": lwt_detection_latency_s,
        "generated_messages": generated_messages,
        "received_messages": received_messages,
        "delivery_ratio_pct": round(received_messages / generated_messages * 100, 2),
        "network_latency_mean_ms": round(mean(latencies), 2),
        "network_latency_p95_ms": round(percentile(latencies, 0.95), 2),
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
    }

    csv_path = output_dir / "telemetry.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    (output_dir / "events.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "simulation_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_performance_chart(output_dir / "performance_overview.png", records, events)
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
    """Plot thermal compliance, door state, alarm times, and MQTT latency."""
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
    """Plot latency, message delivery, and estimated MQTT last-will detection."""
    times = [float(row["timestamp_s"]) / 60 for row in records]
    latencies = [float(row["mqtt_latency_ms"]) for row in records]
    latency_mean = mean(latencies)
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
    output_dir: Path, base_seed: int = 410103, runs: int = 1
) -> dict[str, object]:
    """Run sequential independent seeds and report means, spread, and approximate intervals."""
    if runs < 1:
        raise ValueError("runs must be at least 1")

    seed_values = [base_seed + run_index for run_index in range(runs)]
    trial_metrics: list[dict[str, object]] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    for run_index, seed in enumerate(seed_values):
        if run_index == 0:
            trial_metrics.append(run_simulation(output_dir, seed=seed))
            continue

        # Keep additional trial artifacts temporary; preserve the first trial as a detailed example.
        with tempfile.TemporaryDirectory(prefix="cold-chain-seed-") as temporary_directory:
            trial_metrics.append(run_simulation(Path(temporary_directory), seed=seed))

    metric_names = (
        "delivery_ratio_pct",
        "network_latency_mean_ms",
        "network_latency_p95_ms",
        "alarm_count",
        "temperature_excursions",
        "door_open_alarms",
    )
    aggregated_metrics: dict[str, dict[str, object]] = {}
    for metric_name in metric_names:
        values = [float(metrics[metric_name]) for metrics in trial_metrics]
        average = mean(values)
        standard_deviation = stdev(values) if runs > 1 else None
        interval = None
        if standard_deviation is not None:
            # This normal-approximation interval is descriptive, especially for small run counts.
            margin = 1.96 * standard_deviation / math.sqrt(runs)
            interval = [round(average - margin, 4), round(average + margin, 4)]
        aggregated_metrics[metric_name] = {
            "mean": round(average, 4),
            "values": [round(value, 4) for value in values],
            "sample_standard_deviation": (
                round(standard_deviation, 4)
                if standard_deviation is not None
                else None
            ),
            "approximate_95_percent_confidence_interval": interval,
        }

    summary: dict[str, object] = {
        "simulation": "synthetic; not measured on physical hardware",
        "base_seed": base_seed,
        "run_count": runs,
        "seed_values": seed_values,
        "confidence_interval_method": (
            "Normal approximation: mean +/- 1.96 * sample standard deviation / sqrt(n); "
            "descriptive only, especially for small samples."
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
    return summary


def _write_seed_sweep_chart(
    output_path: Path, trial_metrics: list[dict[str, object]], runs: int
) -> None:
    """Visualize delivery ratio, average latency, and P95 across seed trials."""
    series = (
        ("delivery_ratio_pct", "Message delivery ratio (%)", "#2e7d32"),
        ("network_latency_mean_ms", "Mean network latency (ms)", "#00838f"),
        ("network_latency_p95_ms", "P95 network latency (ms)", "#6a1b9a"),
    )
    figure, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    for axis, (metric_name, title, color) in zip(axes, series):
        values = [float(metrics[metric_name]) for metrics in trial_metrics]
        axis.hist(values, bins=min(20, max(1, runs)), color=color, alpha=0.8)
        axis.axvline(mean(values), color="#212121", linestyle="--", label=f"Mean: {mean(values):.2f}")
        axis.set_title(title)
        axis.set_xlabel("Metric value across independent seeds")
        axis.set_ylabel("Run count")
        axis.legend(loc="upper right")
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle(f"Monte Carlo seed sweep (n={runs})")
    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> None:
    """Parse command-line options, run the seed sweep, and print its summary."""
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
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    summary = run_experiment(args.output_dir, base_seed=args.seed, runs=args.runs)
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
