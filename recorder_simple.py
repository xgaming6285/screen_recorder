"""
Smart Motion-Activated Recorder (Teramind Style)
- Motion Detection: Only records when screen changes.
- Low FPS: optimized for desktop monitoring (5 FPS).
- Result: Massive file size reduction.
"""

import dxcam
import cv2
import time
import ctypes
import numpy as np
import signal
import sys
from datetime import datetime
from pathlib import Path

# === SETTINGS ===
OUTPUT_FOLDER = "smart_recordings"
FPS = 5.0                # 5 FPS is standard for employee monitoring
MOTION_THRESHOLD = 0.5   # 0.5% of pixels must change to trigger a write
CHECK_INTERVAL = 1.0 / FPS
STOP_FILE = Path(__file__).parent / ".stop_recording"

# Global flag for graceful shutdown
_should_stop = False

def get_monitor_count():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(80)


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global _should_stop
    print("\n🛑 Signal received, stopping gracefully...")
    _should_stop = True


def check_stop_signal():
    """Check if we should stop (via file or flag)."""
    global _should_stop
    if _should_stop:
        return True
    if STOP_FILE.exists():
        print("\n🛑 Stop file detected, stopping gracefully...")
        _should_stop = True
        return True
    return False

def record_smart():
    global _should_stop
    _should_stop = False
    
    # Clean up any leftover stop file
    if STOP_FILE.exists():
        STOP_FILE.unlink()
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGBREAK'):  # Windows-specific
        signal.signal(signal.SIGBREAK, signal_handler)
    
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    num_monitors = get_monitor_count()
    
    print("=" * 60)
    print(f"🧠 SMART RECORDER (Motion Activated)")
    print(f"   Target FPS: {FPS} | Monitors: {num_monitors}")
    print("=" * 60)

    cameras = []
    writers = []
    last_frames = [] # To store the previous frame for comparison

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # --- SETUP ---
    for i in range(num_monitors):
        cam = dxcam.create(output_idx=i, output_color="BGR")
        
        # Grab one frame to get size
        frame = cam.grab()
        if frame is None: continue
        height, width, _ = frame.shape
        
        # Use 'mp4v'. If you have the DLL for H264, use 'avc1' for even smaller files.
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        filename = str(Path(OUTPUT_FOLDER) / f"smart_{timestamp}_mon{i}.mp4")
        
        out = cv2.VideoWriter(filename, fourcc, FPS, (width, height))
        
        cameras.append(cam)
        writers.append(out)
        last_frames.append(None) # Initialize "previous frame" as empty
        
        cam.start(target_fps=int(FPS), video_mode=True)
        print(f"   ✅ Monitor {i} Ready")

    print(f"▶️  Recording... (Static screens will be ignored)")

    try:
        while not check_stop_signal():
            start_loop = time.time()

            for i, cam in enumerate(cameras):
                # Get current frame
                frame = cam.get_latest_frame()
                if frame is None: continue

                # --- MOTION DETECTION LOGIC ---
                should_write = False
                
                # If we have a previous frame, compare them
                if last_frames[i] is not None:
                    # 1. Convert to Gray for fast math (saves CPU)
                    curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    prev_gray = cv2.cvtColor(last_frames[i], cv2.COLOR_BGR2GRAY)
                    
                    # 2. Calculate the difference (Absolute Difference)
                    diff = cv2.absdiff(curr_gray, prev_gray)
                    
                    # 3. Threshold the difference (ignore tiny noise)
                    # Any pixel change > 25 (out of 255) is considered "changed"
                    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
                    
                    # 4. Count changed pixels
                    changed_pixels = np.count_nonzero(thresh)
                    total_pixels = frame.shape[0] * frame.shape[1]
                    change_percent = (changed_pixels / total_pixels) * 100

                    # 5. Decide to write
                    if change_percent > MOTION_THRESHOLD:
                        should_write = True
                else:
                    # Always write the very first frame
                    should_write = True

                # --- WRITING ---
                if should_write:
                    writers[i].write(frame)
                    last_frames[i] = frame.copy() # Update reference frame
                else:
                    # OPTIONAL: If you want the video to keep 'real time' accuracy 
                    # but look frozen, you duplicate the previous frame. 
                    # HOWEVER, to save space (Teramind style), we just skip writing.
                    # Note: Skipping writing makes the video 'fast forward' through boring parts.
                    pass

            # Maintain the 5 FPS timing
            elapsed = time.time() - start_loop
            if elapsed < CHECK_INTERVAL:
                time.sleep(CHECK_INTERVAL - elapsed)

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")

    finally:
        print("   Finalizing video files...")
        for cam in cameras: 
            try:
                cam.stop()
            except:
                pass
        for out in writers: 
            try:
                out.release()
            except:
                pass
        cv2.destroyAllWindows()
        # Clean up stop file
        if STOP_FILE.exists():
            try:
                STOP_FILE.unlink()
            except:
                pass
        print("✅ Done. Videos saved properly.")

if __name__ == "__main__":
    record_smart()