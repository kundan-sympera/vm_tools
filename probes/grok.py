import webbrowser
webbrowser.open("grok.com")
import pyautogui

import time

print("getting center position")
time.sleep(5)
print(pyautogui.position())

import pyperclip

pyperclip.copy("check this company details Microsoft")

pyautogui.hotkey("ctrl","v")

pyautogui.press("enter")