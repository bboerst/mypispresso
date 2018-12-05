from lcd import LCD_1in44, LCD_Config
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor

import os, logging, sys, traceback, glob
from random import randint
import multiprocessing
from multiprocessing import Process, Pipe, Queue, Value, Lock, current_process
from subprocess import Popen, PIPE, call, signal
import time

import RPi.GPIO as GPIO

gpio_heat = 4
gpio_pump = 17
gpio_btn_heat_sig = 21
gpio_btn_pump_sig = 20

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(gpio_heat, GPIO.OUT)
GPIO.setup(gpio_pump, GPIO.OUT)
GPIO.setup(gpio_btn_heat_sig, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(gpio_btn_pump_sig, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

logger = logging.getLogger()

detachedmode = False
if("--detached" in  sys.argv):
    detachedmode = True


def logger_init():
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info('******************************************')
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
                timer.value = 0
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


def lcdpainterproc(temp, timer, heat_is_on, timer_is_on):
    p = current_process()
    logger = logging.getLogger("mypispresso").getChild("lcdpainterproc")
    logger.info('Starting:' + p.name + ":" + str(p.pid))

    lcd = LCD_1in44.LCD()

    # Init LCD
    lcd_scandir = LCD_1in44.SCAN_DIR_DFT  # SCAN_DIR_DFT = D2U_L2R
    lcd.LCD_Init(lcd_scandir)

    background = Image.new("RGB", (lcd.width, lcd.height), "BLACK")
    power_icon = Image.open('lcd/power_icon.png').convert('RGBA').resize((18, 18))
    brew_icon = Image.open('lcd/coffee_cup_icon.png').convert('RGBA').resize((18, 18))
    steam_icon = Image.open('lcd/steam_icon.jpg').convert('RGB').resize((18, 18))
    inverted_steam_icon = ImageOps.invert(steam_icon)  # Inverts black to white

    background.paste(power_icon, (1, 24))
    background.paste(brew_icon, (1, 54))
    background.paste(inverted_steam_icon, (1, 84))

    temp_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 25)
    timer_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 60)

    try:
        while (True):
            time.sleep(0.5)
            background_cycle = background.copy()
            draw = ImageDraw.Draw(background_cycle)
            draw.text((73, 1), str(temp.value) + u'\N{DEGREE SIGN}', align="right", font=temp_font, fill="RED" if heat_is_on.value else "GRAY")

            if timer_is_on.value:
                draw.text((40, 25), str(timer.value), align="center", font=timer_font, fill="YELLOW")

            background_cycle = background_cycle.rotate(180)
            lcd.LCD_ShowImage(background_cycle, 0, 0)
            LCD_Config.Driver_Delay_ms(500)
            background_cycle = None
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def catchButton(btn):
    try:
        time.sleep(0.05)
        if GPIO.input(btn) != GPIO.HIGH:  # check to see if the input button is still high, protect against EMI false positive
            return

        if btn == gpio_btn_heat_sig:
            logger.debug("catchButton: Heat ON")

        elif btn == gpio_btn_pump_sig:
            logger.debug("catchButton: Pump ON")

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))


def cleanup():
    logger.info("Shutting down...")
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.cleanup()


if __name__ == '__main__':
    try:
        logger_init()

        GPIO.add_event_detect(gpio_btn_heat_sig, GPIO.RISING, callback=catchButton, bouncetime=250)
        GPIO.add_event_detect(gpio_btn_pump_sig, GPIO.RISING, callback=catchButton, bouncetime=250)

        # Heat is on
        heat_is_on = Value('b', False)

        # Timer Update Loop
        timer_is_on = Value('b', True)
        timer_secs = Value('i', 0)
        timer_lock = Lock()
        timerupdateproc = Process(target=timerupdateproc, args=(timer_is_on, timer_secs, timer_lock))

        # Temperature Update Loop
        curr_temp = Value('i', 0)
        temp_lock = Lock()
        tempupdateproc = Process(target=tempupdateproc, args=(curr_temp, temp_lock))

        # LCD Painting Loop
        lcdpainterproc = Process(target=lcdpainterproc, args=(curr_temp, timer_secs, heat_is_on, timer_is_on))

        timerupdateproc.start()
        tempupdateproc.start()
        lcdpainterproc.start()

        timerupdateproc.join()
        tempupdateproc.join()
        lcdpainterproc.join()

    except KeyboardInterrupt:
        cleanup()
        sys.exit()

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))

        cleanup()
        sys.exit()
