from gpiozero import Button, LED
from statemachine import StateMachine, State
from time import sleep
import board
import digitalio
import adafruit_character_lcd.character_lcd as characterlcd
from threading import Thread

DEBUG = True

class ManagedDisplay():
    def __init__(self):
        self.lcd_rs = digitalio.DigitalInOut(board.D17)
        self.lcd_en = digitalio.DigitalInOut(board.D27)
        self.lcd_d4 = digitalio.DigitalInOut(board.D5)
        self.lcd_d5 = digitalio.DigitalInOut(board.D6)
        self.lcd_d6 = digitalio.DigitalInOut(board.D13)
        self.lcd_d7 = digitalio.DigitalInOut(board.D26)
        self.lcd_columns = 16
        self.lcd_rows = 2 
        self.lcd = characterlcd.Character_LCD_Mono(self.lcd_rs, self.lcd_en, 
                    self.lcd_d4, self.lcd_d5, self.lcd_d6, self.lcd_d7, 
                    self.lcd_columns, self.lcd_rows)
        self.lcd.clear()

    def cleanupDisplay(self):
        self.lcd.clear()
        self.lcd_rs.deinit()
        self.lcd_en.deinit()
        self.lcd_d4.deinit()
        self.lcd_d5.deinit()
        self.lcd_d6.deinit()
        self.lcd_d7.deinit()

    def clear(self):
        self.lcd.clear()

    def updateScreen(self, message):
        self.lcd.clear()
        self.lcd.message = message

class CWMachine(StateMachine):
    redLight = LED(18)
    blueLight = LED(23)

    message1 = 'SOS'
    message2 = 'OK'
    activeMessage = message1
    endTransmission = False

    off = State(initial=True)
    dot = State()
    dash = State()
    dotDashPause = State()
    letterPause = State()
    wordPause = State()

    screen = ManagedDisplay()

    morseDict = {
        "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
        "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
        "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
        "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
        "Y": "-.--", "Z": "--..", "0": "-----", "1": ".----", "2": "..---",
        "3": "...--", "4": "....-", "5": ".....", "6": "-....", "7": "--...",
        "8": "---..", "9": "----."
    }

    doDot = (
        off.to(dot) | dot.to(off)
    )

    doDash = (
        off.to(dash) | dash.to(off)
    )

    doDDP = (
        off.to(dotDashPause) |
        dot.to(dotDashPause) |
        dash.to(dotDashPause) |
        dotDashPause.to(off)
    )

    doLP = (
        off.to(letterPause) |
        dotDashPause.to(letterPause) |
        letterPause.to(off)
    )

    doWP = (
        off.to(wordPause) |
        letterPause.to(wordPause) |
        wordPause.to(off)
    )

    goOff = (
        dot.to(off) |
        dash.to(off) |
        dotDashPause.to(off) |
        letterPause.to(off) |
        wordPause.to(off)
    )

    def on_enter_dot(self):
        self.redLight.on()
        sleep(0.5)
        if DEBUG:
            print("* Changing state to red - dot")

    def on_exit_dot(self):
        self.redLight.off()

    def on_enter_dash(self):
        self.blueLight.on()
        sleep(1.5)
        if DEBUG:
            print("* Changing state to blue - dash")

    def on_exit_dash(self):
        self.blueLight.off()

    def on_enter_dotDashPause(self):
        if DEBUG:
            print("* Pausing Between Dots/Dashes - 250ms")
        sleep(0.25)

    def on_enter_letterPause(self):
        if DEBUG:
            print("* Pausing Between Letters - 750ms")
        sleep(0.75)

    def on_enter_wordPause(self):
        if DEBUG:
            print("* Pausing Between Words - 3000ms")
        sleep(3)

    def toggleMessage(self):
        self.activeMessage = self.message2 if self.activeMessage == self.message1 else self.message1
        if DEBUG:
            print(f"* Toggling active message to: {self.activeMessage}")

    def processButton(self):
        print('*** processButton')
        self.toggleMessage()

    def run(self):
        myThread = Thread(target=self.transmit)
        myThread.start()

    def transmit(self):
        while not self.endTransmission:
            self.screen.updateScreen(f"Sending:\n{self.activeMessage}")
            wordList = self.activeMessage.split()
            wordsCounter = 1
            lenWords = len(wordList)

            for word in wordList:
                wordCounter = 1
                lenWord = len(word)

                for char in word.upper():
                    morse = self.morseDict.get(char, "")
                    morseCounter = 1
                    lenMorse = len(morse)

                    for symbol in morse:
                        # Always return to 'off' before any new action
                        if self.current_state != self.off:
                            self.goOff()

                        if symbol == '.':
                            self.doDot()
                        elif symbol == '-':
                            self.doDash()

                        if morseCounter < lenMorse:
                            if self.current_state != self.off:
                                self.goOff()
                            self.doDDP()
                            morseCounter += 1

                    if wordCounter < lenWord:
                        if self.current_state != self.off:
                            self.goOff()
                        self.doLP()
                        wordCounter += 1

                if wordsCounter < lenWords:
                    if self.current_state != self.off:
                        self.goOff()
                    self.doWP()
                    wordsCounter += 1

        self.screen.cleanupDisplay()

cwMachine = CWMachine()
cwMachine.run()

greenButton = Button(24)
greenButton.when_pressed = cwMachine.processButton

repeat = True

while repeat:
    try:
        if DEBUG:
            print("Killing time in a loop...")
        sleep(20)
    except KeyboardInterrupt:
        print("Cleaning up. Exiting...")
        repeat = False
        cwMachine.endTransmission = True
        sleep(1)
