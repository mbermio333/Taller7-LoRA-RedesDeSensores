#!/usr/bin/env python3
"""
lora_serial.py – Captura datos CSV del nodo RX Heltec via puerto serie.

Uso:
  python3 lora_serial.py --port /dev/ttyUSB0 --sf 12 --distance 100
  python3 lora_serial.py --port /dev/ttyACM0 --sf 7 --distance 300 --output datos.csv

Flujo:
  1. Abre el puerto serie (115200 baud).
  2. Lee líneas que empiecen con "CSV,RX,...".
  3. Les antepone sf y distancia, y las guarda en el CSV acumulativo.
  4. Termina al recibir la línea "DONE,RX,..." o al llegar al timeout.

Cada ejecución agrega filas al CSV; así acumulas todas las mediciones
(SF7/9/12 × distancias) en un solo archivo para lora_analysis.py.

Requiere: pip install pyserial
"""

import argparse
import csv
import os
import sys
import time

try:
    import serial
except ImportError:
    print("Instala pyserial:  pip install pyserial")
    sys.exit(1)

CSV_HEADER = ["sf", "distance_m", "seq", "temp_c", "rssi_dbm", "snr_db", "pdr_pct", "bat_pct"]


def main():
    parser = argparse.ArgumentParser(description="Captura serial LoRa P2P → CSV")
    parser.add_argument("--port", required=True, help="Puerto serie, ej: /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--sf", type=int, required=True, choices=[7, 9, 12],
                        help="Spreading Factor configurado en ambos nodos")
    parser.add_argument("--distance", type=int, required=True,
                        help="Distancia TX-RX en metros")
    parser.add_argument("--output", default="lora_data.csv",
                        help="Archivo CSV acumulativo (default: lora_data.csv)")
    parser.add_argument("--timeout", type=int, default=90,
                        help="Timeout total en segundos (default: 90)")
    args = parser.parse_args()

    # Verificar si el CSV ya existe (para no repetir encabezado)
    file_exists = os.path.isfile(args.output) and os.path.getsize(args.output) > 0

    ser = serial.Serial(args.port, args.baud, timeout=1)
    time.sleep(2)  # esperar que el Heltec reinicie tras abrir el puerto

    print(f"Escuchando {args.port} | SF{args.sf} | {args.distance} m")
    print(f"Guardando en {args.output}  (Ctrl+C para detener)")
    print("-" * 60)

    count = 0
    t_start = time.time()

    with open(args.output, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(CSV_HEADER)

        try:
            while True:
                if time.time() - t_start > args.timeout:
                    print(f"\nTimeout ({args.timeout} s) alcanzado.")
                    break

                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()

                # Mostrar todo en consola (debug)
                if line:
                    print(line)

                # Capturar datos RX
                if line.startswith("CSV,RX,"):
                    parts = line.split(",")
                    # CSV,RX,seq,temp,rssi,snr,pdr,bat
                    if len(parts) == 8:
                        row = [
                            args.sf,
                            args.distance,
                            parts[2],   # seq
                            parts[3],   # temp
                            parts[4],   # rssi
                            parts[5],   # snr
                            parts[6],   # pdr
                            parts[7],   # bat
                        ]
                        writer.writerow(row)
                        f.flush()
                        count += 1

                # Fin de rafaga detectado por el RX
                if line.startswith("DONE,RX,"):
                    print(f"\nRafaga completada. {count} paquetes capturados.")
                    break

        except KeyboardInterrupt:
            print(f"\nDetenido por usuario. {count} paquetes capturados.")

    ser.close()
    print(f"Datos guardados en {args.output}")


if __name__ == "__main__":
    main()
