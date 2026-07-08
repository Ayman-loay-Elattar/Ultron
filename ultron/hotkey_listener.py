import keyboard

def listen(hotkey: str, on_trigger):
    print(f"Listening for hotkey: {hotkey} (Ctrl+C in this terminal to quit)")
    keyboard.add_hotkey(hotkey, on_trigger)
    keyboard.wait()  # blocks forever, listening
