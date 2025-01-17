from ws2812 import WS2812
import time

BLACK = (0, 0, 0)
RED = (255, 0, 0)
YELLOW = (255, 150, 0)
GREEN = (0, 255, 0)
CYAN = (0, 255, 255)
BLUE = (0, 0, 255)
PURPLE = (180, 0, 255)
WHITE = (255, 255, 255)
COLORS = (BLACK, RED, YELLOW, GREEN, CYAN, BLUE, PURPLE, WHITE)

#WS2812(pin_num,led_count)
# CABLE CONFIGURATION IS AS FOLLOWS
# LED: red -> black -> red PICO
# green -> white -> yellow (d16 pin)
# black -> grey -> black
led = WS2812(16,10) # Note that this is on Pin D16.

print("fills")
for color in COLORS:
    led.pixels_fill(color)
    led.pixels_show()
    time.sleep(0.2)

print("chases")
for color in COLORS:
    led.color_chase(color, 0.01)

print("rainbow")
led.rainbow_cycle(0)

# led.pixels_fill(RED)
# print("red")
# led.pixels_show()
# time.sleep(1)
# led.pixels_fill(BLACK)  # Turn off after
# led.pixels_show()
