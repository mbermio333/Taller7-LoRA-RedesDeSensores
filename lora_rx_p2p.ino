/*
 * Taller 10 - Redes de Sensores LoRa (P2P)
 * Nodo RECEPTOR (RX) - Heltec WiFi LoRa 32 V3 (SX1262)
 *
 * Recepcion continua. Detecta fin de rafaga tras 10 s sin paquetes.
 * Salida CSV para captura con lora_serial.py:
 *   CSV,RX,seq,temp,rssi,snr,pdr,bat%
 * Al finalizar la rafaga imprime:  DONE,RX,recibidos,esperados,pdr
 *
 * Para nueva medicion: pulsar RST en la placa.
 */

#include "LoRaWan_APP.h"
#include "HT_SSD1306Wire.h"

// Acceso al driver SX126x para forzar LDRO desde el sketch
extern "C" {
  #include "driver/sx126x.h"
  extern SX126x_t SX126x;
  uint32_t BoardGetBatteryVoltage(void);   // en liblorawan.a, retorna mV
}

// -------- Parametros LoRa (identicos al TX) --------
#define RF_FREQUENCY            915900000
#define LORA_BANDWIDTH          2
#define LORA_SPREADING_FACTOR   12   // <-- igual que TX (7, 9 o 12)
#define LORA_CODINGRATE         4
#define LORA_PREAMBLE_LENGTH    8
#define LORA_SYMBOL_TIMEOUT     0
#define LORA_FIX_LENGTH_PAYLOAD_ON  false
#define LORA_IQ_INVERSION_ON    false

#define PAYLOAD_SIZE            5
#define NODE_ID                 0xA1        // debe ser igual al TX
#define BURST_TIMEOUT_MS        10000

static RadioEvents_t RadioEvents;
static SSD1306Wire display(0x3c, 500000, SDA_OLED, SCL_OLED, GEOMETRY_128_64, RST_OLED);

// Estado rafaga
bool     firstPkt    = true;
bool     burstDone   = false;
uint16_t firstSeq    = 0;
uint16_t lastSeq     = 0;
uint32_t received    = 0;
unsigned long lastRxTime = 0;

// Ultimo paquete
float   lastTemp = 0;
int16_t lastRssi = 0;
int8_t  lastSnr  = 0;

void VextON() { pinMode(Vext, OUTPUT); digitalWrite(Vext, LOW); }

int batteryPercent() {
  uint32_t mv = BoardGetBatteryVoltage();
  return constrain(map((int)mv, 3000, 4200, 0, 100), 0, 100);
}

void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr) {
  // Filtrar: tamaño correcto Y nuestro ID de grupo
  if (size != PAYLOAD_SIZE || payload[0] != NODE_ID) { Radio.Rx(0); return; }

  lastRxTime = millis();

  uint16_t seq       = payload[1] | ((uint16_t)payload[2] << 8);
  int16_t  tempCenti = payload[3] | ((int16_t)payload[4] << 8);
  lastTemp = tempCenti / 100.0;
  lastRssi = rssi;
  lastSnr  = snr;

  if (firstPkt) { firstSeq = seq; firstPkt = false; }
  lastSeq = seq;
  received++;

  uint32_t expected = (uint32_t)(lastSeq - firstSeq) + 1;
  float pdr = expected ? (100.0 * received / expected) : 0.0;
  int batPct = batteryPercent();

  // CSV a Serial
  Serial.printf("CSV,RX,%u,%.2f,%d,%d,%.1f,%d\n",
                seq, lastTemp, rssi, snr, pdr, batPct);

  // OLED
  display.clear();
  display.drawString(0,  0, "RX SF" + String(LORA_SPREADING_FACTOR) +
                            "  Bat:" + String(batPct) + "%");
  display.drawString(0, 14, "T:" + String(lastTemp, 2) + "C  Seq:" + String(seq));
  display.drawString(0, 28, "RSSI:" + String(rssi) + " SNR:" + String(snr));
  display.drawString(0, 42, "PDR:" + String(pdr, 1) + "% (" +
                            String(received) + "/" + String(expected) + ")");
  display.display();

  Radio.Rx(0);   // vuelve a recepcion continua
}

void setup() {
  Serial.begin(115200);

  VextON(); delay(100);
  display.init();
  display.setFont(ArialMT_Plain_10);
  display.drawString(0, 0, "RX LoRa P2P esperando...");
  display.display();

  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);

  RadioEvents.RxDone = OnRxDone;
  Radio.Init(&RadioEvents);
  Radio.SetChannel(RF_FREQUENCY);
  Radio.SetRxConfig(MODEM_LORA, LORA_BANDWIDTH, LORA_SPREADING_FACTOR,
                    LORA_CODINGRATE, 0, LORA_PREAMBLE_LENGTH,
                    LORA_SYMBOL_TIMEOUT, LORA_FIX_LENGTH_PAYLOAD_ON,
                    0, true, 0, 0, LORA_IQ_INVERSION_ON, true);

  // Forzar LDRO para SF12 a BW=500 kHz (requisito Taller 10)
  #if LORA_SPREADING_FACTOR == 12
    SX126x.ModulationParams.Params.LoRa.LowDatarateOptimize = 0x01;
    SX126xSetModulationParams(&SX126x.ModulationParams);
    Serial.println("# LDRO forzado ON para SF12 @ BW500");
  #endif

  Radio.Rx(0);

  Serial.println("# RX LoRa P2P | SF" + String(LORA_SPREADING_FACTOR) +
                 " BW500 CR4/8 | esperando paquetes...");
}

void loop() {
  Radio.IrqProcess();

  // Detectar fin de rafaga (10 s sin recibir)
  if (!burstDone && received > 0 && (millis() - lastRxTime > BURST_TIMEOUT_MS)) {
    burstDone = true;
    uint32_t expected = (uint32_t)(lastSeq - firstSeq) + 1;
    float pdr = 100.0 * received / expected;

    Serial.printf("DONE,RX,%lu,%lu,%.1f\n",
                  (unsigned long)received, (unsigned long)expected, pdr);

    display.clear();
    display.drawString(0,  0, "RAFAGA COMPLETADA");
    display.drawString(0, 14, "Recibidos: " + String(received) + "/" + String(expected));
    display.drawString(0, 28, "PDR final: " + String(pdr, 1) + " %");
    display.drawString(0, 42, "Pulsar RST para nueva");
    display.display();
  }
}
