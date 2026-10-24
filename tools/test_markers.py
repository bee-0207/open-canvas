"""Live check of app/markers.py: camera feed with detected markers + a flattened top-down view.

Usage (from the repo root, venv active; note the -m):
    python -m tools.test_markers --width-mm 279.4 --height-mm 215.9

    --width-mm / --height-mm   the picture's size between the markers (default: Letter, landscape)
    --gap-mm                   white gap between each marker and the picture edge (default 10,
                               which is right if the tile's inner corner touches the picture's corner)
    --camera                   camera index (default 0; try 1 if an iPhone Continuity Camera grabs 0)

Windows:
    camera     green outlines = markers detected this frame, dots = marker centers.
               The painting outline drawn from H should hug the real picture's edges:
               green when H was refreshed this frame, orange when an older H is being reused.
               Hover the mouse to see (u, v) at the cursor.
    flattened  the picture warped to a straight-on view. The red dot is the cursor's (u, v).
Keys: q or Esc to quit.

macOS: the first run asks for camera access for your terminal app. If frames are black,
enable it in System Settings -> Privacy & Security -> Camera, then restart the terminal.
"""

import argparse
import time

import cv2
import numpy as np

from app.markers import MarkerLayout, MarkerTracker

GREEN, ORANGE, RED, YELLOW = (0, 200, 0), (0, 140, 255), (0, 0, 255), (0, 220, 255)


def put_text(img, text, org, scale=0.6, color=(255, 255, 255)):
    """Text with a black outline so it stays readable on any background."""
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def draw_camera_view(frame, det, tracker, mouse_xy):
    view = frame.copy()

    for marker_id, quad in det.corners.items():
        cv2.polylines(view, [quad.astype(np.int32)], True, GREEN, 2)
        cx, cy = det.centers[marker_id]
        cv2.circle(view, (int(cx), int(cy)), 5, YELLOW, -1)
        put_text(view, f"ID {marker_id}", (int(cx) + 8, int(cy) - 8), color=YELLOW)

    if tracker.H is not None:
        outline = tracker.uv_to_camera([[0, 0], [1, 0], [1, 1], [0, 1]])
        cv2.polylines(view, [outline.astype(np.int32)], True, GREEN if det.updated else ORANGE, 2)

    if det.updated:
        h_state = "H: live"
    elif tracker.H is not None:
        h_state = f"H: reused ({tracker.frames_since_update} frames old)"
    else:
        h_state = "H: none yet (need all 4 markers)"
    missing = f"  missing {det.missing}" if det.missing else ""
    put_text(view, f"markers {len(det.corners)}/4{missing}   {h_state}", (10, 25))

    if mouse_xy is not None and tracker.H is not None:
        u, v = tracker.camera_to_uv(*mouse_xy)
        put_text(view, f"u={u:.3f} v={v:.3f}", (mouse_xy[0] + 12, mouse_xy[1] - 12))
    return view


def draw_flat_view(frame, tracker, mouse_xy, width_px):
    flat = tracker.flatten(frame, width_px)
    if flat is None:
        flat = np.zeros((round(width_px * 0.75), width_px, 3), np.uint8)
        put_text(flat, "waiting for all 4 markers...", (20, 40))
        return flat
    if mouse_xy is not None:
        u, v = tracker.camera_to_uv(*mouse_xy)
        h, w = flat.shape[:2]
        if 0 <= u <= 1 and 0 <= v <= 1:
            cv2.circle(flat, (int(u * w), int(v * h)), 6, RED, -1)
    return flat


def main():
    ap = argparse.ArgumentParser(description="Live test for app/markers.py")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width-mm", type=float, default=279.4)
    ap.add_argument("--height-mm", type=float, default=215.9)
    ap.add_argument("--marker-mm", type=float, default=50.0)
    ap.add_argument("--gap-mm", type=float, default=10.0)
    ap.add_argument("--flat-width", type=int, default=800, help="flattened view width in px")
    args = ap.parse_args()

    tracker = MarkerTracker(MarkerLayout(args.width_mm, args.height_mm, args.marker_mm, args.gap_mm))

    def open_camera():
        cap = cv2.VideoCapture(args.camera)
        # Request 720p; macOS may ignore this, so print what we actually got
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        return cap

    cap = open_camera()
    if not cap.isOpened():
        raise SystemExit(f"Couldn't open camera {args.camera}. On macOS, check camera permission for your terminal.")
    print(f"Camera {args.camera}: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

    mouse = {"xy": None}

    def on_mouse(event, x, y, flags, param):
        mouse["xy"] = (x, y)

    cv2.namedWindow("camera")
    cv2.setMouseCallback("camera", on_mouse)

    fps, t_prev = 0.0, time.perf_counter()
    fail_since = None
    while True:
        ok, frame = cap.read()
        if not ok:
            # USB webcams drop out briefly (bumped cable, hub hiccup): reopen instead of quitting
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

        det = tracker.update(frame)

        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)  # smoothed so the number is readable
        t_prev = now

        view = draw_camera_view(frame, det, tracker, mouse["xy"])
        put_text(view, f"{fps:.0f} fps", (10, view.shape[0] - 15))
        cv2.imshow("camera", view)
        cv2.imshow("flattened", draw_flat_view(frame, tracker, mouse["xy"], args.flat_width))

        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
