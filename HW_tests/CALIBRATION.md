# Motor Calibration

Finds `min_pwm` (stiction threshold) and step-response characteristics per motor. Runs over CAN only — no ST-LINK needed.

## Prerequisites
- Firmware running, CAN interface up (`sudo bash ../can_start_kvaser.sh`)
- Cantest GUI **not** running

## Run
```bash
cd HW_tests
python calibration_app.py
```

## Parameters

| | Parameter | Effect |
|---|---|---|
| **Motion** | Step size (ADC) | How far the motor steps. Larger = clearer signal. |
| | Movement threshold (ADC) | Minimum to count as "moved". |
| | Step timeout (s) | Recording window per step attempt. |
| | Settle time (s) | Wait between motors. |
| **PWM search** | Low / High / Step | Range and resolution of the stiction search. |
| **Calib PID** | Kp, Ki=0, u_limit=60 | Ki=0 prevents wind-up. u_limit lower than running to avoid slamming. |

## Results table

| Column | Meaning |
|---|---|
| min_pwm | Main output — lowest PWM that moved the motor. |
| τ (ms) | Step response time constant. Lower = faster motor. |
| Overshoot | How far past target. Large negative = PID too aggressive. |
| Actual step | Real movement vs commanded. Large deviation → suspicious. |

**Status colours:** grey = not connected, yellow = testing, green = good, orange = suspicious (wrong direction, moved <40% of step, or moved way more than commanded — likely not attached to linkage), red = never moved.

## On finish (automatic)
- Saves `calibrations/DD.MM.YY_HH:MM.json` — one file per run, all boards inside.
- Sends calibrated `min_pwm` + normal running config to each board over CAN (only if at least one non-suspicious motor responded).

## Output structure
```json
{
  "timestamp": "15.3.25_15:32",
  "params": { "step_size_adc": 60, ... },
  "boards": {
    "1": {
      "recommended_min_pwm": 50,
      "motors": {
        "12": { "min_pwm": 50, "tau_ms": 554.7, "overshoot": -12.0 },
        "13": { "min_pwm": 30, "suspicious": true }
      }
    }
  }
}
```
