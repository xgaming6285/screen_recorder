"""
Native "Teramind-Style" Recorder
- Capture: DXGI (GPU-based, 0% CPU copy)
- Encode: OpenCV Internal (No external ffmpeg.exe)
- Process: Single process (Stealthier)
"""

import dxcam
import cv2
import time
import ctypes
from datetime import datetime
from pathlib import Path

# === SETTINGS ===
OUTPUT_FOLDER = "recordings"
FPS = 30.0  # DXGI is fast; 30 FPS is easy.

def get_screen_resolution():
    """Get screen size using Windows API (Handles DPI scaling)."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def record_native():
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    width, height = get_screen_resolution()
    
    print("=" * 60)
    print(f"🕵️  NATIVE RECORDER (DXGI + Internal Encode)")
    print(f"    Screen: {width}x{height} | Target FPS: {FPS}")
    print("=" * 60)

    # 1. Initialize DXGI Camera (The "Teramind" Capture Method)
    # output_color="BGR" is crucial because OpenCV uses BGR format.
    # This prevents us from needing to convert colors manually (saving CPU).
    try:
        camera = dxcam.create(output_idx=0, output_color="BGR")
    except Exception as e:
        print(f"❌ DXGI Error: {e}")
        return

    # 2. Setup Video Writer (The "Internal" Encoder)
    # We use 'mp4v' (ISO MPEG-4) which is widely supported and decent speed.
    # For maximum stealth/compression, Teramind uses H.264, but that requires
    # specific DLLs (openh264) to be present for OpenCV. 
    # 'mp4v' is safe and works out of the box.
    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = str(Path(OUTPUT_FOLDER) / f"rec_{timestamp}.mp4")

    # Create the writer object
    out = cv2.VideoWriter(filename, fourcc, FPS, (width, height))

    if not out.isOpened():
        print("❌ Error: Could not open video writer.")
        return

    print(f"▶️  Recording to {filename}...")
    print("    (Press 'q' in the preview window to stop, or Ctrl+C here)")

    # Start the background capture
    camera.start(target_fps=int(FPS), video_mode=True)

    try:
        while True:
            # A. Grab frame from GPU memory
            # This is a direct memory view, not a copy. Very fast.
            frame = camera.get_latest_frame()

            # B. Write to video
            if frame is not None:
                out.write(frame)
                
                # OPTIONAL: Show a preview window (Like a debug mode)
                # Comment these 3 lines out for "Silent/Hidden" mode
                # cv2.imshow("Recorder Preview", frame)
                # if cv2.waitKey(1) == ord('q'):
                #     break

            # Small sleep to yield CPU time to other processes
            # (Teramind does this to stay 'nice' to the system)
            time.sleep(1 / FPS)

    except KeyboardInterrupt:
        print("\n🛑 Stopping recording...")

    finally:
        # Cleanup
        camera.stop()
        out.release()
        cv2.destroyAllWindows()
        print("✅ Video saved. Exiting.")

if __name__ == "__main__":
    record_native()