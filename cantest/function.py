import numpy as np

FUNCTION_DESCRIPTION = "u(x, y, t)"


def motor_function(x_mm, y_mm, t):
    return np.sin(t * 2 * np.pi + x_mm / 100) * np.cos(t * 2 * np.pi + y_mm / 100)