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
    positions_to_set = np.ones([L, W]) * np.sin(2*np.pi*t) * 100 + 127
    # positions_to_set = np.zeros([L, W]) +80
    positions_to_set = positions_to_set.astype(np.uint8)
    return positions_to_set

def reset_the_boards(bus):
    # data = np.zeros([8, 1], dtype=np.uint8)
    data = 0
    data = data.to_bytes()
    for i in BOARD_IDS:
        send_frame(data, bus, i)
# def set_speed(bus, speed_up, speed_down):
#     data = np.zeros(8, dtype=np.uint8)
#     data[0] = 0x5
#     up = np.ones([L,W], dtype=np.uint8) * speed_up
#     for i in BOARD_IDS:
#         send_frame(data[].tobytes(), bus, i)
    
    
    # send_frame(up.tobytes(), bus, 0x1)

    # down = np.ones([L,W], dtype=np.uint8) * speed_down

    # data[1:8] = np.concatenate([np.array([speed_up], dtype=np.uint8), np.array([speed_down], dtype=np.uint8)])

if __name__ == "__main__":
    try:
        with can.interface.Bus(channel="can0", interface="socketcan") as bus:
            pacer = 0
            t0 = time.time()
            while True:
                try:
                    # reset_the_boards(bus)
                    pacer += 1
                    if pacer % 100 == 0:
                        print(f"Time taken for 100 iterations: {time.time() - t0:.4f} seconds")
                        t0 = time.time()
                    positions_to_set = new_position()
                    for i, id in enumerate(BOARD_IDS):
                        pass
                        data1 = positions_to_set[i, :7]
                        data2 = positions_to_set[i, 7:]
                        data1 = np.concatenate([np.array([1], dtype=np.uint8), data1], dtype=np.uint8)
                        data2 = np.concatenate([np.array([2], dtype=np.uint8), data2], dtype=np.uint8)
                        data1 = data1.tobytes()
                        data2 = data2.tobytes()
                        send_frame(data2, bus, id)
                        send_frame(data1, bus, id)
                    # time.sleep(1.0)
                except KeyboardInterrupt:
                    print("Exiting...")
                    break
    except OSError:
        print("Your CAN sucks")
