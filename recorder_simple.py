"""
Universal Screen Recorder - Final Polish
- Fixed: Removed aggressive latency flags to reduce cursor flicker.
- Option: Set SHOW_CURSOR = False for a 100% flicker-free experience.
- Priority: Keeps Windows UI smooth even while recording.
"""

import subprocess
import os
import ctypes
from datetime import datetime
from pathlib import Path
import time
import sys

# === SETTINGS ===
MINUTES_PER_FILE = 60
OUTPUT_FOLDER = "recordings"
FRAMERATE = 10 

# CURSOR SETTINGS
# True  = Cursor is recorded, but it might blink/flicker on your screen.
# False = Cursor is INVISIBLE in video, but your screen will be perfect (No flicker).
SHOW_CURSOR = True

def get_screen_info():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return (
        user32.GetSystemMetrics(76), # left
        user32.GetSystemMetrics(77), # top
        user32.GetSystemMetrics(78), # width
        user32.GetSystemMetrics(79)  # height
    )

def test_encoder(encoder_name):
    """Checks if the hardware encoder works."""
    print(f"   Testing {encoder_name}...", end=" ", flush=True)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360",
        "-c:v", encoder_name, "-frames:v", "1", "-f", "null", "-"
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            print("✅ OK")
            return True
        else:
            print("❌ Failed")
            return False
    except FileNotFoundError:
        return False

def get_optimized_settings(width, height):
    """
    Auto-selects the best settings.
    Removed '-zerolatency' to help with cursor flickering.
    """
    # 1. NVIDIA
    if test_encoder("h264_nvenc"):
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p1",       # Fastest preset
            "-cq", "30",
            "-pix_fmt", "yuv420p"
        ]

    # 2. AMD
    if test_encoder("h264_amf"):
        return [
            "-c:v", "h264_amf",
            "-quality", "speed",
            "-pix_fmt", "yuv420p"
        ]

    # 3. INTEL
    if test_encoder("h264_qsv"):
        return [
            "-c:v", "h264_qsv",
            "-preset", "veryfast",
            "-global_quality", "30",
            "-pix_fmt", "nv12"
        ]

    # 4. CPU FALLBACK
    print("   ⚠️  No GPU found. Using CPU Safe Mode (50% Scale).")
    new_w = int(width * 0.5)
    new_h = int(height * 0.5)
    if new_w % 2 != 0: new_w += 1
    if new_h % 2 != 0: new_h += 1
    
    return [
        "-vf", f"scale={new_w}:{new_h}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p"
    ]

def record():
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
    left, top, width, height = get_screen_info()
    
    print("=" * 60)
    print("🕵️  HARDWARE AUTO-DETECT")
    encoder_flags = get_optimized_settings(width, height)
    print("=" * 60)
    
    # Priority: BELOW_NORMAL (Keep UI smooth)
    PRIORITY_FLAG = 0x00004000
    
    session = 0
    while True:
        session += 1
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(OUTPUT_FOLDER, f"rec_{timestamp}.mkv")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-thread_queue_size", "512", 
            "-framerate", str(FRAMERATE),
            "-draw_mouse", "1" if SHOW_CURSOR else "0",
            "-offset_x", str(left),
            "-offset_y", str(top),
            "-video_size", f"{width}x{height}",
            "-i", "desktop",
        ] + encoder_flags + [
            filename
        ]
        
        print(f"\n▶️  Recording #{session}...")
        
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=sys.stdout,
            stderr=subprocess.STDOUT,
            creationflags=PRIORITY_FLAG 
        )
        
        start_time = time.time()
        max_duration = MINUTES_PER_FILE * 60
        stopped_by_user = False
        
        try:
            # Poll every second to check duration OR if user pressed Ctrl+C
            while process.poll() is None:
                elapsed = time.time() - start_time
                if elapsed >= max_duration:
                    # Time's up - gracefully stop and start new file
                    process.stdin.write(b'q')
                    process.stdin.flush()
                    process.wait()
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            stopped_by_user = True
            print("\n⏳ Finalizing video file...")
            process.stdin.write(b'q')
            process.stdin.flush()
            process.wait()
            print("🛑 Stopped. Video file saved correctly.")
        
        if stopped_by_user:
            break
        
        time.sleep(1)

if __name__ == "__main__":
    record()