#!/usr/bin/env python3
"""Generate deterministic synthetic telemetry, performance metrics, and charts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from statistics import mean

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
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def run_simulation(output_dir: Path, seed: int = 410103) -> dict[str, object]:
    """Run one simulated hour and write CSV, JSON, and a PNG performance plot."""
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
    times = [float(row["timestamp_s"]) / 60 for row in records]
    temperatures = [float(row["temperature_c"]) for row in records]
    humidities = [float(row["humidity_pct"]) for row in records]
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
    axes[0].plot(times, temperatures, label="Temperatura (°C)", color="#1565c0")
    axes[0].axhspan(
        TEMPERATURE_MIN_C, TEMPERATURE_MAX_C, color="#66bb6a", alpha=0.16,
        label="Faixa de conformidade (2–8 °C)",
    )
    axes[0].scatter(
        door_open_times,
        door_open_temps,
        label="Porta aberta",
        color="#ef6c00",
        s=18,
    )
    axes[0].set_ylabel("Temperatura (°C)")
    axes[0].set_title("Simulação da telemetria de cadeia de frio")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.25)

    axes[1].plot(times, latencies, label="Latência MQTT (ms)", color="#6a1b9a")
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
            label="Alarme detectado" if index == 0 else None,
        )
    offline_at_min = DEVICE_DISCONNECT_S / 60
    axes[1].axvline(
        offline_at_min, color="#424242", linestyle="--", label="Desconexão do nó"
    )
    axes[1].set_xlabel("Tempo simulado (minutos)")
    axes[1].set_ylabel("Latência (ms)")
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
    times = [float(row["timestamp_s"]) / 60 for row in records]
    latencies = [float(row["mqtt_latency_ms"]) for row in records]
    latency_mean = mean(latencies)
    latency_p95 = percentile(latencies, 0.95)
    lost_messages = generated_messages - received_messages

    figure, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    axes[0].plot(times, latencies, color="#6a1b9a", linewidth=1, label="Amostras")
    axes[0].axhline(
        latency_mean,
        color="#00838f",
        linestyle="--",
        label=f"Média: {latency_mean:.1f} ms",
    )
    axes[0].axhline(
        latency_p95,
        color="#ad1457",
        linestyle=":",
        label=f"P95: {latency_p95:.1f} ms",
    )
    axes[0].set_title("Latência de rede simulada")
    axes[0].set_ylabel("Latência (ms)")
    axes[0].legend(loc="upper right")
    axes[0].grid(alpha=0.25)

    bars = axes[1].bar(
        ["Recebidas", "Perdidas"],
        [received_messages, lost_messages],
        color=["#2e7d32", "#c62828"],
    )
    axes[1].bar_label(bars)
    delivery_ratio = received_messages / generated_messages * 100
    axes[1].set_title(f"Entrega MQTT simulada: {delivery_ratio:.2f}%")
    axes[1].set_ylabel("Mensagens")
    axes[1].grid(axis="y", alpha=0.25)

    axes[2].bar(
        ["Keep-alive", "Detecção LWT"],
        [MQTT_KEEPALIVE_S, lwt_detection_latency_s],
        color=["#546e7a", "#ef6c00"],
    )
    axes[2].set_title("Disponibilidade após desconexão abrupta simulada")
    axes[2].set_ylabel("Tempo (s)")
    axes[2].grid(axis="y", alpha=0.25)

    figure.savefig(output_path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "reports",
        help="diretório para salvar métricas, eventos, CSV e gráfico",
    )
    parser.add_argument("--seed", type=int, default=410103)
    args = parser.parse_args()
    metrics = run_simulation(args.output_dir, seed=args.seed)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
