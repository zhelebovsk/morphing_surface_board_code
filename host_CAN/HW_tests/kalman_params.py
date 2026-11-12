"""
kalman_params.py — Compute Kalman filter parameters from hardware test results.

Load noise_test and (optionally) step_response_test JSON files and output:
  - R  : measurement noise variance
  - Q  : process noise variance
  - K  : steady-state Kalman gain (equivalent to IIR alpha)
  - Recommended alpha for current IIR filter if Kalman is not implemented yet

Theory (1-D random-walk model):
  State:       x[k+1] = x[k] + w[k],    w ~ N(0, Q)
  Measurement: z[k]   = x[k] + v[k],    v ~ N(0, R)

Steady-state Kalman gain:
  P_ss  = ( -Q + sqrt(Q^2 + 4*Q*R) ) / 2
  K_ss  = (P_ss + Q) / (P_ss + Q + R)
  K_ss  is directly equivalent to IIR alpha.

Usage:
  python kalman_params.py results/noise_motorX.json [results/step_board_motor_step.json]
"""

import json
import math
import sys
import os

# ── Load files ────────────────────────────────────────────────────────────────

def load_json(path):
    with open(path) as f:
        return json.load(f)

def list_result_files():
    results_dir = "results"
    if not os.path.isdir(results_dir):
        return [], []
    noise = sorted(f for f in os.listdir(results_dir) if f.startswith("noise_"))
    step  = sorted(f for f in os.listdir(results_dir) if f.startswith("step_"))
    return [os.path.join(results_dir, f) for f in noise], \
           [os.path.join(results_dir, f) for f in step]

# ── Kalman steady-state solver ────────────────────────────────────────────────

def steady_state_kalman(Q, R):
    """
    Returns (P_ss, K_ss) for the 1-D random-walk Kalman filter.
    K_ss is equivalent to IIR alpha.
    """
    discriminant = Q ** 2 + 4 * Q * R
    P_ss = (-Q + math.sqrt(discriminant)) / 2
    P_pred = P_ss + Q
    K_ss = P_pred / (P_pred + R)
    return P_ss, K_ss

def alpha_to_equivalent_QR(alpha):
    """
    Given an IIR alpha, return the Q/R ratio that produces that Kalman gain.
    K = alpha  →  Q/R = alpha^2 / (1 - alpha)
    """
    return alpha ** 2 / (1 - alpha) if alpha < 1.0 else float("inf")

# ── Analysis ──────────────────────────────────────────────────────────────────

def analyse(noise_path, step_path=None):
    noise_data = load_json(noise_path)
    motor_id   = noise_data["motor_id"]
    R          = noise_data["statistics"]["variance_R"]
    std        = noise_data["statistics"]["std_dev"]
    sample_hz  = noise_data["sample_hz"]

    print(f"\n── Noise test  (motor {motor_id}) ─────────────────────────────")
    print(f"  R (measurement variance) = {R:.3f}  (std = {std:.2f} ADC counts)")
    print(f"  Sampling rate            = {sample_hz:.1f} Hz")
    print(f"  Lag-1 autocorr           = {noise_data['statistics']['lag1_autocorr']:.3f}"
          "  (>0.3 means ADC has correlated noise)")

    Q_sources = {}

    # Q from step response (if available)
    if step_path:
        step_data = load_json(step_path)
        Q_residual = step_data["fit"].get("Q_residual_variance")
        tau_ms     = step_data["fit"].get("tau_ms")
        if Q_residual:
            Q_sources["step_residual"] = Q_residual
            print(f"\n── Step response (board {step_data['board_id']}, "
                  f"active_motor {step_data['active_motor_idx']}) ──────────")
            print(f"  Commanded step:  {step_data['step_value']} → "
                  f"{step_data['actual_step_adc']:.1f} ADC counts actual")
            if tau_ms:
                print(f"  Time constant τ: {tau_ms:.1f} ms")
            print(f"  Q (from residuals): {Q_residual:.3f}")

    # Q from autocorrelation: if pot_raw is correlated, sensor drift dominates
    # Rule of thumb: Q ≈ R * autocorr / (1 - autocorr)
    autocorr = noise_data["statistics"]["lag1_autocorr"]
    if autocorr > 0.05:
        Q_autocorr = R * autocorr / (1.0 - autocorr)
        Q_sources["autocorr"] = Q_autocorr

    # Default fallback Q values (conservative, moderate, aggressive)
    Q_options = {
        "conservative (slow, smooth)": R / 100,
        "moderate":                    R / 10,
        "aggressive (fast, noisier)":  R,
    }
    if "step_residual" in Q_sources:
        Q_options["from step response"] = Q_sources["step_residual"]
    if "autocorr" in Q_sources:
        Q_options["from autocorrelation"] = Q_sources["autocorr"]

    print(f"\n── Kalman filter parameters ───────────────────────────────────")
    print(f"  R = {R:.3f}")
    print()
    print(f"  {'Q source':<35}  {'Q':>8}  {'K_ss (alpha)':>14}  {'tau at 10kHz':>14}")
    print(f"  {'-'*35}  {'-'*8}  {'-'*14}  {'-'*14}")

    recommended_K = None
    for label, Q in Q_options.items():
        _, K = steady_state_kalman(Q, R)
        # Equivalent IIR time constant at current sample rate
        if K > 0 and K < 1:
            tau_iir = -1.0 / (10000 * math.log(1 - K))
            tau_str = f"{tau_iir * 1000:.1f} ms"
        else:
            tau_str = "n/a"
        marker = " ← recommended" if "moderate" in label else ""
        print(f"  {label:<35}  {Q:>8.3f}  {K:>14.4f}  {tau_str:>14}{marker}")
        if "moderate" in label:
            recommended_K = K

    current_alpha = 0.2
    print(f"\n── Comparison to current IIR (alpha={current_alpha}) ───────────")
    _, K_current = steady_state_kalman(alpha_to_equivalent_QR(current_alpha) * R, R)
    print(f"  alpha=0.2 is equivalent to K_ss ≈ {current_alpha:.4f}")
    print(f"  Implied Q/R ratio = {alpha_to_equivalent_QR(current_alpha):.4f}")
    implied_Q = alpha_to_equivalent_QR(current_alpha) * R
    print(f"  Implied Q = {implied_Q:.3f}")

    if recommended_K:
        if abs(recommended_K - current_alpha) < 0.05:
            print(f"\n  Current alpha=0.2 is close to optimal. No change needed.")
        elif recommended_K < current_alpha:
            print(f"\n  Recommended alpha = {recommended_K:.3f}  "
                  f"(lower → more filtering, less lag for this noise level)")
        else:
            print(f"\n  Recommended alpha = {recommended_K:.3f}  "
                  f"(higher → trust sensor more, faster response)")

    print(f"\n── To send new alpha to all boards ────────────────────────────")
    if recommended_K:
        alpha_byte = max(0, min(255, int(recommended_K * 255)))
        print(f"  engine.send_config(board_ids=range(1,31), "
              f"kp=51, ki=26, kd=0, alpha={alpha_byte}, limit_signal=100, deadband=10)")
        print(f"  (alpha byte {alpha_byte} → firmware alpha = {alpha_byte/255:.3f})")

    print()

# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    noise_files, step_files = list_result_files()

    if len(sys.argv) >= 2:
        noise_path = sys.argv[1]
        step_path  = sys.argv[2] if len(sys.argv) >= 3 else None
        analyse(noise_path, step_path)
        return

    if not noise_files:
        print("No noise test results found in results/")
        print("Run:  python noise_test.py [motor_id]  first.")
        return

    # Process all available noise files, pair with step files if possible
    for nf in noise_files:
        motor_id = nf.split("motor")[-1].replace(".json", "")
        matching_step = next(
            (sf for sf in step_files if f"_motor{motor_id}_" in sf), None
        )
        analyse(nf, matching_step)


if __name__ == "__main__":
    main()
