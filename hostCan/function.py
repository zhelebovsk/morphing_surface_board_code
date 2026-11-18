import numpy as np

# t is in wave cycles, not seconds: the pattern should repeat every 1.0 of t.
# The GUI's μ sets how many cycles run per second.
def motor_function(x_mm, y_mm, t):
    return np.sin(t * 2 * np.pi + x_mm / 100)
    # return np.sin(t * 2 * np.pi + x_mm / 100) * np.cos(t * 2 * np.pi + y_mm / 100)
    # return -1.0