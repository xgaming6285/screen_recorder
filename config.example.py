"""
Enterprise Recorder Configuration Template
==========================================
Copy this file to config.py and modify for your environment.
"""

from pathlib import Path

# Employee identification
# Defaults to Windows username if not set
EMPLOYEE_NAME = None  # Set to override, e.g., "john.doe"

# Recording settings
FPS = 5.0                      # Frames per second (5 is optimal for monitoring)
MOTION_THRESHOLD = 0.5         # Percentage of pixels that must change to record
CHUNK_DURATION_SECONDS = 600   # 10 minutes per file

# Local cache for offline recording
CACHE_FOLDER = Path("./cache")

# Network share path for central storage
# This should be the UNC path to your file server
# Example: \\\\SERVER\\Share  or  \\\\192.168.1.100\\Recordings
NETWORK_SHARE = r"\\OFFICE_SERVER\Recordings"

# Upload daemon settings  
UPLOAD_RETRY_INTERVAL = 30.0   # Seconds between retry attempts when network is down
UPLOAD_CHECK_INTERVAL = 5.0    # How often to check for new files to upload

# Video codec settings
# X264 = Best compression, requires OpenH264 DLL
# XVID = Good fallback, widely compatible
PREFERRED_CODEC = "X264"
FALLBACK_CODEC = "XVID"

