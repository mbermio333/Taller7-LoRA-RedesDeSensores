#!/usr/bin/env python3
"""
lora_analysis.py – Genera graficas de caracterizacion del enlace LoRa P2P
                   y tabla de estimacion de consumo/bateria por SF.

Uso:
  python3 lora_analysis.py --input lora_data.csv

Genera:
  1. RSSI vs Distancia (por SF)
  2. SNR  vs Distancia (por SF)
  3. PDR  vs Distancia (por SF)
  4. Heatmap RSSI (SF × Distancia)
  5. Tabla de Time-on-Air y autonomia por SF (impresa en consola + PNG)

Requiere: pip install pandas matplotlib seaborn numpy
"""

import argparse
import math
import sys

try:
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib
    import seaborn as sns
    import numpy as np
except ImportError as e:
    print(f"Falta dependencia: {e}")
    print("Instala con:  pip install pandas matplotlib seaborn numpy")
    sys.exit(1)

matplotlib.rcParams.update({"font.size": 10})

# ===================== Parametros del enlace =====================
BW_HZ       = 500_000       # 500 kHz
CR_VAL      = 4              # CR 4/8  (valor 1..4 para 4/5..4/8)
PL_BYTES    = 4              # payload optimizado
PREAMBLE    = 8
HEADER_ON   = True           # H=0 (explicit header)
CRC_ON      = True
TX_POWER_DBM = 10
TX_CURRENT_MA = 100          # mA (valor del taller; a 10 dBm es ~30 mA real)
SLEEP_CURRENT_UA = 10        # uA (ESP32-S3 deep sleep + SX1262 sleep)
BATTERY_MAH  = 2000

# SNR demod limits (Semtech typical)
SNR_LIMITS = {7: -7.5, 8: -10.0, 9: -12.5, 10: -15.0, 11: -17.5, 12: -20.0}
NF_DB = 6  # SX1262 noise figure


# ===================== Calculo Time-on-Air =====================
def lora_toa_ms(sf, bw_hz=BW_HZ, cr=CR_VAL, pl=PL_BYTES,
                preamble=PREAMBLE, header=HEADER_ON, crc=CRC_ON,
                ldro=None):
    """Calcula Time-on-Air en ms segun formula Semtech AN1200.13."""
    t_sym = (2**sf) / bw_hz * 1000  # ms

    # LDRO: auto si no se especifica
    if ldro is None:
        ldro = t_sym >= 16.38

    de = 1 if ldro else 0
    h  = 0 if header else 1
    crc_bits = 16 if crc else 0

    # Preambulo
    t_preamble = (preamble + 4.25) * t_sym

    # Simbolos de payload
    numerator   = 8 * pl - 4 * sf + 28 + crc_bits - 20 * h
    denominator = 4 * (sf - 2 * de)
    if denominator <= 0:
        denominator = 4 * sf  # fallback seguro
    n_payload = 8 + max(math.ceil(numerator / denominator) * (cr + 4), 0)

    t_payload = n_payload * t_sym
    return t_preamble + t_payload


def sensitivity_dbm(sf, bw_hz=BW_HZ, nf=NF_DB):
    """Sensibilidad teorica del receptor en dBm."""
    snr = SNR_LIMITS.get(sf, -7.5)
    return -174 + 10 * math.log10(bw_hz) + nf + snr


# ===================== Graficas =====================
def plot_metric(df_avg, metric, ylabel, title, filename,
                ref_line=None, ref_label=None):
    """Grafica metrica vs distancia, una curva por SF."""
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = {7: "#e74c3c", 9: "#2ecc71", 12: "#3498db"}
    markers = {7: "o", 9: "s", 12: "^"}

    for sf in sorted(df_avg["sf"].unique()):
        sub = df_avg[df_avg["sf"] == sf].sort_values("distance_m")
        ax.plot(sub["distance_m"], sub[metric],
                marker=markers.get(sf, "o"), color=colors.get(sf, "gray"),
                label=f"SF{sf}", linewidth=2, markersize=7)

    if ref_line is not None:
        ax.axhline(y=ref_line, linestyle="--", color="gray", alpha=0.7,
                   label=ref_label)

    ax.set_xlabel("Distancia (m)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"  -> {filename}")
    plt.close(fig)


def plot_heatmap(df_avg, filename):
    """Heatmap RSSI (filas=SF, columnas=distancia)."""
    pivot = df_avg.pivot_table(index="sf", columns="distance_m",
                               values="rssi_dbm", aggfunc="mean")
    pivot = pivot.sort_index(ascending=True)

    fig, ax = plt.subplots(figsize=(8, 3))
    sns.heatmap(pivot, annot=True, fmt=".0f", cmap="RdYlGn_r",
                cbar_kws={"label": "RSSI (dBm)"}, ax=ax,
                linewidths=0.5, linecolor="white")
    ax.set_title("Heatmap RSSI (dBm)")
    ax.set_ylabel("SF")
    ax.set_xlabel("Distancia (m)")
    fig.tight_layout()
    fig.savefig(filename, dpi=150, bbox_inches="tight")
    print(f"  -> {filename}")
    plt.close(fig)


# ===================== Tabla bateria / ToA =====================
def battery_table():
    """Imprime y grafica tabla de ToA y estimacion de bateria por SF."""
    sfs = [7, 9, 12]
    rows = []
    for sf in sfs:
        ldro_forced = (sf == 12)  # forzado para SF12 segun requisito
        toa = lora_toa_ms(sf, ldro=ldro_forced)
        sens = sensitivity_dbm(sf)

        # Energia por paquete
        charge_per_pkt_mah = TX_CURRENT_MA * (toa / 1000) / 3600
        # Escenario 1: 1 pkt / 2 s (lab continuo)
        pkts_per_hour_lab = 1800
        tx_mah_per_hour_lab = pkts_per_hour_lab * charge_per_pkt_mah
        # Escenario 2: 1 pkt / hora (campo)
        tx_mah_per_hour_field = charge_per_pkt_mah

        # Autonomia solo TX (sleep el resto)
        sleep_mah_per_hour = SLEEP_CURRENT_UA / 1000
        # Lab (1 pkt/2s, sin dormir entre pkts → idle ~4 mA el resto)
        idle_current_ma = 4  # RX idle del SX1262
        duty_tx = toa / 2000  # fraccion del periodo de 2s
        avg_current_lab = duty_tx * TX_CURRENT_MA + (1 - duty_tx) * idle_current_ma
        hours_lab = BATTERY_MAH / avg_current_lab

        # Campo (1 pkt/h, deep sleep el resto)
        avg_current_field = (TX_CURRENT_MA * (toa / 1000) / 3600) + sleep_mah_per_hour
        hours_field = BATTERY_MAH / avg_current_field if avg_current_field > 0 else float("inf")

        rows.append({
            "SF": sf,
            "ToA (ms)": round(toa, 2),
            "Sensibilidad (dBm)": round(sens, 1),
            "I_avg lab (mA)": round(avg_current_lab, 2),
            "Autonomia lab": f"{hours_lab:.0f} h ({hours_lab/24:.0f} d)",
            "I_avg campo (mA)": round(avg_current_field * 1000, 2),  # en uA
            "Autonomia campo": f"{hours_field:.0f} h ({hours_field/24/365:.1f} a)",
        })

    # Imprimir tabla
    print("\n" + "=" * 90)
    print("ESTIMACION DE CONSUMO Y AUTONOMIA POR SF")
    print(f"  Config: BW={BW_HZ/1000:.0f} kHz, CR=4/{CR_VAL+4}, PL={PL_BYTES} B, "
          f"Tx={TX_POWER_DBM} dBm ({TX_CURRENT_MA} mA), Bat={BATTERY_MAH} mAh")
    print(f"  Lab: 1 pkt/2s, idle 4 mA entre pkts")
    print(f"  Campo: 1 pkt/h, deep sleep ({SLEEP_CURRENT_UA} uA) entre pkts")
    print("=" * 90)

    df_bat = pd.DataFrame(rows)
    print(df_bat.to_string(index=False))
    print()

    # Grafica de barras ToA
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    colors = ["#e74c3c", "#2ecc71", "#3498db"]

    toas = [r["ToA (ms)"] for r in rows]
    ax1.bar([f"SF{sf}" for sf in sfs], toas, color=colors)
    for i, v in enumerate(toas):
        ax1.text(i, v + max(toas)*0.02, f"{v:.1f} ms", ha="center", fontsize=9)
    ax1.set_ylabel("Time-on-Air (ms)")
    ax1.set_title("ToA por Spreading Factor")
    ax1.grid(axis="y", alpha=0.3)

    # Grafica autonomia
    hours_lab_list = [BATTERY_MAH / r["I_avg lab (mA)"] for r in rows]
    ax2.bar([f"SF{sf}" for sf in sfs], [h / 24 for h in hours_lab_list], color=colors)
    for i, h in enumerate(hours_lab_list):
        ax2.text(i, h/24 + max(hours_lab_list)/24*0.02,
                 f"{h/24:.0f} d", ha="center", fontsize=9)
    ax2.set_ylabel("Autonomia (dias)")
    ax2.set_title(f"Autonomia estimada (lab, 1 pkt/2s, {BATTERY_MAH} mAh)")
    ax2.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig("battery_estimation.png", dpi=150, bbox_inches="tight")
    print("  -> battery_estimation.png")
    plt.close(fig)

    return df_bat


# ===================== Main =====================
def main():
    parser = argparse.ArgumentParser(
        description="Analisis de datos LoRa P2P: graficas + estimacion de bateria")
    parser.add_argument("--input", default="lora_data.csv",
                        help="CSV generado por lora_serial.py")
    parser.add_argument("--battery-only", action="store_true",
                        help="Solo generar tabla de bateria (sin datos de campo)")
    args = parser.parse_args()

    # Siempre generar tabla de bateria / ToA
    battery_table()

    if args.battery_only:
        return

    # Leer datos de campo
    if not pd.io.common.file_exists(args.input):
        print(f"\nArchivo {args.input} no encontrado.")
        print("Ejecuta primero lora_serial.py para capturar datos, o usa --battery-only")
        return

    df = pd.read_csv(args.input)
    required = {"sf", "distance_m", "rssi_dbm", "snr_db", "pdr_pct"}
    if not required.issubset(df.columns):
        print(f"Columnas requeridas: {required}")
        print(f"Columnas encontradas: {set(df.columns)}")
        return

    print(f"\nDatos cargados: {len(df)} registros")
    print(f"SFs: {sorted(df['sf'].unique())}  |  "
          f"Distancias: {sorted(df['distance_m'].unique())} m")

    # Promedios por (SF, distancia)
    df_avg = df.groupby(["sf", "distance_m"]).agg(
        rssi_dbm=("rssi_dbm", "mean"),
        snr_db=("snr_db", "mean"),
        # PDR: tomar el ultimo valor (acumulativo) o recalcular
        pdr_pct=("pdr_pct", "last"),
        count=("seq", "count")
    ).reset_index()

    print("\nPromedios por (SF, distancia):")
    print(df_avg.to_string(index=False))

    # Generar graficas
    print("\nGenerando graficas...")

    plot_metric(df_avg, "rssi_dbm", "RSSI (dBm)",
                "RSSI vs Distancia (915.9 MHz, BW=500 kHz, CR=4/8)",
                "rssi_vs_distancia.png")

    plot_metric(df_avg, "snr_db", "SNR (dB)",
                "SNR vs Distancia (915.9 MHz, BW=500 kHz, CR=4/8)",
                "snr_vs_distancia.png",
                ref_line=0, ref_label="SNR = 0 dB")

    plot_metric(df_avg, "pdr_pct", "PDR (%)",
                "PDR vs Distancia (915.9 MHz, BW=500 kHz, CR=4/8)",
                "pdr_vs_distancia.png",
                ref_line=90, ref_label="PDR = 90 %")

    plot_heatmap(df_avg, "heatmap_rssi.png")

    # Tabla resumen para el informe
    print("\nTabla resumen para el informe (copiar a LaTeX):")
    print("-" * 70)
    print(f"{'SF':>4} {'Dist (m)':>10} {'RSSI (dBm)':>12} {'SNR (dB)':>10} "
          f"{'PDR (%)':>10} {'N pkts':>8}")
    for _, row in df_avg.iterrows():
        print(f"{int(row['sf']):>4} {int(row['distance_m']):>10} "
              f"{row['rssi_dbm']:>12.1f} {row['snr_db']:>10.1f} "
              f"{row['pdr_pct']:>10.1f} {int(row['count']):>8}")
    print("-" * 70)

    print("\nListo. Las imagenes PNG estan en el directorio actual,")
    print("listas para incluir en el informe LaTeX.")


if __name__ == "__main__":
    main()
