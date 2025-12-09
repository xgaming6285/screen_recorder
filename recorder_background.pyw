"""
Universal Screen Recorder - Background Mode
- Runs completely invisible (no console window)
- Logs to file instead of printing
- Auto-restarts recording on errors
- Designed for Windows startup
"""

import subprocess
import os
import ctypes
from datetime import datetime
from pathlib import Path
import time
import sys
import logging

# === SETTINGS ===
MINUTES_PER_FILE = 60
OUTPUT_FOLDER = "recordings"
FRAMERATE = 10 
LOG_FILE = "recorder.log"

# CURSOR SETTINGS
SHOW_CURSOR = True

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT_PATH = SCRIPT_DIR / OUTPUT_FOLDER
LOG_PATH = SCRIPT_DIR / LOG_FILE

# FFmpeg path - check local folder first, then PATH
LOCAL_FFMPEG = SCRIPT_DIR / "ffmpeg.exe"
FFMPEG_CMD = str(LOCAL_FFMPEG) if LOCAL_FFMPEG.exists() else "ffmpeg"

# Setup logging to file
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log(message):
    """Log message to file"""
    logging.info(message)

def get_screen_info():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return (
        user32.GetSystemMetrics(76),  # left
        user32.GetSystemMetrics(77),  # top
        user32.GetSystemMetrics(78),  # width
        user32.GetSystemMetrics(79)   # height
    )

def test_encoder(encoder_name):
    """Checks if the hardware encoder works."""
    log(f"Testing encoder: {encoder_name}")
    cmd = [
        FFMPEG_CMD, "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360",
        "-c:v", encoder_name, "-frames:v", "1", "-f", "null", "-"
    ]
    try:
        # CREATE_NO_WINDOW flag to hide subprocess
        CREATE_NO_WINDOW = 0x08000000
        result = subprocess.run(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            log(f"Encoder {encoder_name}: OK")
            return True
        else:
            log(f"Encoder {encoder_name}: Failed")
            return False
    except FileNotFoundError:
        log(f"FFmpeg not found")
        return False

def get_optimized_settings(width, height):
    """Auto-selects the best settings."""
    # 1. NVIDIA
    if test_encoder("h264_nvenc"):
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p1",
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
    log("No GPU encoder found. Using CPU Safe Mode (50% Scale).")
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
    OUTPUT_PATH.mkdir(exist_ok=True)
    left, top, width, height = get_screen_info()
    
    log("=" * 50)
    log("Screen Recorder Started (Background Mode)")
    log(f"Screen: {width}x{height} at ({left}, {top})")
    log("=" * 50)
    
    encoder_flags = get_optimized_settings(width, height)
    
    # Flags for hidden subprocess
    CREATE_NO_WINDOW = 0x08000000
    BELOW_NORMAL_PRIORITY = 0x00004000
    CREATION_FLAGS = CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY
    
    session = 0
    while True:
        session += 1
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = str(OUTPUT_PATH / f"rec_{timestamp}.mkv")
        
        cmd = [
            FFMPEG_CMD, "-y",
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
        
        log(f"Recording session #{session} started: {filename}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATION_FLAGS
            )
            
            start_time = time.time()
            max_duration = MINUTES_PER_FILE * 60
            
            # Poll every second to check duration
            while process.poll() is None:
                elapsed = time.time() - start_time
                if elapsed >= max_duration:
                    # Time's up - gracefully stop and start new file
                    log(f"Session #{session} completed (duration limit reached)")
                    process.stdin.write(b'q')
                    process.stdin.flush()
                    process.wait()
                    break
                time.sleep(1)
            
        except Exception as e:
            log(f"Error in session #{session}: {str(e)}")
            try:
                process.terminate()
            except:
                pass
            time.sleep(5)  # Wait before retry
            continue
        
        time.sleep(1)

def main():
    """Main entry point with error recovery"""
    while True:
        try:
            record()
        except Exception as e:
            log(f"Critical error: {str(e)}. Restarting in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()

