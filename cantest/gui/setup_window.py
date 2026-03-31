from tkinter import Tk, Label, StringVar, LEFT, Button, OptionMenu

from communication import can_search
from config import SCALING_FACTOR


class SetupWindow:
    def __init__(self):
        channels = can_search()

        self.window = Tk()
        self.window.tk.call('tk', 'scaling', SCALING_FACTOR)
        self.window.title("GUI setup")
        self.window.geometry("960x120")
        self.window.resizable(False, False)

        self.channel_choice = StringVar(value=channels[0])
        self.started = False

        Label(self.window, text="CAN channel:").pack(side=LEFT, padx=4, pady=8)
        OptionMenu(self.window, self.channel_choice, *channels).pack(side=LEFT, padx=4, pady=8)
        Button(self.window, text="Start", command=self.on_start).pack(side=LEFT, padx=8, pady=8)
        self.window.mainloop()

    def on_start(self):
        self.started = True
        self.window.destroy()

    def get_channel(self):
        return self.channel_choice.get()
