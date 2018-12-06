from lcd import LCD_1in44, LCD_Config
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor

import os, logging, sys, traceback, glob
from random import randint
import multiprocessing
from multiprocessing import Process, Pipe, Queue, Event, Value, Lock, current_process
from subprocess import Popen, PIPE, call, signal
import time
from functools import partial

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


def timerupdateproc(timer_is_on, timer, lock):
    p = current_process()
    logger = logging.getLogger("mypispresso").getChild("tempupdateproc")
    logger.info('Starting:' + p.name + ":" + str(p.pid))

    try:
        while (True):
            if timer_is_on.value:
                time.sleep(1)
                with lock:
                    timer.value += 1
            else:
                timer.value = 1
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


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


def lcdpainterproc(temp, timer, heat_is_on, timer_is_on, power_button_press, brew_button_press, steam_button_press):
    p = current_process()
    logger = logging.getLogger("mypispresso").getChild("lcdpainterproc")
    logger.info('Starting:' + p.name + ":" + str(p.pid))

    lcd = LCD_1in44.LCD()

    # Init LCD
    lcd_scandir = LCD_1in44.SCAN_DIR_DFT  # SCAN_DIR_DFT = D2U_L2R
    lcd.LCD_Init(lcd_scandir)

    background = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
    # gaggia_logo = Image.open('lcd/gaggia.png').convert('RGBA').resize((80, 121))
    power_on_icon = Image.open('lcd/power_button_on.png').convert('RGBA').resize((18, 18))
    power_off_icon = Image.open('lcd/power_button_off.png').convert('RGBA').resize((18, 18))
    brew_on_icon = Image.open('lcd/brew_button_on.png').convert('RGBA').resize((18, 18))
    brew_off_icon = Image.open('lcd/brew_button_off.png').convert('RGBA').resize((18, 18))
    steam_on_icon = Image.open('lcd/steam_button_on.png').convert('RGB').resize((18, 18))
    steam_off_icon = Image.open('lcd/steam_button_off.png').convert('RGB').resize((18, 18))

    temp_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 25)
    timer_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 60)

    try:
        while (True):
            time.sleep(0.5)
            background_cycle = background.copy()
            draw = ImageDraw.Draw(background_cycle)

            if timer_is_on.value:
                draw.text((40, 25), str(timer.value), align="center", font=timer_font, fill="YELLOW")

            if power_button_press.is_set():
                draw.text((73, 1), str(temp.value) + u'\N{DEGREE SIGN}', align="right", font=temp_font, fill="RED" if heat_is_on.value else "GRAY")
                background.paste(power_on_icon, (1, 24))
            else:
                background.paste(power_off_icon, (1, 24))
                # background.paste(gaggia_logo, (37, 5))

            if brew_button_press.is_set():
                background.paste(brew_on_icon, (1, 54))
            else:
                background.paste(brew_off_icon, (1, 54))

            if steam_button_press.is_set():
                background.paste(steam_on_icon, (1, 84))
            else:
                background.paste(steam_off_icon, (1, 84))

            background_cycle = background_cycle.rotate(180)
            lcd.LCD_ShowImage(background_cycle, 0, 0)
            LCD_Config.Driver_Delay_ms(500)
            background_cycle = None
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def powerButtonPress(channel):
    try:
        if power_button_press.is_set():
            logger.info('Power Off')
            power_button_press.clear()

            # Turn off the machine here...
        else:
            logger.info('Power On')
            power_button_press.set()

            # Turn on the machine here...

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            ''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def brewButtonPress(timer_is_on):
    try:
        if power_button_press.is_set():
            if brew_button_press.is_set():
                logger.info('Brew Off')
                brew_button_press.clear()
                timer_is_on.value = False

                # Turn off the pump here...
            else:
                logger.info('Brew On')
                brew_button_press.set()

                timer_is_on.value = True
                # Turn on the pump here...

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            ''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def steamButtonPress(channel):
    try:
        if power_button_press.is_set():
            if steam_button_press.is_set():
                logger.info('Steam Off')
                steam_button_press.clear()

                # Turn off the steam here...
            else:
                logger.info('Steam On')
                steam_button_press.set()

                # Turn on the steam here...

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            ''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def cleanup():
    logger.info("Shutting down...")
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.cleanup()


if __name__ == '__main__':


    try:
        logger_init()

        # Heat is on
        heat_is_on = Value('b', False)

        # Button press events
        power_button_press = Event()
        brew_button_press = Event()
        steam_button_press = Event()

        GPIO.add_event_detect(gpio_btn_power, GPIO.RISING, callback=powerButtonPress, bouncetime=300)
        GPIO.add_event_detect(gpio_btn_brew, GPIO.RISING, callback=lambda x: brewButtonPress(timer_is_on), bouncetime=300)
        GPIO.add_event_detect(gpio_btn_steam, GPIO.RISING, callback=steamButtonPress, bouncetime=300)

        # Timer Update Loop
        timer_is_on = Value('b', False)
        timer_secs = Value('i', 0)
        timer_lock = Lock()
        timerupdateproc = Process(target=timerupdateproc, args=(timer_is_on, timer_secs, timer_lock))

        # Temperature Update Loop
        curr_temp = Value('i', 0)
        temp_lock = Lock()
        tempupdateproc = Process(target=tempupdateproc, args=(curr_temp, temp_lock))

        # LCD Painting Loop
        lcdpainterproc = Process(target=lcdpainterproc, args=(curr_temp, timer_secs, heat_is_on, timer_is_on, power_button_press, brew_button_press, steam_button_press))

        timerupdateproc.start()
        tempupdateproc.start()
        lcdpainterproc.start()

        timerupdateproc.join()
        tempupdateproc.join()
        lcdpainterproc.join()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        cleanup()
        sys.exit()

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))

        cleanup()
        sys.exit()
