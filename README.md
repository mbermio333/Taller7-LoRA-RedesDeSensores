# Taller 10 — Redes de Sensores LoRa P2P

Caracterización de un enlace LoRa punto a punto (P2P) entre dos nodos **Heltec WiFi LoRa 32 V3** (SX1262), evaluando el impacto del Spreading Factor sobre RSSI, SNR y PDR a distintas distancias.

> Universidad de Cuenca — Facultad de Ingeniería — Redes Inalámbricas de Sensores

## Configuración del enlace

| Parámetro | Valor |
|-----------|-------|
| Frecuencia | 915.9 MHz (Canal 1) |
| Ancho de banda | 500 kHz |
| Coding Rate | 4/8 |
| Spreading Factor | 7 / 9 / 12 (barrido) |
| Potencia Tx | 10 dBm |
| Payload | 5 bytes (binario optimizado) |
| LDRO | Forzado ON para SF12 |

## Estructura del repositorio

```
├── lora_tx_p2p/
│   └── lora_tx_p2p.ino      # Nodo transmisor (30 paquetes por ráfaga)
├── lora_rx_p2p/
│   └── lora_rx_p2p.ino      # Nodo receptor (CSV por serial + detección de fin de ráfaga)
├── lora_serial.py            # Captura datos del RX vía puerto serie → CSV
├── lora_merge.py             # Une múltiples CSV en un archivo limpio con PDR recalculado
├── lora_analysis.py          # Genera gráficas de caracterización + estimación de batería
└── README.md
```

## Requisitos

**Hardware:** 2× Heltec WiFi LoRa 32 V3 con antenas 915 MHz

**Software Arduino:**
- Board: `Heltec ESP32 Dev-Boards` (URL: `https://resource.heltec.cn/download/package_heltec_esp32_index.json`)
- Placa seleccionada: *WiFi LoRa 32(V3)*

**Python 3:**
```bash
pip install pyserial pandas matplotlib seaborn numpy
```

## Uso

### 1. Flashear los nodos

Abrir `lora_tx_p2p.ino` y `lora_rx_p2p.ino` en Arduino IDE. Ajustar `LORA_SPREADING_FACTOR` al mismo valor en ambos (7, 9 o 12). Compilar y subir cada sketch a su nodo.

### 2. Capturar datos

Conectar el nodo RX al PC por USB y ejecutar:

```bash
python3 lora_serial.py --port /dev/ttyUSB0 --sf 12 --distance 100
```

Encender el TX. El script captura los 30 paquetes y los guarda en `lora_data.csv`.

### 3. Unir mediciones

Si se generaron CSV separados por SF/distancia:

```bash
python3 lora_merge.py --folder ./mediciones --output lora_data.csv
```

### 4. Generar gráficas

```bash
python3 lora_analysis.py --input lora_data.csv
```

Genera: `rssi_vs_distancia.png`, `snr_vs_distancia.png`, `pdr_vs_distancia.png`, `heatmap_rssi.png`, `battery_estimation.png`.

Para solo la estimación de batería (sin datos de campo):

```bash
python3 lora_analysis.py --battery-only
```

## Autores

- Miguel Mateo Bermeo Montero — mateo.bermeo@ucuenca.edu.ec
- Pablo Andrés Calle González — pablo.calle1404@ucuenca.edu.ec
