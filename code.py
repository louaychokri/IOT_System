import machine
from machine import Pin, SoftI2C, ADC, PWM
from i2c_lcd import I2cLcd  
import time
import dht
import network
import urequests
import ujson
import os
import socket
import _thread
from time import ticks_ms, ticks_diff

class IoTSystem:
    def __init__(self):
        # I2C LCD Configuration
        self.I2C_ADDR = 0x27
        self.I2C_NUM_ROWS = 4
        self.I2C_NUM_COLS = 20
        self.i2c = SoftI2C(scl=Pin(17), sda=Pin(16), freq=400000) 
        try:
            self.lcd = I2cLcd(self.i2c, self.I2C_ADDR, self.I2C_NUM_ROWS, self.I2C_NUM_COLS)
            print("LCD initialized successfully!")
        except Exception as e:
            print("Error initializing LCD:", e)
            self.lcd = None

        # Wi-Fi Configuration
        self.WIFI_SSID = "louay"
        self.WIFI_PASSWORD = "20062002louay"
        self.wlan = None

        # Keypad Configuration
        self.keys = [
            ['1', '2', '3', 'A'],
            ['4', '5', '6', 'B'],
            ['7', '8', '9', 'C'],
            ['*', '0', '#', 'D']
        ]
        self.rows = [Pin(32, Pin.OUT), Pin(33, Pin.OUT), Pin(25, Pin.OUT), Pin(26, Pin.OUT)]
        self.cols = [Pin(27, Pin.IN, Pin.PULL_UP), Pin(14, Pin.IN, Pin.PULL_UP), Pin(12, Pin.IN, Pin.PULL_UP), Pin(13, Pin.IN, Pin.PULL_UP)]

        # Sensor Configurations
        self.adc = ADC(Pin(34))  
        self.adc.atten(ADC.ATTN_11DB) 
        self.VOLTAGE_DIVIDER_RATIO = 5.0  
        self.MAX_ADC_VALUE = 4095  
        self.dht_sensor = dht.DHT22(machine.Pin(23))
        self.s0 = Pin(5, Pin.OUT)
        self.s1 = Pin(18, Pin.OUT)
        self.s2 = Pin(19, Pin.OUT)
        self.mux_adc = ADC(Pin(35))
        self.mux_adc.atten(ADC.ATTN_11DB)

        self.buzzer = PWM(Pin(15), freq=1000, duty=0)
        self.green_led = Pin(21, Pin.OUT)
        self.yellow_led = Pin(4, Pin.OUT)
        self.red_led = Pin(2, Pin.OUT)

        self.system_active = False
        self.button_marche = Pin(22, Pin.IN, Pin.PULL_UP)
        self.last_button_check_time = 0  

        self.temp = None
        self.hum = None
        self.voltage = None
        self.mq5_adc = None
        self.ky026_adc = None
        self.sw420_adc = None
        self.fc51_adc = None
        self.float_level_adc = None
        self.mq5 = None
        self.ky026 = None
        self.sw420 = None
        self.fc51 = None
        self.float_level = None
        
        # Limits
        try:
            with open('limits.json', 'r') as f:
                self.limits = ujson.load(f)
                print('Limits loaded:', self.limits)
        except:
            self.limits = {
                'temp': 35,     
                'hum': 101,     
                'volt': 35,  
                'gas': 1,     
                'flame': 1,   
                'vibr': 1,    
                'obst': 1,    
                'level': 1   
            }
            print('Using default limits:', self.limits)

        self.last_sensor_read = ticks_ms()
        self.last_data_send = ticks_ms()
        self.sensor_interval = 5000  
        self.data_interval = 60000  

        self.menu_displayed = False

        self.leds_off()

    def check_button(self):
        current_time = ticks_ms()
        if ticks_diff(current_time, self.last_button_check_time) > 50:  
            button_state = self.button_marche.value()  
            new_system_active = (button_state == 0)  
            
            if new_system_active != self.system_active: 
                self.system_active = new_system_active
                if self.system_active:
                    self.lcd.clear()
                    self.lcd.move_to(3, 1)
                    self.lcd.putstr("WELCOME TO THE ")
                    self.lcd.move_to(4, 2)
                    self.lcd.putstr("IOT SYSTEM ")
                    time.sleep(0.1)
                    self.wlan = self.connect_wifi()
                    if self.wlan and self.wlan.isconnected():
                        self.lcd.clear()
                        self.lcd.move_to(0, 1)
                        self.lcd.putstr("Wi-Fi CONNECTED")
                        time.sleep(0.1)
                    else:
                        self.lcd.clear()
                        self.lcd.move_to(0, 1)
                        self.lcd.putstr("Wi-Fi Failed")
                        time.sleep(0.1)
                        self.system_active = False
                else:
                    if self.wlan and self.wlan.isconnected():
                        self.wlan.disconnect()
                        self.wlan = None
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("System Stopped")
                    time.sleep(0.5)
                    self.menu_displayed = False
                    self.leds_off()
                    print("System Stopped")
            
            self.last_button_check_time = current_time

    def connect_wifi(self):
        sta_if = network.WLAN(network.STA_IF)
        sta_if.active(True)
        if not sta_if.isconnected():
            print("Connecting to Wi-Fi...")
            sta_if.connect(self.WIFI_SSID, self.WIFI_PASSWORD)
            for _ in range(15):  
                if sta_if.isconnected():
                    break
                time.sleep(2)
        if sta_if.isconnected():
            print("Wi-Fi connected successfully")
            print("Network config:", sta_if.ifconfig())
            return sta_if 
        else:
            print("Failed to connect to Wi-Fi")
            return None

    def read_keypad(self):
        for i, row in enumerate(self.rows):
            row.value(0) 
            for j, col in enumerate(self.cols):
                if col.value() == 0:  
                    time.sleep(0.1)
                    if col.value() == 0: 
                        row.value(1)
                        print("Key pressed:", self.keys[i][j])
                        return self.keys[i][j]  
            row.value(1)  
        return None

    def read_voltage(self):
        adc_value = self.adc.read()
        voltage_at_adc = (adc_value / self.MAX_ADC_VALUE) * 3.3
        input_voltage = voltage_at_adc * self.VOLTAGE_DIVIDER_RATIO
        return input_voltage

    def read_dht22(self):
        self.dht_sensor.measure()
        temp = self.dht_sensor.temperature()
        hum = self.dht_sensor.humidity()
        return temp, hum

    def select_channel(self, channel):
        self.s0.value(channel & 1)
        self.s1.value((channel >> 1) & 1)
        self.s2.value((channel >> 2) & 1)
        time.sleep(0.1)  

    def read_digital_channel(self, channel, threshold):
        self.select_channel(channel)
        self.mux_adc.read()  
        values = []
        for _ in range(5):
            values.append(self.mux_adc.read())
            time.sleep(0.01)
        value = sum(values) / len(values)
        digital = 1 if value >= threshold else 0
        return value, digital
    
    def read_digital_channel_2(self, channel, threshold):
        self.select_channel(channel)
        self.mux_adc.read()  
        values = []
        for _ in range(5):
            values.append(self.mux_adc.read())
            time.sleep(0.01)
        value = sum(values) / len(values)
        digital = 1 if value <= threshold else 0
        return value, digital

    def read_all_sensors(self):
        self.temp, self.hum = self.read_dht22()
        self.voltage = self.read_voltage() 
        self.mq5_adc, self.mq5 = self.read_digital_channel(0, 700)
        self.ky026_adc, self.ky026 = self.read_digital_channel_2(1, 2000) 
        self.fc51_adc, self.fc51 = self.read_digital_channel_2(3, 2000)
        self.sw420_adc, self.sw420 = self.read_digital_channel(2, 700)
        self.float_level_adc, self.float_level = self.read_digital_channel(4, 100)
        
        print("Sensor Readings:")
        print(f"Temp: {self.temp if self.temp is not None else 'N/A'}C")
        print(f"Hum: {self.hum if self.hum is not None else 'N/A'}%")
        print(f"Voltage: {self.voltage:.2f}V")
        print(f"Gas: ADC={self.mq5_adc:.1f}, Status={self.mq5}")
        print(f"Flame: ADC={self.ky026_adc:.1f}, Status={self.ky026}")
        print(f"Vibration: ADC={self.sw420_adc:.1f}, Digital={self.sw420}")
        print(f"Obstacle: ADC={self.fc51_adc:.1f}, Digital={self.fc51}")
        print(f"Float Level: ADC={self.float_level_adc:.1f}, Digital={self.float_level}")
        
        return self.temp, self.hum, self.voltage, self.mq5, self.ky026, self.sw420, self.fc51, self.float_level

    def send_to_thingspeak(self):
        try:
            THINGSPEAK_API_KEY = "1R1O0NY81HUYUUU4"
            THINGSPEAK_URL = "https://api.thingspeak.com/update"
            if self.temp is None or self.hum is None:
                print("Invalid sensor data. Skipping upload.")
                return
            payload = {
                "api_key": THINGSPEAK_API_KEY,
                "field1": self.temp,
                "field2": self.hum,
                "field3": self.voltage,
                "field4": self.mq5,
                "field5": self.ky026,
                "field6": self.fc51,
                "field7": self.sw420,
                "field8": self.float_level,
            }
            response = urequests.post(THINGSPEAK_URL, json=payload)
            print("ThingSpeak Response:", response.text)
            response.close()
        except Exception as e:
            print("Error sending data to ThingSpeak:", e)

    def receive_from_thingspeak(self, start_date=None, end_date=None):
        if not self.system_active:
            return
        CHANNEL_ID = "2916723"
        READ_API_KEY = "MQT9LRAF2A0R5YYF"
        THINGSPEAK_URL = f"https://api.thingspeak.com/channels/{CHANNEL_ID}/feeds.csv?api_key={READ_API_KEY}"
        if start_date and end_date:
            start_date_formatted = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}%2000:00:00"
            end_date_formatted = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}%2023:59:59"
            THINGSPEAK_URL += f"&start={start_date_formatted}&end={end_date_formatted}"
            filename = f"{start_date}_{end_date}.csv"
        else:
            THINGSPEAK_URL += "&results=100"
            file_number = 1
            while True:
                filename = f"sensor_data_{file_number}.csv"
                try:
                    with open(filename, "r"):
                        file_number += 1
                except OSError:
                    break
        try:
            response = urequests.get(THINGSPEAK_URL)
            with open(filename, "w") as file:
                header = "Timestamp,temp,hum,voltage,gaz,flamme,obstacle,vibration,float level"
                file.write(header + "\n")
                response.raw.readline()  # Skip the header line
                while self.system_active:
                    line = response.raw.readline()
                    if not line:
                        break
                    line = line.decode('utf-8').strip()
                    if line:
                        parts = line.split(',')
                        if len(parts) >= 10:
                            timestamp = parts[0]
                            fields = parts[2:10]
                            row = [timestamp] + fields
                            file.write(','.join(row) + "\n")
                        else:
                            print(f"Warning: Line has {len(parts)} parts, expected 10")
                    self.check_button()
            if self.system_active:
                print(f"Data saved to {filename}")
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("DATA RECEIVED FILE ")
                self.lcd.move_to(0, 2)
                self.lcd.putstr(f"NAME: {filename}")
                time.sleep(0.1)
            else:
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("Operation Cancelled")
                time.sleep(1)
        except Exception as e:
            print("Error receiving data from ThingSpeak:", e)
            self.lcd.clear()
            self.lcd.move_to(0, 1)
            self.lcd.putstr("ERROR RECEIVING DATA")
            time.sleep(1)
        finally:
            response.close()

    def read_date(self, message):
        if not self.system_active:
            return None
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("* DEL   # CONFIRM")
        self.lcd.move_to(0, 1)
        self.lcd.putstr(f"FORM: AAAA/MM/JJ" )
        self.lcd.move_to(0, 2)
        self.lcd.putstr(f"{message} :" )
        
        date_str = ''
        i = 0  
        while self.system_active:
            key = self.read_keypad()
            if key and key.isdigit():
                if len(date_str) < 8:
                    date_str += key
                    self.lcd.move_to(i, 3)  
                    self.lcd.putstr(key)
                    i += 1             
            elif key == '*':
                if date_str:
                    date_str = date_str[:-1]  
                    i -= 1                    
                    self.lcd.move_to(i, 3)
                    self.lcd.putstr(' ')           
                    self.lcd.move_to(i, 3)         
            elif key == '#':
                if len(date_str) == 8:
                    break                     
                else:
                    self.lcd.move_to(0, 3)
                    self.lcd.putstr("INVALID DATE")
                    time.sleep(0.1)
                    self.lcd.move_to(0, 3)
                    self.lcd.putstr(' ' * 12)     
            time.sleep(0.1)
            self.check_button()
        if not self.system_active:
            return None
        return date_str

    def display_sensor_data(self):
        if self.lcd:
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr(f"TEMP:{self.temp}C")
            self.lcd.move_to(0, 1)
            self.lcd.putstr(f"HUM:{self.hum}%")
            self.lcd.move_to(0, 2)
            self.lcd.putstr(f"VOLTAGE:{self.voltage:.2f}V")
            self.lcd.move_to(0, 3)
            self.lcd.putstr(f"GAZ:{self.mq5}")
            time.sleep(2)
            if not self.system_active:
                return
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr(f"FLAME:{self.ky026}")
            self.lcd.move_to(0, 1)
            self.lcd.putstr(f"OBSTACLE:{self.fc51}")
            self.lcd.move_to(0, 2)
            self.lcd.putstr(f"VIBRATION:{self.sw420}")
            self.lcd.move_to(0, 3)
            self.lcd.putstr(f"LEVEL:{self.float_level}")
            time.sleep(2)
            self.lcd.clear()

    def display_sensor_limits(self):
        if self.lcd:
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr(f"TEMP: {self.limits['temp']}C")
            self.lcd.move_to(0, 1)
            self.lcd.putstr(f"HUM: {self.limits['hum']}%")
            self.lcd.move_to(0, 2)
            self.lcd.putstr(f"VOLT: {self.limits['volt']}V")
            self.lcd.move_to(0, 3)
            self.lcd.putstr(f"GAZ: {self.limits['gas']}")
            time.sleep(2)
            if not self.system_active:
                return
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr(f"FLAME: {self.limits['flame']}")
            self.lcd.move_to(0, 1)
            self.lcd.putstr(f"VIBR: {self.limits['vibr']}")
            self.lcd.move_to(0, 2)
            self.lcd.putstr(f"OBST: {self.limits['obst']}")
            self.lcd.move_to(0, 3)
            self.lcd.putstr(f"LEVEL: {self.limits['level']}")
            time.sleep(2)
            self.lcd.clear()

    def save_limits(self):
        with open('limits.json', 'w') as f:
            ujson.dump(self.limits, f)
            print('Limits saved:', self.limits)

    def read_number(self):
        if not self.system_active:
            return None
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("* DEL   # UPDATE  ")
        self.lcd.move_to(0, 1)
        self.lcd.putstr("SET LIMIT TO :")
        number = ''
        i = 0
        while self.system_active:
            key = self.read_keypad()
            if key and key.isdigit():
                if len(number) < 6:
                    number += key
                    self.lcd.move_to(i, 2)
                    self.lcd.putstr(key)
                    i += 1
            elif key == '*':
                if number:
                    number = number[:-1]  
                    i -= 1                    
                    self.lcd.move_to(i, 2)
                    self.lcd.putstr(' ')           
                    self.lcd.move_to(i, 2)   
            elif key == '#':
                break
            self.check_button()
        if not self.system_active:
            return None
        self.lcd.clear()
        return int(number) if number else 0

    def set_limits(self):
        if not self.system_active:
            return
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Select sensor:")
        self.lcd.move_to(0, 1)
        self.lcd.putstr("1:Temp 2:Hum 3:Volt")
        self.lcd.move_to(0, 2)
        self.lcd.putstr("4:Gas 5:Flame")
        self.lcd.move_to(0, 3)
        self.lcd.putstr("6:Vibr 7:Obst 8:Level")
        sensor_key = None
        while self.system_active and sensor_key not in ['1', '2', '3', '4', '5', '6', '7', '8']:
            sensor_key = self.read_keypad()
            time.sleep(0.01)
            self.check_button()
        if not self.system_active:
            return
        sensor_map = {'1': 'temp', '2': 'hum', '3': 'volt', '4': 'gas', '5': 'flame', '6': 'vibr', '7': 'obst', '8': 'level'}
        sensor = sensor_map[sensor_key] 
        limit = self.read_number()
        if limit is not None:
            self.limits[sensor] = limit
            self.save_limits()
            self.lcd.move_to(0,1)
            self.lcd.putstr(f"SET {sensor} LIMIT TO :")
            self.lcd.move_to(4,2)
            self.lcd.putstr(f"{limit}")
            print(f'Limit set for {sensor}: {limit}')
        

    def set_buzzer(self, level):
        if level == 0:
            self.buzzer.duty(0)
        elif level == 1: 
            self.buzzer.freq(500)
            self.buzzer.duty(256)
        elif level == 2:  
            self.buzzer.freq(1000)
            self.buzzer.duty(512)
        elif level == 3:  
            self.buzzer.freq(2000)
            self.buzzer.duty(768)

    def set_leds(self, green, yellow, red):
        self.green_led.value(green)
        self.yellow_led.value(yellow)
        self.red_led.value(red)

    def leds_off(self):
        self.set_leds(0, 0, 0)

    def check_limits_and_alert(self):
        simple_alert = False
        moderate_alert = False
        critical_alert = False

        if self.temp is not None and self.temp > self.limits['temp']:
            print("Alert: Temp high")
            simple_alert = True
        if self.hum is not None and self.hum > self.limits['hum']:
            print("Alert: Hum high")
            simple_alert = True
        if self.voltage > self.limits['volt']:
            print("Alert: Volt high")
            simple_alert = True
            
        if self.sw420 == self.limits['vibr']:
            print("Alert: Vibration detected")
            moderate_alert = True
        if self.fc51 == self.limits['obst']:
            print("Alert: Obstacle detected")
            moderate_alert = True
        if self.float_level == self.limits['level']:
            print("Alert: Level high")
            moderate_alert = True
        if self.mq5 == self.limits['gas']:
            print("Alert: Gas high")
            critical_alert = True
        if self.ky026 == self.limits['flame']:
            print("Alert: Flame detected")
            critical_alert = True

        green = 1 if simple_alert else 0
        yellow = 1 if moderate_alert else 0
        red = 1 if critical_alert else 0
        self.set_leds(green, yellow, red)

        # Set buzzer based on alert severity
        if critical_alert:
            self.set_buzzer(3)
        elif moderate_alert:
            self.set_buzzer(2)
        elif simple_alert:
            self.set_buzzer(1)
        else:
            self.set_buzzer(0)

        return simple_alert or moderate_alert or critical_alert

    def list_last_files(self, num=4):
        try:
            files = [f for f in os.listdir() if f.endswith('.csv')]
            files.sort(key=lambda x: os.stat(x)[7], reverse=True)
            print(files[:num])
            return files[:num]
        except Exception as e:
            print("Error listing files:", e)
            return []

    def send_file_to_pc(self, ip_address, filename):
        if not self.system_active:
            return
        addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
        s = socket.socket()
        s.bind(addr)
        s.listen(1)
        
        print(f"Sending {filename}, visit http://{ip_address}/")
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("SENDING FILE...")
        print("Sending File...")
        self.lcd.move_to(0, 1)
        self.lcd.putstr(filename[:17])
        self.lcd.move_to(0, 2)
        self.lcd.putstr(f"http://{ip_address}/")
        
        conn, addr = s.accept()
        print('Client connected from', addr)
        
        request = b""
        while self.system_active:
            part = conn.recv(1024)
            if not part or b"\r\n\r\n" in request + part:
                request += part
                break
            request += part
            self.check_button()
        
        if not self.system_active:
            conn.close()
            s.close()
            return
        
        try:
            file_size = os.stat(filename)[6]
            with open(filename, 'rb') as f:
                headers = (
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: text/csv\r\n"
                    f"Content-Disposition: attachment; filename=\"{filename}\"\r\n"
                    f"Content-Length: {file_size}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                )
                conn.sendall(headers.encode('utf-8'))
                
                while self.system_active:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    conn.sendall(chunk)
                    self.check_button()
            
            if self.system_active:
                time.sleep(1)
                os.remove(filename)
                print(f"Deleted {filename}")
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("FILE SENT & DELETED")
            else:
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("OPERATION CANCELLED")
        except OSError as e:
            print(f"Error during file operation: {e}")
            self.lcd.clear()
            self.lcd.move_to(0, 1)
            self.lcd.putstr("ERROR SENDING OR")
            self.lcd.move_to(0, 2)
            self.lcd.putstr("DELETING")
        finally:
            conn.close()
            s.close()
            time.sleep(2)

    def main_loop(self):
        while True:
            self.check_button()
            current_time = ticks_ms()
            if self.system_active and self.wlan and self.wlan.isconnected():
                if ticks_diff(current_time, self.last_sensor_read) >= self.sensor_interval:
                    self.read_all_sensors()
                    self.check_limits_and_alert()
                    self.last_sensor_read = current_time

                if ticks_diff(current_time, self.last_data_send) >= self.data_interval:
                    if self.temp is not None and self.hum is not None:
                        self.send_to_thingspeak()
                        print("Data sent to ThingSpeak at", ticks_ms())
                    self.last_data_send = current_time

                if not self.menu_displayed:
                    self.lcd.clear()
                    self.lcd.move_to(0, 0)
                    self.lcd.putstr("1: SET LIMIT")
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("2: RECEIVE DATA")
                    self.lcd.move_to(0, 2)
                    self.lcd.putstr("3: SENSORS OPTIONS")
                    self.lcd.move_to(0, 3)
                    self.lcd.putstr("4: SEND FILE")
                    self.menu_displayed = True

                key = self.read_keypad()
                if key:
                    self.menu_displayed = False
                    if key == '1':
                        self.set_limits()
                    elif key == '2':
                        start_date = self.read_date("START DATE")
                        if start_date and self.system_active:
                            end_date = self.read_date("END DATE")
                            if end_date and self.system_active:
                                self.lcd.clear()
                                self.lcd.move_to(0,1)
                                self.lcd.putstr('RECEIVING DATA...')
                                self.receive_from_thingspeak(start_date, end_date)
                    elif key == '3':
                        self.lcd.clear()
                        self.lcd.move_to(0, 0)
                        self.lcd.putstr("1: SENSORS DATA")
                        self.lcd.move_to(0, 1)
                        self.lcd.putstr("2: SENSORS LIMITS")
                        sub_key = None
                        while self.system_active and sub_key not in ['1', '2']:
                            sub_key = self.read_keypad()
                            time.sleep(0.01)
                            self.check_button()
                        if sub_key == '1' and self.system_active:
                            self.display_sensor_data()
                        elif sub_key == '2' and self.system_active:
                            self.display_sensor_limits()
                    elif key == '4':
                        files = self.list_last_files()
                        if not files:
                            self.lcd.clear()
                            self.lcd.move_to(0, 1)
                            self.lcd.putstr("No files found")
                            time.sleep(1)
                        else:
                            self.lcd.clear()
                            for i, file in enumerate(files):
                                self.lcd.move_to(0, i)
                                self.lcd.putstr(f"{i+1}:{file[:17]}")
                            selected = None
                            valid_options = ['1', '2', '3', '4'][:len(files)]
                            while self.system_active and selected not in valid_options:
                                selected = self.read_keypad()
                                time.sleep(0.01)
                                self.check_button()
                            if selected and self.system_active:
                                file_to_send = files[int(selected) - 1]
                                self.lcd.clear()
                                self.lcd.move_to(0, 1)
                                self.lcd.putstr("File selected:")
                                self.lcd.move_to(0, 2)
                                self.lcd.putstr(file_to_send[:20])
                                time.sleep(2)
                                self.send_file_to_pc(self.wlan.ifconfig()[0], file_to_send)
                                self.menu_displayed = False
            

if __name__ == "__main__":
    iot_system = IoTSystem()
    iot_system.main_loop()