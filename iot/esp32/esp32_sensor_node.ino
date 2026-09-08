/*
 * Sustainable Agriculture — ESP32 Sensor Node
 * ------------------------------------------------------------
 * Reads BUDGET sensors and POSTs readings to the backend every INTERVAL.
 *
 * Sensors (see README "Budget-friendly sensor shopping list"):
 *   - Capacitive Soil Moisture Sensor v1.2  -> GPIO 34 (analog)
 *   - DHT22 (or DHT11) Temp + Humidity       -> GPIO 4  (digital)
 *   - HC-SR04 Ultrasonic (water tank level)  -> TRIG 5 / ECHO 18
 *
 * Board: any ESP32 dev board (e.g. ESP32 DevKit v1, ~₹350-450).
 *
 * Libraries (install via Arduino Library Manager):
 *   - "DHT sensor library" by Adafruit
 *   - "Adafruit Unified Sensor"
 *   - ArduinoJson (v6+)
 *
 * Fill in WIFI_SSID, WIFI_PASS, and SERVER_URL below.
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "DHT.h"

// ---------------- CONFIG — EDIT THESE ----------------
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
// Use your computer's LAN IP where the backend runs, e.g. http://192.168.1.50:8000
const char* SERVER_URL = "http://192.168.1.50:8000/api/iot/sensor-data";
const char* DEVICE_ID  = "ESP32-001";
const unsigned long INTERVAL_MS = 30000;  // send every 30 seconds
// -----------------------------------------------------

// ---- Pins ----
#define SOIL_PIN   34      // capacitive soil moisture (analog)
#define DHT_PIN    4       // DHT22 data
#define DHT_TYPE   DHT22   // change to DHT11 if using DHT11
#define TRIG_PIN   5       // HC-SR04 trigger
#define ECHO_PIN   18      // HC-SR04 echo

// Calibrate these for YOUR soil sensor (read raw values in air vs. water):
const int SOIL_DRY_RAW = 3200;   // reading in dry air
const int SOIL_WET_RAW = 1300;   // reading fully in water

// Water tank geometry for level % (cm). Adjust to your tank.
const float TANK_EMPTY_CM = 30.0; // distance when tank empty
const float TANK_FULL_CM  = 5.0;  // distance when tank full

DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  dht.begin();
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();

  float soil = readSoilMoisture();
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();
  float water = readWaterLevel();

  if (isnan(temp)) temp = 0;
  if (isnan(hum))  hum = 0;

  Serial.printf("soil=%.1f%% temp=%.1fC hum=%.1f%% water=%.1f%%\n",
                soil, temp, hum, water);

  sendReading(soil, temp, hum, water);
  delay(INTERVAL_MS);
}

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 40) {
    delay(500); Serial.print("."); tries++;
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? " connected!" : " FAILED");
}

float readSoilMoisture() {
  int raw = analogRead(SOIL_PIN);
  // Map raw -> 0..100% (higher moisture = lower raw for capacitive sensors)
  float pct = 100.0 * (SOIL_DRY_RAW - raw) / (float)(SOIL_DRY_RAW - SOIL_WET_RAW);
  if (pct < 0) pct = 0; if (pct > 100) pct = 100;
  return pct;
}

float readWaterLevel() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // timeout 30ms
  if (duration == 0) return 0;
  float distance_cm = duration * 0.0343 / 2.0;
  float pct = 100.0 * (TANK_EMPTY_CM - distance_cm) / (TANK_EMPTY_CM - TANK_FULL_CM);
  if (pct < 0) pct = 0; if (pct > 100) pct = 100;
  return pct;
}

void sendReading(float soil, float temp, float hum, float water) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<256> doc;
  doc["device_id"]     = DEVICE_ID;
  doc["soil_moisture"] = soil;
  doc["temperature"]   = temp;
  doc["humidity"]      = hum;
  doc["water_level"]   = water;
  doc["water_flow"]    = 0;

  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  Serial.printf("POST -> HTTP %d\n", code);
  http.end();
}
