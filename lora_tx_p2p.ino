/*
 * Taller 10 - Redes de Sensores LoRa (P2P)
 * Nodo TRANSMISOR (TX) - Heltec WiFi LoRa 32 V3 (SX1262)
 *
 * Envia exactamente NUM_PACKETS paquetes y se detiene.
 * Salida Serial en formato CSV para captura con lora_serial.py
 * Muestra porcentaje de bateria en OLED y Serial.
 *
 * Trama binaria optimizada: [seq:2B][temp_centi:2B] = 4 bytes
 */

#include "LoRaWan_APP.h"
#include "HT_SSD1306Wire.h"
#include <math.h>

// Acceso al driver SX126x para forzar LDRO desde el sketch
// (la libreria es precompilada, no se puede editar radio.c)
extern "C" {
  #include "driver/sx126x.h"
  extern SX126x_t SX126x;
  uint32_t BoardGetBatteryVoltage(void);   // en liblorawan.a, retorna mV
}

// -------- Parametros LoRa --------
#define RF_FREQUENCY            915900000   // Canal 1 = 915.9 MHz
#define TX_OUTPUT_POWER         10          // dBm
#define LORA_BANDWIDTH          2           // 2 = 500 kHz
#define LORA_SPREADING_FACTOR   12          // <-- cambiar: 7, 9 o 12
#define LORA_CODINGRATE         4           // 4 = CR 4/8 (max FEC)
#define LORA_PREAMBLE_LENGTH    8
#define LORA_SYMBOL_TIMEOUT     0
#define LORA_FIX_LENGTH_PAYLOAD_ON  false
#define LORA_IQ_INVERSION_ON    false

// -------- Control de prueba --------
#define TX_INTERVAL_MS          2000
#define NUM_PACKETS             30
#define PAYLOAD_SIZE            5           // 1B ID + 2B seq + 2B temp
#define NODE_ID                 0xA1        // identificador de grupo (cambiar si hay colision)

uint8_t txpacket[PAYLOAD_SIZE];
static RadioEvents_t RadioEvents;
static SSD1306Wire display(0x3c, 500000, SDA_OLED, SCL_OLED, GEOMETRY_128_64, RST_OLED);

uint16_t seq = 0;
bool loraIdle = true;
bool txDone   = false;
unsigned long lastTx = 0;

void VextON() { pinMode(Vext, OUTPUT); digitalWrite(Vext, LOW); }
void OnTxDone()    { loraIdle = true; }
void OnTxTimeout() { Radio.Sleep(); loraIdle = true; }

int batteryPercent() {
  uint32_t mv = BoardGetBatteryVoltage();
  return constrain(map((int)mv, 3000, 4200, 0, 100), 0, 100);
}

void setup() {
  Serial.begin(115200);
  randomSeed(micros());

  VextON(); delay(100);
  display.init();
  display.setFont(ArialMT_Plain_10);

  Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);

  RadioEvents.TxDone    = OnTxDone;
  RadioEvents.TxTimeout = OnTxTimeout;
  Radio.Init(&RadioEvents);
  Radio.SetChannel(RF_FREQUENCY);
  Radio.SetTxConfig(MODEM_LORA, TX_OUTPUT_POWER, 0, LORA_BANDWIDTH,
                    LORA_SPREADING_FACTOR, LORA_CODINGRATE,
                    LORA_PREAMBLE_LENGTH, LORA_FIX_LENGTH_PAYLOAD_ON,
                    true, 0, 0, LORA_IQ_INVERSION_ON, 3000);

  // Forzar LDRO para SF12 a BW=500 kHz (requisito Taller 10)
  // A 500 kHz el tiempo de simbolo es 8.19 ms < 16.38 ms,
  // el driver no lo activa automaticamente, asi que lo forzamos.
  #if LORA_SPREADING_FACTOR == 12
    SX126x.ModulationParams.Params.LoRa.LowDatarateOptimize = 0x01;
    SX126xSetModulationParams(&SX126x.ModulationParams);
    Serial.println("# LDRO forzado ON para SF12 @ BW500");
  #endif

  Serial.println("# TX LoRa P2P | SF" + String(LORA_SPREADING_FACTOR) +
                 " BW500 CR4/8 | " + String(NUM_PACKETS) + " paquetes");
}

void loop() {
  if (!txDone && loraIdle && seq < NUM_PACKETS &&
      (millis() - lastTx >= TX_INTERVAL_MS)) {
    lastTx = millis();

    float tempC = 15.0 + random(0, 2100) / 100.0;
    int16_t tempCenti = (int16_t) lround(tempC * 100.0);
    int batPct = batteryPercent();

    // Empaquetado binario little-endian (5 bytes: ID + seq + temp)
    txpacket[0] =  NODE_ID;
    txpacket[1] =  seq        & 0xFF;
    txpacket[2] = (seq >> 8)  & 0xFF;
    txpacket[3] =  tempCenti  & 0xFF;
    txpacket[4] = (tempCenti >> 8) & 0xFF;

    // CSV a Serial:  CSV,TX,seq,temp,bat%
    Serial.printf("CSV,TX,%u,%.2f,%d\n", seq, tempC, batPct);

    // OLED
    display.clear();
    display.drawString(0,  0, "TX SF" + String(LORA_SPREADING_FACTOR) +
                              " CR4/8  Bat:" + String(batPct) + "%");
    display.drawString(0, 14, "Temp: " + String(tempC, 2) + " C");
    display.drawString(0, 28, "Pkt: " + String(seq + 1) + "/" + String(NUM_PACKETS));
    display.drawString(0, 42, "915.9 MHz  BW500");
    display.display();

    Radio.Send(txpacket, PAYLOAD_SIZE);
    loraIdle = false;
    seq++;
  }

  // Transmision completada
  if (!txDone && seq >= NUM_PACKETS && loraIdle) {
    txDone = true;
    Radio.Sleep();
    Serial.println("DONE,TX," + String(NUM_PACKETS));

    display.clear();
    display.drawString(0,  0, "TX COMPLETADO");
    display.drawString(0, 14, String(NUM_PACKETS) + " paquetes enviados");
    display.drawString(0, 28, "SF" + String(LORA_SPREADING_FACTOR) + " CR4/8 BW500");
    display.drawString(0, 42, "Bat: " + String(batteryPercent()) + " %");
    display.display();
  }

  Radio.IrqProcess();
}
