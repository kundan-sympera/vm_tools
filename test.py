import pyautogui
import webbrowser
from probes._common import open_console, close_console

webbrowser.open("https://www.zoominfo.com/companies-search/location-usa--south-dakota--sioux-falls-industry-accounting?pageNum=2")


import time
time.sleep(3)
open_console()

print("capturing")
time.sleep(3)
print(pyautogui.position())