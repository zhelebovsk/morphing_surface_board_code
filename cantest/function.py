import numpy as np

def motor_function(x_mm, y_mm, t):
    return np.sin(t * 2 * np.pi/10 + x_mm / 100) * np.cos(t * 2 * np.pi/10 + y_mm / 100)
    # return -1