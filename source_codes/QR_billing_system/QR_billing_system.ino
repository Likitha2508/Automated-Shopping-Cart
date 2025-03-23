#include <LiquidCrystal.h>

const int rs = 12, en = 11, d4 = 5, d5 = 4, d6 = 3, d7 = 2, ct = 9;
LiquidCrystal mylcd(rs, en, d4, d5, d6, d7);

String line1 = "";  // Variables to hold the incoming display lines
String line2 = "";
String line3 = "";
String line4 = "";

void setup() {
  analogWrite(ct, 50);
  mylcd.begin(20, 4);  // Initialize 20x4 LCD
  Serial.begin(115200);  // Start serial communication
  mylcd.print("Waiting for data...");  // Display initial message
}

void loop() {
  if (Serial.available() > 0) {
    line1 = Serial.readStringUntil('\n');  // Receive line for recent scan 1
    line2 = Serial.readStringUntil('\n');  // Receive line for recent scan 2
    line3 = Serial.readStringUntil('\n');  // Receive line for recent scan 3
    line4 = Serial.readStringUntil('\n');  // Receive line for total price

    // Clear LCD and display received lines
    mylcd.clear();
    mylcd.setCursor(0, 0);
    mylcd.print(line1);
    mylcd.setCursor(0, 1);
    mylcd.print(line2);
    mylcd.setCursor(0, 2);
    mylcd.print(line3);
    mylcd.setCursor(0, 3);
    mylcd.print(line4);
  }
}
