"""
Enterprise Screen Recorder - Production Ready
=============================================
Features:
- MKV container (resilient to crashes)
- 10-minute file chunking
- Lock screen detection (pause on lock, resume on unlock)
- Local cache with background upload to network share
- Automatic offline recovery
"""

import dxcam
import cv2
import time
import ctypes
import ctypes.wintypes
import numpy as np
import signal
import sys
import os
import shutil
import threading
import queue
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import IntEnum


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class RecorderConfig:
    """Central configuration for the enterprise recorder."""
    # Employee identification
    employee_name: str = os.environ.get("USERNAME", "unknown_user")
    
    # Recording settings
    fps: float = 5.0
    motion_threshold: float = 0.5  # Percentage of pixels that must change
    chunk_duration_seconds: int = 600  # 10 minutes = 600 seconds
    
    # Paths
    cache_folder: Path = Path("./cache")
    network_share: str = r"\\OFFICE_SERVER\Recordings"  # Maps to E:/recordings on server
    
    # Upload settings
    upload_retry_interval: float = 30.0  # Seconds between retry attempts
    upload_check_interval: float = 5.0   # How often to check for files to upload
    
    # Codec settings (MKV with H264 or fallback)
    preferred_codec: str = "X264"  # Try H264 first
    fallback_codec: str = "XVID"   # Fallback to XVID
    
    @property
    def employee_network_path(self) -> Path:
        """Full path to employee's folder on network share."""
        return Path(self.network_share) / self.employee_name
    
    @property
    def local_cache_path(self) -> Path:
        """Resolved local cache path."""
        return self.cache_folder.resolve()


# ============================================================================
# WINDOWS SESSION MONITORING (Lock/Unlock Detection)
# ============================================================================

class SessionState(IntEnum):
    """Windows session states."""
    ACTIVE = 0
    LOCKED = 1
    UNKNOWN = 2


class WTS_SESSION_NOTIFICATION(ctypes.Structure):
    """Structure for session change notifications."""
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("dwSessionId", ctypes.wintypes.DWORD),
    ]


# Windows API constants
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0


class SessionMonitor:
    """
    Monitors Windows session state (lock/unlock) using ctypes.
    This is a polling-based approach for simplicity.
    """
    
    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._last_input_info = self._create_last_input_info()
        
    def _create_last_input_info(self):
        """Create LASTINPUTINFO structure."""
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("dwTime", ctypes.c_uint),
            ]
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        return lii
    
    def is_session_locked(self) -> bool:
        """
        Check if the Windows session is locked.
        Uses OpenInputDesktop - returns None if desktop is locked.
        """
        # Try to open the input desktop
        hDesk = self._user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        
        if hDesk == 0:
            # Cannot open desktop = locked or no access
            return True
        else:
            # Desktop is open = not locked
            self._user32.CloseDesktop(hDesk)
            return False
    
    def get_session_state(self) -> SessionState:
        """Get current session state."""
        try:
            if self.is_session_locked():
                return SessionState.LOCKED
            return SessionState.ACTIVE
        except Exception:
            return SessionState.UNKNOWN
    
    def wait_for_unlock(self, check_interval: float = 1.0) -> None:
        """Block until the session is unlocked."""
        while self.is_session_locked():
            time.sleep(check_interval)


# ============================================================================
# UPLOAD DAEMON (Background Thread)
# ============================================================================

class UploadDaemon(threading.Thread):
    """
    Background thread that continuously monitors the cache folder
    and uploads completed files to the network share.
    
    Features:
    - Non-blocking uploads (never interrupts recording)
    - Automatic retry on network failure
    - Maintains upload queue
    """
    
    def __init__(self, config: RecorderConfig, logger: logging.Logger):
        super().__init__(daemon=True, name="UploadDaemon")
        self.config = config
        self.logger = logger
        self._stop_event = threading.Event()
        self._upload_queue: queue.Queue = queue.Queue()
        self._currently_recording: set = set()  # Files being written to
        self._lock = threading.Lock()
        
    def stop(self):
        """Signal the daemon to stop."""
        self._stop_event.set()
        
    def mark_file_recording(self, filepath: Path):
        """Mark a file as currently being recorded (don't upload yet)."""
        with self._lock:
            self._currently_recording.add(str(filepath.resolve()))
            
    def mark_file_complete(self, filepath: Path):
        """Mark a file as complete and ready for upload."""
        with self._lock:
            resolved = str(filepath.resolve())
            if resolved in self._currently_recording:
                self._currently_recording.discard(resolved)
            # Add to priority upload queue
            self._upload_queue.put(filepath)
            self.logger.info(f"📤 Queued for upload: {filepath.name}")
    
    def _is_file_ready(self, filepath: Path) -> bool:
        """Check if file is ready for upload (not being recorded)."""
        with self._lock:
            return str(filepath.resolve()) not in self._currently_recording
    
    def _ensure_network_folder(self) -> bool:
        """Ensure the employee's network folder exists."""
        try:
            target_folder = self.config.employee_network_path
            target_folder.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            self.logger.debug(f"Cannot access network: {e}")
            return False
    
    def _upload_file(self, filepath: Path) -> bool:
        """
        Upload a single file to the network share.
        Returns True on success, False on failure.
        """
        if not filepath.exists():
            self.logger.warning(f"File disappeared: {filepath}")
            return True  # File gone, consider it "handled"
            
        try:
            target_folder = self.config.employee_network_path
            target_path = target_folder / filepath.name
            
            # Ensure folder exists
            target_folder.mkdir(parents=True, exist_ok=True)
            
            # Copy first, then delete (safer than move)
            self.logger.info(f"📤 Uploading: {filepath.name} -> {target_folder}")
            shutil.copy2(filepath, target_path)
            
            # Verify the copy
            if target_path.exists() and target_path.stat().st_size == filepath.stat().st_size:
                # Success - delete local cache
                filepath.unlink()
                self.logger.info(f"✅ Uploaded & cleaned: {filepath.name}")
                return True
            else:
                self.logger.warning(f"⚠️ Size mismatch after copy: {filepath.name}")
                return False
                
        except PermissionError:
            self.logger.debug(f"Permission denied (network may be down): {filepath.name}")
            return False
        except OSError as e:
            self.logger.debug(f"Network error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Upload failed: {filepath.name} - {e}")
            return False
    
    def _scan_cache_folder(self) -> List[Path]:
        """Scan cache folder for any pending .mkv files."""
        try:
            cache = self.config.local_cache_path
            if not cache.exists():
                return []
            
            files = []
            for f in cache.glob("*.mkv"):
                if self._is_file_ready(f):
                    files.append(f)
            
            # Sort by modification time (oldest first)
            files.sort(key=lambda x: x.stat().st_mtime)
            return files
        except Exception:
            return []
    
    def run(self):
        """Main daemon loop."""
        self.logger.info("🚀 Upload daemon started")
        
        pending_files: List[Path] = []
        last_network_check = 0
        network_available = False
        
        while not self._stop_event.is_set():
            try:
                # Check for priority uploads from queue
                try:
                    while True:
                        priority_file = self._upload_queue.get_nowait()
                        if priority_file not in pending_files:
                            pending_files.insert(0, priority_file)
                except queue.Empty:
                    pass
                
                # Periodic scan of cache folder for any missed files
                current_time = time.time()
                if current_time - last_network_check > self.config.upload_retry_interval:
                    scanned = self._scan_cache_folder()
                    for f in scanned:
                        if f not in pending_files:
                            pending_files.append(f)
                    last_network_check = current_time
                    
                    # Check network availability
                    network_available = self._ensure_network_folder()
                    if not network_available and pending_files:
                        self.logger.debug(f"⏳ Network unavailable. {len(pending_files)} files pending.")
                
                # Process pending files if network is available
                if network_available and pending_files:
                    # Process one file at a time to not block too long
                    filepath = pending_files[0]
                    if self._upload_file(filepath):
                        pending_files.pop(0)
                    else:
                        # Failed - will retry on next cycle
                        network_available = False  # Assume network issue
                        
            except Exception as e:
                self.logger.error(f"Upload daemon error: {e}")
            
            # Sleep before next check
            self._stop_event.wait(self.config.upload_check_interval)
        
        # Final upload attempt on shutdown
        self.logger.info("🛑 Upload daemon shutting down, final sync...")
        for filepath in pending_files[:]:
            if self._upload_file(filepath):
                pending_files.remove(filepath)
        
        if pending_files:
            self.logger.warning(f"⚠️ {len(pending_files)} files remain in cache (will upload on next run)")
        
        self.logger.info("✅ Upload daemon stopped")


# ============================================================================
# VIDEO WRITER WRAPPER
# ============================================================================

class ChunkedVideoWriter:
    """
    Manages video writing with automatic chunking every N seconds.
    Handles MKV format and proper file naming.
    """
    
    def __init__(
        self,
        config: RecorderConfig,
        monitor_index: int,
        frame_size: Tuple[int, int],
        upload_daemon: UploadDaemon,
        logger: logging.Logger,
    ):
        self.config = config
        self.monitor_index = monitor_index
        self.frame_size = frame_size  # (width, height)
        self.upload_daemon = upload_daemon
        self.logger = logger
        
        self._current_writer: Optional[cv2.VideoWriter] = None
        self._current_filepath: Optional[Path] = None
        self._chunk_start_time: float = 0
        self._chunk_start_epoch: int = 0
        self._frame_count: int = 0
        self._fourcc = self._get_fourcc()
        
        # Ensure cache folder exists
        self.config.local_cache_path.mkdir(parents=True, exist_ok=True)
        
    def _get_fourcc(self) -> int:
        """Get the best available codec."""
        # For MKV, we can use various codecs
        # X264 gives best compression, XVID is fallback
        try:
            fourcc = cv2.VideoWriter_fourcc(*self.config.preferred_codec)
            return fourcc
        except:
            return cv2.VideoWriter_fourcc(*self.config.fallback_codec)
    
    def _generate_filename(self, start_epoch: int, end_epoch: int) -> str:
        """Generate filename following naming convention."""
        # rec_{EMPLOYEE_NAME}_{START_EPOCH}_{END_EPOCH}_mon{N}.mkv
        return f"rec_{self.config.employee_name}_{start_epoch}_{end_epoch}_mon{self.monitor_index}.mkv"
    
    def _start_new_chunk(self):
        """Start a new video chunk."""
        self._chunk_start_time = time.time()
        self._chunk_start_epoch = int(self._chunk_start_time)
        self._frame_count = 0
        
        # Create temporary filename (will be renamed on close)
        temp_name = f"recording_{self.config.employee_name}_{self._chunk_start_epoch}_mon{self.monitor_index}.mkv"
        self._current_filepath = self.config.local_cache_path / temp_name
        
        # Create video writer
        width, height = self.frame_size
        self._current_writer = cv2.VideoWriter(
            str(self._current_filepath),
            self._fourcc,
            self.config.fps,
            (width, height)
        )
        
        if not self._current_writer.isOpened():
            raise RuntimeError(f"Failed to create video writer: {self._current_filepath}")
        
        # Mark as recording (don't upload yet)
        self.upload_daemon.mark_file_recording(self._current_filepath)
        
        self.logger.info(f"🎬 Started new chunk: {self._current_filepath.name}")
    
    def _finalize_current_chunk(self) -> Optional[Path]:
        """Finalize and rename the current chunk."""
        if self._current_writer is None:
            return None
            
        old_path = self._current_filepath
        
        # Release the writer
        self._current_writer.release()
        self._current_writer = None
        
        if old_path is None or not old_path.exists():
            return None
        
        # Calculate end epoch
        end_epoch = int(time.time())
        
        # Generate final filename
        final_name = self._generate_filename(self._chunk_start_epoch, end_epoch)
        final_path = self.config.local_cache_path / final_name
        
        # Rename the file
        try:
            old_path.rename(final_path)
            self.logger.info(f"✅ Finalized chunk: {final_name} ({self._frame_count} frames)")
            
            # Mark as complete for upload
            self.upload_daemon.mark_file_complete(final_path)
            
            return final_path
        except Exception as e:
            self.logger.error(f"Failed to rename chunk: {e}")
            # Still try to upload the old file
            self.upload_daemon.mark_file_complete(old_path)
            return old_path
    
    def write_frame(self, frame: np.ndarray) -> Optional[Path]:
        """
        Write a frame to the current chunk.
        Returns the finalized chunk path if a new chunk was started.
        """
        current_time = time.time()
        finalized_path = None
        
        # Check if we need to start a new chunk
        if self._current_writer is None:
            self._start_new_chunk()
        elif current_time - self._chunk_start_time >= self.config.chunk_duration_seconds:
            # Chunk duration exceeded - finalize and start new
            finalized_path = self._finalize_current_chunk()
            self._start_new_chunk()
        
        # Write the frame
        if self._current_writer is not None:
            self._current_writer.write(frame)
            self._frame_count += 1
        
        return finalized_path
    
    def close(self) -> Optional[Path]:
        """Close the writer and finalize any pending chunk."""
        return self._finalize_current_chunk()


# ============================================================================
# MAIN RECORDER CLASS
# ============================================================================

class EnterpriseRecorder:
    """
    Production-ready enterprise screen recorder.
    
    Features:
    - MKV container format (crash-resilient)
    - Automatic 10-minute chunking
    - Lock screen detection (pause/resume)
    - Local cache with background upload
    - Multi-monitor support
    - Motion detection
    """
    
    def __init__(self, config: Optional[RecorderConfig] = None):
        self.config = config or RecorderConfig()
        self._setup_logging()
        
        self._should_stop = False
        self._is_recording = False
        self._session_monitor = SessionMonitor()
        self._upload_daemon: Optional[UploadDaemon] = None
        self._cameras: List = []
        self._writers: List[ChunkedVideoWriter] = []
        self._last_frames: List[Optional[np.ndarray]] = []
        
    def _setup_logging(self):
        """Configure logging."""
        self.logger = logging.getLogger("EnterpriseRecorder")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            self.logger.addHandler(handler)
            
            # Also log to file
            log_file = self.config.local_cache_path / "recorder.log"
            self.config.local_cache_path.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            ))
            self.logger.addHandler(file_handler)
    
    def _get_monitor_count(self) -> int:
        """Get the number of connected monitors."""
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(80)  # SM_CMONITORS
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        self.logger.info("🛑 Termination signal received")
        self._should_stop = True
    
    def _setup_signals(self):
        """Register signal handlers."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, self._signal_handler)
    
    def _detect_motion(self, current_frame: np.ndarray, previous_frame: Optional[np.ndarray]) -> bool:
        """
        Detect if there's significant motion between frames.
        Returns True if motion exceeds threshold.
        """
        if previous_frame is None:
            return True  # Always record first frame
        
        # Convert to grayscale for faster comparison
        curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate absolute difference
        diff = cv2.absdiff(curr_gray, prev_gray)
        
        # Threshold to ignore minor noise
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        
        # Calculate percentage of changed pixels
        changed_pixels = np.count_nonzero(thresh)
        total_pixels = current_frame.shape[0] * current_frame.shape[1]
        change_percent = (changed_pixels / total_pixels) * 100
        
        return change_percent > self.config.motion_threshold
    
    def _initialize_cameras(self) -> bool:
        """Initialize cameras and writers for all monitors."""
        num_monitors = self._get_monitor_count()
        self.logger.info(f"📺 Detected {num_monitors} monitor(s)")
        
        self._cameras = []
        self._writers = []
        self._last_frames = []
        
        for i in range(num_monitors):
            try:
                cam = dxcam.create(output_idx=i, output_color="BGR")
                
                # Grab initial frame to get dimensions
                frame = cam.grab()
                if frame is None:
                    self.logger.warning(f"⚠️ Monitor {i}: Could not grab frame, skipping")
                    continue
                
                height, width, _ = frame.shape
                self.logger.info(f"   Monitor {i}: {width}x{height}")
                
                # Create chunked video writer
                writer = ChunkedVideoWriter(
                    config=self.config,
                    monitor_index=i,
                    frame_size=(width, height),
                    upload_daemon=self._upload_daemon,
                    logger=self.logger,
                )
                
                # Start camera capture
                cam.start(target_fps=int(self.config.fps), video_mode=True)
                
                self._cameras.append(cam)
                self._writers.append(writer)
                self._last_frames.append(None)
                
                self.logger.info(f"   ✅ Monitor {i} ready")
                
            except Exception as e:
                self.logger.error(f"   ❌ Monitor {i} failed: {e}")
        
        return len(self._cameras) > 0
    
    def _cleanup_cameras(self):
        """Stop cameras and finalize all writers."""
        self.logger.info("🧹 Cleaning up...")
        
        # Finalize all writers (this queues files for upload)
        for writer in self._writers:
            try:
                writer.close()
            except Exception as e:
                self.logger.error(f"Error closing writer: {e}")
        
        # Stop all cameras
        for cam in self._cameras:
            try:
                cam.stop()
            except Exception:
                pass
        
        self._cameras = []
        self._writers = []
        self._last_frames = []
        
        cv2.destroyAllWindows()
    
    def _recording_loop(self):
        """Main recording loop for one session (between lock/unlock)."""
        check_interval = 1.0 / self.config.fps
        
        while not self._should_stop:
            loop_start = time.time()
            
            # Check for lock screen
            if self._session_monitor.is_session_locked():
                self.logger.info("🔒 Screen locked, pausing recording...")
                return  # Exit loop to trigger cleanup and wait
            
            # Process each camera
            for i, cam in enumerate(self._cameras):
                try:
                    frame = cam.get_latest_frame()
                    if frame is None:
                        continue
                    
                    # Motion detection
                    if self._detect_motion(frame, self._last_frames[i]):
                        self._writers[i].write_frame(frame)
                        self._last_frames[i] = frame.copy()
                    # else: skip frame (saves space, fast-forwards through static)
                    
                except Exception as e:
                    self.logger.error(f"Frame error on monitor {i}: {e}")
            
            # Maintain target FPS
            elapsed = time.time() - loop_start
            if elapsed < check_interval:
                time.sleep(check_interval - elapsed)
    
    def run(self):
        """
        Main entry point. Runs the recording loop with lock screen handling.
        """
        self._should_stop = False
        self._setup_signals()
        
        self.logger.info("=" * 60)
        self.logger.info("🏢 ENTERPRISE SCREEN RECORDER")
        self.logger.info(f"   Employee: {self.config.employee_name}")
        self.logger.info(f"   FPS: {self.config.fps}")
        self.logger.info(f"   Chunk Duration: {self.config.chunk_duration_seconds}s")
        self.logger.info(f"   Cache: {self.config.local_cache_path}")
        self.logger.info(f"   Network: {self.config.employee_network_path}")
        self.logger.info("=" * 60)
        
        # Ensure cache folder exists
        self.config.local_cache_path.mkdir(parents=True, exist_ok=True)
        
        # Start upload daemon
        self._upload_daemon = UploadDaemon(self.config, self.logger)
        self._upload_daemon.start()
        
        try:
            while not self._should_stop:
                # Wait if session is locked
                if self._session_monitor.is_session_locked():
                    self.logger.info("🔒 Waiting for unlock...")
                    while self._session_monitor.is_session_locked() and not self._should_stop:
                        time.sleep(1.0)  # Low CPU when locked
                    
                    if self._should_stop:
                        break
                    
                    self.logger.info("🔓 Session unlocked, resuming...")
                
                # Initialize cameras for this recording session
                if not self._initialize_cameras():
                    self.logger.error("❌ No cameras available, retrying in 5s...")
                    time.sleep(5)
                    continue
                
                self.logger.info("▶️  Recording started...")
                self._is_recording = True
                
                try:
                    self._recording_loop()
                finally:
                    self._is_recording = False
                    self._cleanup_cameras()
                    
        except KeyboardInterrupt:
            self.logger.info("🛑 Interrupted by user")
        except Exception as e:
            self.logger.error(f"❌ Fatal error: {e}")
            raise
        finally:
            # Final cleanup
            if self._is_recording:
                self._cleanup_cameras()
            
            # Stop upload daemon (will do final sync)
            if self._upload_daemon:
                self._upload_daemon.stop()
                self._upload_daemon.join(timeout=30)  # Wait up to 30s for uploads
            
            self.logger.info("✅ Recorder stopped")


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point with optional config overrides."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enterprise Screen Recorder")
    parser.add_argument("--employee", "-e", help="Employee name (default: Windows username)")
    parser.add_argument("--fps", type=float, default=5.0, help="Frames per second (default: 5)")
    parser.add_argument("--chunk", type=int, default=600, help="Chunk duration in seconds (default: 600)")
    parser.add_argument("--cache", default="./cache", help="Local cache folder (default: ./cache)")
    parser.add_argument("--network", default=r"\\OFFICE_SERVER\Recordings", 
                        help="Network share path (default: \\\\OFFICE_SERVER\\Recordings)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Build config
    config = RecorderConfig(
        fps=args.fps,
        chunk_duration_seconds=args.chunk,
        cache_folder=Path(args.cache),
        network_share=args.network,
    )
    
    if args.employee:
        config.employee_name = args.employee
    
    # Create and run recorder
    recorder = EnterpriseRecorder(config)
    
    if args.debug:
        recorder.logger.setLevel(logging.DEBUG)
    
    recorder.run()


if __name__ == "__main__":
    main()

