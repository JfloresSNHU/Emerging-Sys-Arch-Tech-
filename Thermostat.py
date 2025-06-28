#
# Thermostat.py
#   - Three states (off, heat, cool)
#   - LEDs indicate state & temp vs. setpoint
#   - Buttons cycle state / raise / lower setpoint
#   - 16×2 LCD shows date/time + alternating status
#   - Serial port sends CSV status every 30s
#

from time       import sleep
from datetime   import datetime
from statemachine import StateMachine, State
import board
import adafruit_ahtx0
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd
import serial
from gpiozero  import Button, PWMLED
from threading import Thread, Lock
from math      import floor

DEBUG = True

# A global lock to serialize all I2C sensor accesses:
sensor_lock = Lock()

# I2C & sensor
i2c      = board.I2C()
thSensor = adafruit_ahtx0.AHTx0(i2c)

# Serial port
ser = serial.Serial(
    port='/dev/ttyS0',
    baudrate=115200,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# LEDs
redLight  = PWMLED(18)
blueLight = PWMLED(23)

class ManagedDisplay:
    def __init__(self):
        # LCD pin mapping
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)

        self.lcd_columns = 16
        self.lcd_rows    = 2

        self.lcd = characterlcd.Character_LCD_Mono(
            self.lcd_rs, self.lcd_en,
            self.lcd_d4, self.lcd_d5,
            self.lcd_d6, self.lcd_d7,
            self.lcd_columns, self.lcd_rows
        )
        self.lcd.clear()

    def clear(self):
        self.lcd.clear()

    def cleanupDisplay(self):
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()

    def updateScreen(self, message: str):
        # message must be "line1\nline2"
        self.lcd.clear()
        self.lcd.message = message

screen = ManagedDisplay()

class TemperatureMachine(StateMachine):
    """A state machine managing off/heat/cool thermostat logic."""

    off  = State(initial=True)
    heat = State()
    cool = State()

    # Default setpoint
    setPoint = 72

    # State‐cycle event
    cycle = off.to(heat) | heat.to(cool) | cool.to(off)

    def __init__(self):
        super().__init__()
        self.endDisplay = False    # <— ensure this exists before thread starts
        if DEBUG:
            print("TemperatureMachine initialized")

    # State entry/exit hooks
    def on_enter_heat(self):
        if DEBUG: print("* ENTER HEAT")
        self.updateLights()

    def on_exit_heat(self):
        redLight.off()
        if DEBUG: print("* EXIT HEAT: redLight OFF")

    def on_enter_cool(self):
        if DEBUG: print("* ENTER COOL")
        self.updateLights()

    def on_exit_cool(self):
        blueLight.off()
        if DEBUG: print("* EXIT COOL: blueLight OFF")

    def on_enter_off(self):
        if DEBUG: print("* ENTER OFF")
        self.updateLights()

    # Button‐driven callbacks
    def processTempStateButton(self):
        if DEBUG: print("Button: Cycle State")
        self.cycle()
        self.updateLights()

    def processTempIncButton(self):
        if DEBUG: print("Button: Increase SetPoint")
        self.setPoint += 1
        self.updateLights()

    def processTempDecButton(self):
        if DEBUG: print("Button: Decrease SetPoint")
        self.setPoint -= 1
        self.updateLights()

    # Centralized LED logic
    def updateLights(self):
        temp = floor(self.getFahrenheit())
        redLight.off()
        blueLight.off()

        if DEBUG:
            print(f"  State: {self.current_state.id}")
            print(f"  Temp:  {temp}°F")
            print(f"  SetPt: {self.setPoint}°F")

        if self.current_state.id == 'heat':
            if temp < self.setPoint:
                redLight.pulse(fade_in_time=1, fade_out_time=1)
            else:
                redLight.on()

        elif self.current_state.id == 'cool':
            if temp > self.setPoint:
                blueLight.pulse(fade_in_time=1, fade_out_time=1)
            else:
                blueLight.on()
        # 'off' leaves both off

    # Safe, locked read of the sensor
    def getFahrenheit(self):
        with sensor_lock:
            c = thSensor.temperature
        return ((9/5)*c) + 32

    # Prepare comma‐delimited status
    def setupSerialOutput(self):
        temp = floor(self.getFahrenheit())
        return f"{self.current_state.id},{temp},{self.setPoint}"

    # Kick off the display/serial thread
    def run(self):
        Thread(target=self.manageMyDisplay, daemon=True).start()

    def manageMyDisplay(self):
        counter    = 1
        altCounter = 1

        while not self.endDisplay:
            now = datetime.now()
            # Line 1: "YYYY-MM-DD HH:MM"
            lcd_line_1 = now.strftime("%Y-%m-%d %H:%M")

            # Alternate every 5s
            if altCounter < 6:
                temp       = floor(self.getFahrenheit())
                lcd_line_2 = f"Temp:{temp}F".ljust(16)
            else:
                state_name = self.current_state.id.title()
                lcd_line_2 = f"{state_name}:{self.setPoint}F".ljust(16)
                if altCounter >= 11:
                    self.updateLights()
                    altCounter = 1

            screen.updateScreen(lcd_line_1 + "\n" + lcd_line_2)
            altCounter += 1

            # Every 30s, send CSV status
            if counter % 30 == 0:
                ser.write((self.setupSerialOutput() + "\n").encode('utf-8'))
                counter = 1
            else:
                counter += 1

            sleep(1)

        screen.cleanupDisplay()

# Instantiate & start
tsm = TemperatureMachine()
tsm.run()

# Hook up the buttons
greenButton = Button(24)
greenButton.when_pressed = tsm.processTempStateButton

redButton = Button(25)
redButton.when_pressed = tsm.processTempIncButton

blueButton = Button(12)
blueButton.when_pressed = tsm.processTempDecButton

# Main loop—wait for CTRL-C
try:
    while True:
        sleep(30)
except KeyboardInterrupt:
    print("Cleaning up and exiting...")
    tsm.endDisplay = True
    sleep(1)
