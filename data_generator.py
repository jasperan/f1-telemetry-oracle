import pyautogui
import keyboard
import pickle
from pathlib import Path
import time
# directkeys.py
# http://stackoverflow.com/questions/13564851/generate-keyboard-events
# msdn.microsoft.com/en-us/library/dd375731

import ctypes
from ctypes import wintypes
import time
import pyautogui


user32 = ctypes.WinDLL('user32', use_last_error=True)

INPUT_MOUSE    = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_UNICODE     = 0x0004
KEYEVENTF_SCANCODE    = 0x0008

MAPVK_VK_TO_VSC = 0

# List of all codes for keys:
# # msdn.microsoft.com/en-us/library/dd375731

# spanish key names. you can replace with your keyboard-language equivalents
hex_keys = {
    'esc': 0x1B,
    'enter': 0x0D,
    'esc': 0x1B,
    'space': 0x20,
    'flecha izquierda': 0x25,
    'flecha arriba': 0x26,
    'flecha derecha': 0x27,
    'flecha abajo': 0x28,
    '0': 0x30,
    '1': 0x31,
    '2': 0x32, 
    '3': 0x33,
    '4': 0x34,
    '5': 0x35,
    '6': 0x36,
    '7': 0x37,
    '8': 0x38,
    '9':0x39,
    'A': 0x41,
    'B': 0x42,
    'C': 0x43,
    'D': 0x44,
    'E': 0x45,
    'F': 0x46,
    'G': 0x47,
    'H': 0x48,
    'I': 0x49,
    'J': 0x4A,
    'K': 0x4B,
    'L': 0x4C,
    'M': 0x4D,
    'N': 0x4E, 
    'O': 0x4F,
    'P': 0x50,
    'Q': 0x51,
    'R': 0x52,
    'S': 0x53,
    'T': 0x54,
    'U': 0x55,
    'V': 0x56,
    'W': 0x57,
    'X': 0x58,
    'Y': 0x59,
    'Z': 0x5A,
    'f1': 0x70 ,
    'f2': 0x71,
    'f3': 0x72,
    'f4': 0x73,
    'f5': 0x74,
    'f6': 0x75,
    'f7': 0x76,
    'f8': 0x77,
    'f9': 0x78,
    'f10': 0x79,
    'f11': 0x7A,
    'f12': 0x7B
}

# C struct definitions

wintypes.ULONG_PTR = wintypes.WPARAM

class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx",          wintypes.LONG),
                ("dy",          wintypes.LONG),
                ("mouseData",   wintypes.DWORD),
                ("dwFlags",     wintypes.DWORD),
                ("time",        wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR))

class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk",         wintypes.WORD),
                ("wScan",       wintypes.WORD),
                ("dwFlags",     wintypes.DWORD),
                ("time",        wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR))

    def __init__(self, *args, **kwds):
        super(KEYBDINPUT, self).__init__(*args, **kwds)
        # some programs use the scan code even if KEYEVENTF_SCANCODE
        # isn't set in dwFflags, so attempt to map the correct code.
        if not self.dwFlags & KEYEVENTF_UNICODE:
            self.wScan = user32.MapVirtualKeyExW(self.wVk,
                                                 MAPVK_VK_TO_VSC, 0)

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg",    wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))

class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT),
                    ("mi", MOUSEINPUT),
                    ("hi", HARDWAREINPUT))
    _anonymous_ = ("_input",)
    _fields_ = (("type",   wintypes.DWORD),
                ("_input", _INPUT))

LPINPUT = ctypes.POINTER(INPUT)

def _check_count(result, func, args):
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    return args

user32.SendInput.errcheck = _check_count
user32.SendInput.argtypes = (wintypes.UINT, # nInputs
                             LPINPUT,       # pInputs
                             ctypes.c_int)  # cbSize

# Functions

def PressKey(hexKeyCode):
    x = INPUT(type=INPUT_KEYBOARD,
              ki=KEYBDINPUT(wVk=hexKeyCode))
    user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))

def ReleaseKey(hexKeyCode):
    x = INPUT(type=INPUT_KEYBOARD,
              ki=KEYBDINPUT(wVk=hexKeyCode,
                            dwFlags=KEYEVENTF_KEYUP))
    user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))


'''
Written by @jasperan

This script aims to automate the data generation process of the F1 2021 game. The script interacts with the user's GUI while playing in a simple way and may not be used for any other purposes other than for generating data offline.
Doing this online will negatively impact the gaming experience of other users.
'''

def save_keyboard_sequence(keyboard_sequence_name, list_events):
    root_dir = Path(__file__).parent
    with open('{}/keyboard_sequences/{}.pickle'.format(root_dir, keyboard_sequence_name), 'wb') as file_object:
        print('Saving packet: {}/keyboard_sequences/{}.pickle'.format(root_dir, keyboard_sequence_name))
        pickle.dump(list_events, file_object, protocol=pickle.HIGHEST_PROTOCOL)



def load_keyboard_sequence(keyboard_sequence_name):
    root_dir = Path(__file__).parent
    with open('{}/keyboard_sequences/{}.pickle'.format(root_dir, keyboard_sequence_name), 'rb') as file_object:
        print('Reading packet: {}/keyboard_sequences/{}.pickle'.format(root_dir, keyboard_sequence_name))
        list_events = pickle.load(file_object)
        print('Read {} keyboard sequences'.format(len(list_events)))
    return list_events



def record(file_name):
    recorded = keyboard.record(until='f8')
    del recorded[-1] # delete the end trigger
    '''
    for x in recorded:
        #print(x)
        print(str(x))
        print(str(x).split('('))
    '''
    print(recorded)
    save_keyboard_sequence(file_name, recorded)



# this method is useless for F1 2021 since the keyboard module is blocked, probably, by the game's anticheat.
def playback(file_name):
    list_events = load_keyboard_sequence(file_name)
    keyboard.play(list_events, speed_factor=1) # replay at original speed



def get_sequence(file_name):
    list_event = load_keyboard_sequence(file_name)
    str_actions = list()
    prev_time = list_event[0].time # get the first time as baseline
    for x in list_event:
        concrete_action = str(x).split('(')[1][:-1]
        print(concrete_action)
        print('Delay: {}'.format(x.time - prev_time))
        str_actions.append(
            {
                'action': concrete_action,
                'delay': x.time - prev_time
            }
        )
        prev_time = x.time
    return str_actions



def parse_actions(actions_list):
    parsed_actions = list()
    for x in actions_list:
        action_type = x['action'].split(' ')[-1] # get the last word, which is always either 'up' or 'down'
        key_stroke = x['action'].split(action_type)[0].rstrip() # get the key stroke to reproduce
        print('ACTION TYPE: {} | KEY STROKE: {}'.format(action_type, key_stroke))
        parsed_actions.append(
            {
                'action_type': action_type,
                'key_stroke': key_stroke,
                'delay': x['delay']
            }
        )
    return parsed_actions



def play_actions(actions_list):
    for x in actions_list:
        time.sleep(x['delay'])
        if x['action_type'] == 'down':
            PressKey(hex_keys[x['key_stroke']])
            print('Pressed {}'.format(x['key_stroke']))
        else:
            ReleaseKey(hex_keys[x['key_stroke']])
            print('Released {}'.format(x['key_stroke']))
        


def advance_practice():
    time.sleep(62*60) # sleep for an hour

    PressKey(hex_keys['enter'])
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])

    time.sleep(30)
 
    PressKey(hex_keys['enter']) # advance to next phase
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])



def advance_qualifying():
    time.sleep(20*60) # sleep for 18 minutes

    PressKey(hex_keys['enter'])
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])

    time.sleep(30)
 
    PressKey(hex_keys['enter']) # accept fastest driver
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])

    time.sleep(5)

    PressKey(hex_keys['enter']) # advance to next phase
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])

    time.sleep(30)

    PressKey(hex_keys['enter']) # go to race
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])

    time.sleep(60*5) # wait 3 minutes



def race_day():
    # go to track
    PressKey(hex_keys['enter']) # go to race
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])

    time.sleep(10)
    # Now press 'space' for the race to start.
    PressKey(hex_keys['space'])
    time.sleep(1)
    ReleaseKey(hex_keys['space'])

    time.sleep(60*4) # wait 2 minutes to be DQ'd

    for x in range(2):
        # Now press 'enter' to advance
        PressKey(hex_keys['enter'])
        time.sleep(.1)
        ReleaseKey(hex_keys['enter'])

        time.sleep(5)

    time.sleep(25) # and now go to next session.
    PressKey(hex_keys['enter'])
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])




if __name__ == '__main__':
    # Countdown for beginning of program
    for i in list(range(4))[::-1]:
        print(i + 1)
        time.sleep(1)
    
    actions = get_sequence('new_gp')
    parsed_actions = parse_actions(actions)
    print('Parsed {} actions'.format(len(parsed_actions)))
    
    '''
    PressKey(hex_keys['enter'])
    time.sleep(.1)
    ReleaseKey(hex_keys['enter'])
    '''

    play_actions(parsed_actions)

    for x in range(23): # all circuits
        for x in range(3):
            advance_practice()

        # Now we are in qualifying. 1 qualifying round since we'll be disqualified in the first round..

        advance_qualifying()

        race_day()


    # qualifying is 18 minutes long

    '''
    record('new_gp')
    '''


