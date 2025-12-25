import serial
import re
import collections
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation


# === CONFIGURE ===
PORT = "/dev/ttyACM0"   # or COM3 on Windows
BAUD = 115200
HISTORY = 200           # number of points to show

# === SERIAL ===
ser = serial.Serial(PORT, BAUD, timeout=1)

# Rolling buffer
data = collections.deque(maxlen=HISTORY)

# Regex to extract POT value e.g. "POTs: 592"
pattern = re.compile(r"POTs:\s*(\d+)")

# === Plot setup ===
fig, ax = plt.subplots()
line, = ax.plot([], [], lw=2)
ax.set_ylim(0-410, 4095+410)
ax.set_xlim(0, HISTORY)
ax.set_title("Real-time POT input")
ax.set_xlabel("Samples")
ax.set_ylabel("ADC value")

ax.grid()


def update(frame):
    global data
    line_from_serial = ser.readline().decode(errors='ignore').strip()

    match = pattern.search(line_from_serial)
    if match:
        pot = int(match.group(1))
        data.append(pot)

    # Update plot data
    line.set_data(range(len(data)), list(data))
    return line,


ani = FuncAnimation(fig, update, interval=1, blit=True)
plt.tight_layout()
plt.show()