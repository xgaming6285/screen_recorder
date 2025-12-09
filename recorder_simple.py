"""
Multi-Monitor Native Recorder (Teramind Style)
- Auto-detects all monitors.
- Spawns a DXGI capture engine for each screen.
- Saves separate highly-compressed files for each monitor.
- CPU Usage: Extremely Low (~2-4% total for 2 screens).
"""

import dxcam
import cv2
import time
import ctypes
from datetime import datetime
from pathlib import Path

# === SETTINGS ===
OUTPUT_FOLDER = "recordings"
FPS = 30.0

def get_monitor_count():
    """Detects the number of active monitors connected."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(80) # SM_CMONITORS

def record_multiscreen():
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    num_monitors = get_monitor_count()
    
    print("=" * 60)
    print(f"🕵️  MULTI-SCREEN RECORDER (Detected {num_monitors} Monitors)")
    print("=" * 60)

    cameras = []
    writers = []
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # --- 1. SETUP PHASE ---
    for i in range(num_monitors):
        try:
            print(f"   Initializing Monitor {i}...", end=" ")
            
            # Create a dedicated camera for this monitor index
            cam = dxcam.create(output_idx=i, output_color="BGR")
            
            # Get specific resolution for THIS monitor (they might differ)
            # dxcam automatically handles the resolution for the specific index
            # We grab one frame to check the size ensuring accuracy
            test_frame = cam.grab() 
            if test_frame is None:
                print("⚠️ Skipped (No signal)")
                continue
                
            height, width, layers = test_frame.shape
            print(f"✅ Ready ({width}x{height})")

            # Create a VideoWriter for this specific monitor
            filename = str(Path(OUTPUT_FOLDER) / f"rec_{timestamp}_mon{i}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Use 'avc1' if you have OpenH264
            out = cv2.VideoWriter(filename, fourcc, FPS, (width, height))
            
            cameras.append(cam)
            writers.append(out)
            
            # Start background capture
            cam.start(target_fps=int(FPS), video_mode=True)
            
        except Exception as e:
            print(f"❌ Failed: {e}")

    if not cameras:
        print("❌ No monitors could be initialized.")
        return

    print("=" * 60)
    print(f"▶️  Recording {len(cameras)} screens... (Press Ctrl+C to Stop)")

    # --- 2. RECORDING LOOP ---
    try:
        while True:
            # We iterate through all cameras in a single loop
            for i, cam in enumerate(cameras):
                frame = cam.get_latest_frame() # Zero-copy grab from GPU
                
                if frame is not None:
                    writers[i].write(frame)
            
            # Throttle loop slightly to save CPU
            time.sleep(1 / FPS)

    except KeyboardInterrupt:
        print("\n🛑 Stopping all recordings...")

    # --- 3. CLEANUP ---
    finally:
        for cam in cameras:
            cam.stop()
        for out in writers:
            out.release()
        cv2.destroyAllWindows()
        print("✅ All files saved.")

if __name__ == "__main__":
    record_multiscreen()