from gpiozero import RGBLED
from time import sleep

# Using GPIO17 / GPIO16 / GPIO26
led = RGBLED(red=17, green=16, blue=26)

while True:
    led.color = (1, 0, 0)  # Red
    sleep(3)
    led.color = (0, 1, 0)  # Green
    sleep(3)
    led.color = (0, 0, 1)  # Blue
    sleep(3)
    led.color = (1, 1, 1)  # White
    sleep(3)
    led.off()
    sleep(5)
