#!/usr/bin/env python3
"""
lora_merge.py – Une todos los CSV de una carpeta en un solo lora_data.csv limpio.

Uso:
  python3 lora_merge.py --folder ./mediciones
  python3 lora_merge.py --folder ./mediciones --output lora_data.csv

Que hace:
  1. Lee todos los .csv de la carpeta indicada
  2. Elimina BOM, filas vacias, filas duplicadas, filas con campos faltantes
  3. Recalcula el PDR real por cada grupo (sf, distancia):
       PDR = paquetes_recibidos / (max_seq - min_seq + 1) * 100
  4. Genera un CSV unico con encabezado limpio, listo para lora_analysis.py

Requisitos: pip install pandas
"""

import argparse
import glob
import os
import sys

try:
    import pandas as pd
except ImportError:
    print("Instala pandas:  pip install pandas")
    sys.exit(1)

EXPECTED_COLS = ["sf", "distance_m", "seq", "temp_c", "rssi_dbm", "snr_db", "pdr_pct", "bat_pct"]


def clean_and_load(filepath):
    """Lee un CSV manejando BOM, encoding variado, y filas basura."""
    try:
        df = pd.read_csv(filepath, encoding="utf-8-sig", skipinitialspace=True)
    except Exception:
        try:
            df = pd.read_csv(filepath, encoding="latin-1", skipinitialspace=True)
        except Exception as e:
            print(f"  WARN: No pude leer {filepath}: {e}")
            return pd.DataFrame()

    # Limpiar nombres de columna (espacios, BOM residual)
    df.columns = [c.strip().replace("\ufeff", "") for c in df.columns]

    # Verificar que tenga las columnas esperadas
    if not set(EXPECTED_COLS).issubset(df.columns):
        missing = set(EXPECTED_COLS) - set(df.columns)
        print(f"  WARN: {os.path.basename(filepath)} le faltan columnas: {missing}")
        return pd.DataFrame()

    # Quedarse solo con las columnas esperadas
    df = df[EXPECTED_COLS].copy()

    # Eliminar filas donde sf, seq o rssi esten vacios o no numericos
    for col in ["sf", "seq", "rssi_dbm"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["sf", "seq", "rssi_dbm"], inplace=True)

    # Convertir tipos
    df["sf"]         = df["sf"].astype(int)
    df["distance_m"] = pd.to_numeric(df["distance_m"], errors="coerce").astype(int)
    df["seq"]        = df["seq"].astype(int)
    df["temp_c"]     = pd.to_numeric(df["temp_c"], errors="coerce")
    df["rssi_dbm"]   = df["rssi_dbm"].astype(int)
    df["snr_db"]     = pd.to_numeric(df["snr_db"], errors="coerce").astype(int)
    df["bat_pct"]    = pd.to_numeric(df["bat_pct"], errors="coerce").astype(int)

    return df


def recalculate_pdr(df):
    """Recalcula PDR real por grupo (sf, distance_m)."""
    rows = []
    for (sf, dist), group in df.groupby(["sf", "distance_m"]):
        g = group.copy()
        min_seq = g["seq"].min()
        max_seq = g["seq"].max()
        expected = max_seq - min_seq + 1
        received = len(g)
        pdr_real = 100.0 * received / expected if expected > 0 else 0.0

        # Reemplazar pdr_pct con el valor correcto (unico por grupo)
        g["pdr_pct"] = round(pdr_real, 1)
        rows.append(g)

    return pd.concat(rows, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description="Une CSVs LoRa de una carpeta en uno solo")
    parser.add_argument("--folder", required=True, help="Carpeta con los .csv individuales")
    parser.add_argument("--output", default="lora_data.csv", help="Archivo de salida")
    args = parser.parse_args()

    csv_files = sorted(glob.glob(os.path.join(args.folder, "*.csv")))
    if not csv_files:
        print(f"No se encontraron archivos .csv en {args.folder}")
        sys.exit(1)

    print(f"Encontrados {len(csv_files)} archivos CSV:")
    frames = []
    for f in csv_files:
        df = clean_and_load(f)
        if len(df) > 0:
            print(f"  {os.path.basename(f):30s}  ->  {len(df)} filas  "
                  f"(SF{df['sf'].iloc[0]}, {df['distance_m'].iloc[0]} m)")
            frames.append(df)
        else:
            print(f"  {os.path.basename(f):30s}  ->  VACIO / descartado")

    if not frames:
        print("No hay datos validos para unir.")
        sys.exit(1)

    # Unir y eliminar duplicados exactos
    merged = pd.concat(frames, ignore_index=True)
    merged.drop_duplicates(inplace=True)

    # Recalcular PDR real
    merged = recalculate_pdr(merged)

    # Ordenar: SF, distancia, seq
    merged.sort_values(["sf", "distance_m", "seq"], inplace=True)
    merged.reset_index(drop=True, inplace=True)

    # Guardar
    merged.to_csv(args.output, index=False)

    print(f"\nResultado: {len(merged)} filas guardadas en {args.output}")
    print("\nResumen por grupo:")
    summary = merged.groupby(["sf", "distance_m"]).agg(
        pkts=("seq", "count"),
        pdr=("pdr_pct", "first"),
        rssi_mean=("rssi_dbm", "mean"),
        snr_mean=("snr_db", "mean")
    ).reset_index()
    print(summary.to_string(index=False))
    print(f"\nListo. Ejecuta:  python3 lora_analysis.py --input {args.output}")


if __name__ == "__main__":
    main()
