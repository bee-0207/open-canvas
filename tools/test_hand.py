"""Live check of app/hand.py: fingertip tracking, its speed, and (u, v) on the painting.

Usage (from the repo root, venv active; note the -m):
    python -m tools.test_hand --camera 0

    --camera                   camera index (the Acer was 0 with the iPhone connected; check)
    --width-mm / --height-mm   picture size between the markers, same as tools/test_markers
    --gap-mm / --marker-mm     same as tools/test_markers

Window:
    camera   hand skeleton in blue, index fingertip (landmark 8) as a red dot.
             Top line: markers found and homography state. Once all 4 markers have been
             seen, the fingertip's (u, v) on the painting is printed next to it.
             Bottom line: frame rate and how long MediaPipe took on this frame (ms).
Keys: q or Esc to quit.

Latency budget (CLAUDE.md section 11): fingertip -> sound under ~100 ms. One camera frame at
30 fps is 33 ms and audio output is ~27 ms, so hand detection should stay under ~30 ms.
"""

import argparse
import time

import cv2
import numpy as np

from app.hand import HAND_CONNECTIONS, FingertipTracker
from app.markers import MarkerLayout, MarkerTracker
from tools.test_markers import GREEN, ORANGE, RED, put_text

BLUE = (255, 140, 0)


def draw_hand(view, tip):
    pts = tip.landmarks.astype(np.int32)
    for a, b in HAND_CONNECTIONS:
        cv2.line(view, tuple(pts[a]), tuple(pts[b]), BLUE, 2)
    cv2.circle(view, (int(tip.x), int(tip.y)), 8, RED, -1)


def main():
    ap = argparse.ArgumentParser(description="Live test for app/hand.py")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width-mm", type=float, default=279.4)
    ap.add_argument("--height-mm", type=float, default=215.9)
    ap.add_argument("--marker-mm", type=float, default=50.0)
    ap.add_argument("--gap-mm", type=float, default=10.0)
    args = ap.parse_args()

    markers = MarkerTracker(MarkerLayout(args.width_mm, args.height_mm, args.marker_mm, args.gap_mm))
    hand = FingertipTracker()

    def open_camera():
        cap = cv2.VideoCapture(args.camera)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap

    cap = open_camera()
    if not cap.isOpened():
        raise SystemExit(f"Couldn't open camera {args.camera}. On macOS, check camera permission for your terminal.")
    print(f"Camera {args.camera}: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

    fps, t_prev = 0.0, time.perf_counter()
    hand_ms_log = []
    fail_since = None
    while True:
        ok, frame = cap.read()
        if not ok:
            # Same reconnect behavior as tools/test_markers
            if fail_since is None:
                fail_since = time.perf_counter()
                print("Frame grab failed, trying to reconnect...")
            if time.perf_counter() - fail_since > 10:
                print("Camera gone for 10 s (disconnected or permission denied), quitting")
                break
            cap.release()
            time.sleep(0.5)
            cap = open_camera()
            continue
        if fail_since is not None:
            print("Camera back")
            fail_since = None

        det = markers.update(frame)
        t0 = time.perf_counter()
        tip = hand.detect(frame)
        hand_ms = (time.perf_counter() - t0) * 1000
        hand_ms_log.append(hand_ms)

        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)  # smoothed so the number is readable
        t_prev = now

        view = frame.copy()
        if markers.H is not None:
            outline = markers.uv_to_camera([[0, 0], [1, 0], [1, 1], [0, 1]])
            cv2.polylines(view, [outline.astype(np.int32)], True, GREEN if det.updated else ORANGE, 2)
        h_state = "H: live" if det.updated else ("H: reused" if markers.H is not None else "H: none yet")
        put_text(view, f"markers {len(det.corners)}/4   {h_state}", (10, 25))

        if tip is not None:
            draw_hand(view, tip)
            label = f"{tip.handedness} {tip.score:.2f}"
            if markers.H is not None:
                u, v = markers.camera_to_uv(tip.x, tip.y)
                on = 0 <= u <= 1 and 0 <= v <= 1
                label = f"u={u:.3f} v={v:.3f}" + ("" if on else " (off painting)")
            put_text(view, label, (int(tip.x) + 12, int(tip.y) - 12))
        else:
            put_text(view, "no hand", (10, 55), color=RED)

        put_text(view, f"{fps:.0f} fps   hand {hand_ms:.0f} ms", (10, view.shape[0] - 15))
        cv2.imshow("camera", view)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    if hand_ms_log:
        a = np.array(hand_ms_log[10:] or hand_ms_log)  # skip the first frames (model warm-up)
        print(f"hand detect: median {np.median(a):.1f} ms, 95th pct {np.percentile(a, 95):.1f} ms, "
              f"over {len(a)} frames")
    hand.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
