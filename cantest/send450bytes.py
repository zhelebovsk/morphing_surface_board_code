import can
import time
import numpy as np

L = 30
W = 14
BOARD_IDS = np.arange(L, dtype=np.uint16) + 1

DX = 10 # mm
DY = 10 # mm


def send_frame(data, bus, id):
    msg = can.Message(arbitration_id=id+0x100, data=data, is_extended_id=False)
    bus.send(msg, timeout=0.1)
    # time.sleep(.05)

def new_position():
    t = time.time()
    positions_to_set = np.ones([L, W]) * np.sin(t) * 50 + 127
    positions_to_set = positions_to_set.astype(np.uint8)
    return positions_to_set


if __name__ == "__main__":
    try:
        with can.interface.Bus(channel="can0", interface="socketcan") as bus:
            pacer = 0
            t0 = time.time()
            while True:
                try:
                    pacer += 1
                    if pacer % 100 == 0:
                        print(f"Time taken for 100 iterations: {time.time() - t0:.4f} seconds")
                        t0 = time.time()
                    positions_to_set = new_position()
                    for i, id in enumerate(BOARD_IDS):
                        data1 = positions_to_set[i, :7]
                        data2 = positions_to_set[i, 7:]
                        data1 = np.concatenate([np.array([1], dtype=np.uint8), data1], dtype=np.uint8)
                        data2 = np.concatenate([np.array([2], dtype=np.uint8), data2], dtype=np.uint8)
                        data1 = data1.tobytes()
                        data2 = data2.tobytes()
                        send_frame(data2, bus, id)
                        send_frame(data1, bus, id)
                except KeyboardInterrupt:
                    print("Exiting...")
                    break
    except OSError:
        print("Your CAN sucks")
