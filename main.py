from lcd import LCD_1in44, LCD_Config
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor

import os, logging, sys, traceback, glob
import multiprocessing
from multiprocessing import Process, Pipe, Queue, Value, current_process
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
onewire_base_dir = '/sys/bus/w1/devices/'


class mem:
    lcd_connection = Pipe()
    lcd_base_image = Image()
    one_wire = None


def logger_init():
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info('******************************************')
    logger.info('Starting up...')


def test_lcd():
    lcd = LCD_1in44.LCD()

    # Init LCD
    lcd_scandir = LCD_1in44.SCAN_DIR_DFT  # SCAN_DIR_DFT = D2U_L2R
    lcd.LCD_Init(lcd_scandir)

    image = Image.new("RGB", (lcd.width, lcd.height), "WHITE")
    draw = ImageDraw.Draw(image)

    # font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf', 16)

    # draw line
    #draw.line([(0, 0), (127, 0)], fill="BLUE", width=5)
    #draw.line([(127, 0), (127, 127)], fill="BLUE", width=5)
    #draw.line([(127, 127), (0, 127)], fill="BLUE", width=5)
    #draw.line([(0, 127), (0, 0)], fill="BLUE", width=5)

    # draw rectangle
    #draw.rectangle([(18, 10), (110, 20)], fill="RED")

    # draw text
    draw.text((33, 22), 'WaveShare ', fill="BLUE")
    draw.text((32, 36), 'Electronic ', fill="BLUE")
    draw.text((28, 48), '1.44inch LCD ', fill="BLUE")

    lcd.LCD_ShowImage(image, 0, 0)
    LCD_Config.Driver_Delay_ms(500)

    #image = Image.open('time.bmp')
    #lcd.LCD_ShowImage(image, 0, 0)


def read_temp_raw():
    f = open(mem.one_wire, 'r')
    lines = f.readlines()
    f.close()
    return lines


def gettempProc():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return str(int(temp_f))


def lcdpainterproc(lcd_child_conn):
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
    background = background.rotate(180)

    temp_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 45)
    timer_font = ImageFont.truetype("/usr/src/app/lcd/arial.ttf", 20)

    try:
        while (True):
            time.sleep(0.5)
            draw = ImageDraw.Draw(background)
            draw.text((35, 1), gettempProc() + u'\N{DEGREE SIGN}', font=temp_font, fill="WHITE")
            draw.text((65, 105), "00 sec", font=timer_font, fill="WHITE")
            lcd.LCD_ShowImage(background, 0, 0)
            LCD_Config.Driver_Delay_ms(500)
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
        #test_lcd()

        # call(["modprobe", "w1-gpio"])
        # call(["modprobe", "w1-therm"])
        # call(["modprobe", "i2c-dev"])

        try:
            onewire_base_dir = glob.glob(onewire_base_dir + '28*')[0]
        except:
            logger.error("1-Wire Temp sensor not found in " + onewire_base_dir)

        mem.one_wire = onewire_base_dir + '/w1_slave'

        GPIO.add_event_detect(gpio_btn_heat_sig, GPIO.RISING, callback=catchButton, bouncetime=250)
        GPIO.add_event_detect(gpio_btn_pump_sig, GPIO.RISING, callback=catchButton, bouncetime=250)

        lcd_parent_conn, lcd_child_conn = Pipe()
        mem.lcd_connection = lcd_parent_conn

        lcdpainterproc = Process(name="lcdpainterproc", target=lcdpainterproc, args=(lcd_child_conn,))
        lcdpainterproc.start()

    except KeyboardInterrupt:
        cleanup()
        sys.exit()

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(''.join('!! ' + line for line in traceback.format_exception(exc_type, exc_value, exc_traceback)))

        cleanup()
        sys.exit()
