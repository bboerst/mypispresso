from lcd.LCD_1in44 import *
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor

import os, logging, sys, traceback, glob
from random import randint
import multiprocessing
from multiprocessing import Process, Pipe, Event, Value, Lock, current_process
import time

import RPi.GPIO as GPIO

gpio_heat = 4
gpio_pump = 17

gpio_btn_power = 16
gpio_btn_brew = 20
gpio_btn_steam = 21

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(gpio_heat, GPIO.OUT)
GPIO.setup(gpio_pump, GPIO.OUT)
GPIO.setup(gpio_btn_power, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(gpio_btn_brew, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(gpio_btn_steam, GPIO.IN, pull_up_down=GPIO.PUD_UP)

logger = logging.getLogger()

detachedmode = False
if("--detached" in  sys.argv):
    detachedmode = True


class mem:  # global class
    lcd_connection = Pipe()
    timer_connection = Pipe()


class globalvars(object):
    def __init__(self, initval = 0):
        self.temperature = multiprocessing.Value("i", initval)

    def set_temp(self, n=0):
        with self.temperature.get_lock():
            self.temperature.value = n

    @property
    def temp(self):
        with self.temperature.get_lock():
            return self.temperature.value


def logger_init():
    logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)

    logger.info('Starting up...')


def refreshlcd(payload="refresh"):
    mem.lcd_connection.send(payload)


def timer(timer_child_conn):
    p = current_process()
    logger = logging.getLogger("mypispresso").getChild("timerproc")
    logger.info('Starting:' + p.name + ":" + str(p.pid))

    timer = 0

    while (True):
        timer += 1
        refreshlcd("time=" + str(timer))
        time.sleep(1)


def read_temp_raw():
    onewire_base_dir = '/sys/bus/w1/devices/'
    onewire_base_dir = glob.glob(onewire_base_dir + '28*')[0]
    onewire_base_dir = onewire_base_dir + '/w1_slave'

    f = open(onewire_base_dir, 'r')
    lines = f.readlines()
    f.close()
    return lines


def gettemp():
    if detachedmode:
        return randint(199, 204)

    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return int(temp_f)


def tempupdateproc(temp, lock):
    p = current_process()
    logger = logging.getLogger("mypispresso").getChild("tempupdateproc")
    logger.info('Starting:' + p.name + ":" + str(p.pid))

    try:
        while (True):
            time.sleep(1)
            current_temp = gettemp()
            with lock:
                temp.value = current_temp
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def lcdpainterproc(lcd_child_conn):
    p = current_process()
    logger = logging.getLogger("mypispresso").getChild("lcdpainterproc")
    logger.info('Starting:' + p.name + ":" + str(p.pid))

    lcd = LCD()

    # Init LCD
    lcd_scandir = LCD.LCD_Scan_Dir  # SCAN_DIR_DFT = D2U_L2R
    lcd.LCD_Init(lcd_scandir)
    LCD.LCD_Clear()
    initial_load = True

    # gaggia_logo = Image.open('lcd/gaggia.png').convert('RGBA').resize((80, 121))
    power_on_icon = Image.open('lcd/power_button_on.png').convert('RGBA').resize((18, 18))
    power_off_icon = Image.open('lcd/power_button_off.png').convert('RGBA').resize((18, 18))
    brew_on_icon = Image.open('lcd/brew_button_on.png').convert('RGBA').resize((18, 18))
    brew_off_icon = Image.open('lcd/brew_button_off.png').convert('RGBA').resize((18, 18))
    steam_on_icon = Image.open('lcd/steam_button_on.png').convert('RGB').resize((18, 18))
    steam_off_icon = Image.open('lcd/steam_button_off.png').convert('RGB').resize((18, 18))

    temp_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 25)
    timer_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 60)

    background = Image.new("RGB", (lcd.width, lcd.height), "BLACK")

    while True:

        if initial_load:
            background.paste(power_off_icon, (1, 24))
            background.paste(brew_off_icon, (1, 54))
            background.paste(steam_off_icon, (1, 84))
            LCD.LCD_ShowImage(background.rotate(180), 0, 0)
            initial_load = False

        time.sleep(0.25)

        while lcd_child_conn.poll():
            try:
                recv = lcd_child_conn.recv()
                background_cycle = background.copy()
                draw = ImageDraw.Draw(background_cycle)

                # Show Timer
                if brew_button.is_set():
                    if "time" in recv:
                        draw.text((40, 25), str(recv.split('=')[1]), font=timer_font, fill="YELLOW")

                # Power Button
                if power_button.is_set():
                    background_cycle.paste(power_on_icon, (1, 24))

                    # Show Timer
                    draw.text((73, 1), str(123) + u'\N{DEGREE SIGN}', font=temp_font, fill="WHITE")
                else:
                    background_cycle.paste(power_off_icon, (1, 24))

                # Brew Button
                if brew_button.is_set():
                    background_cycle.paste(brew_on_icon, (1, 54))
                else:
                    background_cycle.paste(brew_off_icon, (1, 54))

                # Steam Button
                if steam_button.is_set():
                    background_cycle.paste(steam_on_icon, (1, 84))
                else:
                    background_cycle.paste(steam_off_icon, (1, 84))

                background_cycle = background_cycle.rotate(180)
                LCD.LCD_ShowImage(background_cycle, 0, 0)
                LCD.Driver_Delay_ms(500)
                background_cycle = None
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def powerButtonPress(channel):
    try:
        if power_button.is_set():
            logger.info('Power Off')
            power_button.clear()
            refreshlcd()

            # Turn off the machine here...
        else:
            logger.info('Power On')
            power_button.set()
            refreshlcd()

            # Turn on the machine here...

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            ''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def brewButtonPress(channel):
    try:
        if power_button.is_set():
            if brew_button.is_set():
                logger.info('Brew Off')
                brew_button.clear()
                refreshlcd()

                # Turn off the pump here...
            else:
                logger.info('Brew On')
                brew_button.set()

                # Timer Process
                timer_parent_conn, timer_child_conn = Pipe()
                mem.timer_connection = timer_parent_conn
                timerproc = Process(target=timer, args=(timer_child_conn,))
                timerproc.start()

                refreshlcd()

                # Turn on the pump here...

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            ''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def steamButtonPress(channel):
    if power_button.is_set():
        if steam_button.is_set():
            logger.info('Steam Off')
            steam_button.clear()
            refreshlcd()

            # Turn off the steam here...
        else:
            logger.info('Steam On')
            steam_button.set()
            refreshlcd()

            # Turn on the steam here...


def cleanup():
    logger.info("Shutting down...")
    GPIO.cleanup()


if __name__ == '__main__':

    try:
        logger_init()

        # Heat is on
        heat_is_on = Value('b', False)

        # Button press events
        power_button = Event()
        brew_button = Event()
        steam_button = Event()

        GPIO.add_event_detect(gpio_btn_power, GPIO.RISING, callback=powerButtonPress, bouncetime=300)
        GPIO.add_event_detect(gpio_btn_brew, GPIO.RISING, callback=brewButtonPress, bouncetime=300)
        GPIO.add_event_detect(gpio_btn_steam, GPIO.RISING, callback=steamButtonPress, bouncetime=300)

        # Temperature Update Loop
        curr_temp = Value('i', 0)
        temp_lock = Lock()
        tempupdateproc = Process(target=tempupdateproc, args=(curr_temp, temp_lock))

        # LCD Process
        lcd_parent_conn, lcd_child_conn = Pipe()
        mem.lcd_connection = lcd_parent_conn
        lcdpainterproc = Process(target=lcdpainterproc, args=(lcd_child_conn,))

        tempupdateproc.start()
        lcdpainterproc.start()

    except KeyboardInterrupt:
        cleanup()
        sys.exit()

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))

        cleanup()
        sys.exit()
