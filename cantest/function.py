import numpy as np

def motor_function(x_mm, y_mm, t):
    return np.sin(2 * np.pi * (- t * 8 + x_mm / 50))
    # return np.sin(t * 2 * np.pi/5 + x_mm / 100) * np.cos(t * 2 * np.pi/5 + y_mm / 100)
    # return -1.0