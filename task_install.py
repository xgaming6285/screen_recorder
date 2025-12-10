"""
Scheduled Task Installer for Smart Motion-Activated Recorder
=============================================================
Runs the recorder as a scheduled task at user logon.
Unlike a Windows Service, this runs in the user's session and CAN capture the screen.

Features:
  - Starts automatically at user logon
  - Runs hidden (no console window)
  - Auto-restarts on failure (every 1 minute, up to 3 times)
  - Hidden from casual Task Manager inspection (runs as a system task)

Usage:
  python task_install.py install       # Install the scheduled task
  python task_install.py remove        # Remove the scheduled task
  python task_install.py start         # Start recording now
  python task_install.py stop          # Stop recording
  python task_install.py status        # Check status

IMPORTANT: Run this script as Administrator!
"""

import sys
import os
import ctypes
import subprocess
import time

# Ensure we're running as admin
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    print("ERROR: This script must be run as Administrator!")
    print("Right-click Command Prompt -> Run as Administrator")
    sys.exit(1)

# === CONFIGURATION ===
TASK_NAME = "SmartMotionRecorder"
TASK_DESCRIPTION = "Smart Motion-Activated Screen Recorder - Records screen activity using motion detection"

# Get paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDER_SCRIPT = os.path.join(SCRIPT_DIR, "recorder_simple.py")
PYTHON_EXE = sys.executable
PYTHONW_EXE = os.path.join(os.path.dirname(PYTHON_EXE), "pythonw.exe")

# Use pythonw.exe if available (no console window), otherwise python.exe
if os.path.exists(PYTHONW_EXE):
    EXEC_PATH = PYTHONW_EXE
else:
    EXEC_PATH = PYTHON_EXE
    print(f"Note: pythonw.exe not found, using python.exe (console may flash briefly)")


def run_powershell(script, capture=True):
    """Run a PowerShell script and return the result."""
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=capture,
            text=True,
            encoding='utf-8',
            errors='replace'  # Replace undecodable chars instead of crashing
        )
        return result
    except Exception as e:
        # Return a mock result on error
        class MockResult:
            stdout = ""
            stderr = str(e)
            returncode = 1
        return MockResult()


def task_exists():
    """Check if the scheduled task exists."""
    result = run_powershell(f'Get-ScheduledTask -TaskName "{TASK_NAME}" -ErrorAction SilentlyContinue')
    return result.stdout and TASK_NAME in result.stdout


def get_task_status():
    """Get the current status of the scheduled task."""
    if not task_exists():
        return "NOT INSTALLED"
    
    result = run_powershell(f'(Get-ScheduledTask -TaskName "{TASK_NAME}").State')
    return (result.stdout or "").strip() or "Unknown"


def is_recorder_running():
    """Check if the recorder process is currently running."""
    result = run_powershell(
        f'Get-Process | Where-Object {{$_.Path -like "*python*" -and $_.CommandLine -like "*recorder_simple*"}} | Select-Object Id'
    )
    return bool(result.stdout.strip())


def do_install():
    """Install the scheduled task."""
    print("\n" + "=" * 60)
    print("INSTALLING SMART MOTION RECORDER (Scheduled Task)")
    print("=" * 60)
    
    # Check if recorder script exists
    if not os.path.exists(RECORDER_SCRIPT):
        print(f"ERROR: Recorder script not found: {RECORDER_SCRIPT}")
        return False
    
    # Remove existing task if present
    if task_exists():
        print("  Removing existing task...")
        run_powershell(f'Unregister-ScheduledTask -TaskName "{TASK_NAME}" -Confirm:$false')
    
    print(f"  Creating scheduled task '{TASK_NAME}'...")
    
    # Build the PowerShell command to create the task
    # Using XML for more control over settings
    task_xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{TASK_DESCRIPTION}</Description>
    <Author>SmartRecorder</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
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
      <Command>"{EXEC_PATH}"</Command>
      <Arguments>"{RECORDER_SCRIPT}"</Arguments>
      <WorkingDirectory>{SCRIPT_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>'''
    
    # Write XML to temp file
    xml_path = os.path.join(SCRIPT_DIR, "task_temp.xml")
    with open(xml_path, 'w', encoding='utf-16') as f:
        f.write(task_xml)
    
    try:
        # Register the task using the XML
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"ERROR: {result.stderr}")
            return False
        
        print("  ✓ Task created")
        
    finally:
        # Clean up temp file
        if os.path.exists(xml_path):
            os.remove(xml_path)
    
    # Verify installation
    if not task_exists():
        print("ERROR: Task was not created properly")
        return False
    
    print("\n" + "=" * 60)
    print("✅ INSTALLATION COMPLETE")
    print("=" * 60)
    print(f"  Task Name: {TASK_NAME}")
    print(f"  Status: {get_task_status()}")
    print(f"  Executable: {EXEC_PATH}")
    print(f"  Script: {RECORDER_SCRIPT}")
    print(f"  Recordings: {os.path.join(SCRIPT_DIR, 'smart_recordings')}")
    print("\n  📋 BEHAVIOR:")
    print("     - Starts automatically at user logon")
    print("     - Runs hidden (no window)")
    print("     - Auto-restarts on crash (up to 999 times, 1 min interval)")
    print("     - Hidden from standard Task Manager view")
    print("\n  To start recording now:")
    print(f"     python {os.path.basename(__file__)} start")
    
    return True


def do_remove():
    """Remove the scheduled task."""
    print("\n" + "=" * 60)
    print("REMOVING SMART MOTION RECORDER TASK")
    print("=" * 60)
    
    if not task_exists():
        print(f"Task '{TASK_NAME}' is not installed.")
        return True
    
    # Stop if running
    do_stop(quiet=True)
    
    print("  Removing task...")
    result = run_powershell(f'Unregister-ScheduledTask -TaskName "{TASK_NAME}" -Confirm:$false')
    
    if task_exists():
        print("ERROR: Could not remove task")
        return False
    
    print("  ✓ Task removed")
    print("\n✅ Task successfully removed")
    return True


def do_start():
    """Start the recording task."""
    print(f"Starting '{TASK_NAME}'...")
    
    if not task_exists():
        print(f"Task '{TASK_NAME}' is not installed. Run 'install' first.")
        return False
    
    # Start the scheduled task
    result = subprocess.run(
        ["schtasks", "/Run", "/TN", TASK_NAME],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return False
    
    time.sleep(2)
    
    print("✅ Recording started!")
    print(f"   Recordings will be saved to: {os.path.join(SCRIPT_DIR, 'smart_recordings')}")
    return True


def do_stop(quiet=False):
    """Stop the recording task gracefully."""
    if not quiet:
        print(f"Stopping '{TASK_NAME}'...")
    
    # Create stop file to signal graceful shutdown
    stop_file = os.path.join(SCRIPT_DIR, ".stop_recording")
    
    if not quiet:
        print("  Signaling graceful shutdown...")
    
    # Create the stop file
    with open(stop_file, 'w') as f:
        f.write("stop")
    
    # Wait for process to stop gracefully (up to 10 seconds)
    for i in range(10):
        time.sleep(1)
        # Check if still running
        result = run_powershell('''
        $procs = Get-WmiObject Win32_Process | Where-Object { 
            $_.Name -like "*python*" -and $_.CommandLine -like "*recorder_simple*" 
        }
        if ($procs) { Write-Output "running" } else { Write-Output "stopped" }
        ''')
        if "stopped" in (result.stdout or ""):
            if not quiet:
                print("  ✓ Process stopped gracefully")
            break
        if not quiet and i == 4:
            print("  Still waiting for graceful shutdown...")
    else:
        # Force kill if graceful shutdown failed
        if not quiet:
            print("  Graceful shutdown timed out, force stopping...")
        kill_script = '''
        $procs = Get-WmiObject Win32_Process | Where-Object { 
            $_.Name -like "*python*" -and $_.CommandLine -like "*recorder_simple*" 
        }
        foreach ($proc in $procs) {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
        '''
        run_powershell(kill_script)
    
    # Clean up stop file
    if os.path.exists(stop_file):
        try:
            os.remove(stop_file)
        except:
            pass
    
    # Also end the task formally
    subprocess.run(
        ["schtasks", "/End", "/TN", TASK_NAME],
        capture_output=True,
        text=True
    )
    
    if not quiet:
        print("✅ Recording stopped")
    
    return True


def do_status():
    """Show task status."""
    print("\n" + "=" * 60)
    print("TASK STATUS")
    print("=" * 60)
    
    if not task_exists():
        print(f"Task '{TASK_NAME}' is NOT installed.")
        return
    
    status = get_task_status()
    print(f"  Task Name: {TASK_NAME}")
    print(f"  Task State: {status}")
    
    # Check if recorder is actually running
    result = run_powershell('''
    $procs = Get-WmiObject Win32_Process | Where-Object { 
        $_.Name -like "*python*" -and $_.CommandLine -like "*recorder_simple*" 
    }
    if ($procs) {
        foreach ($proc in $procs) {
            Write-Output "  PID: $($proc.ProcessId)"
        }
    } else {
        Write-Output "  (not running)"
    }
    ''')
    print(f"  Recorder Process: {result.stdout.strip()}")
    
    # Check recordings folder
    recordings_dir = os.path.join(SCRIPT_DIR, "smart_recordings")
    if os.path.exists(recordings_dir):
        files = os.listdir(recordings_dir)
        print(f"  Recordings: {len(files)} file(s) in {recordings_dir}")
        if files:
            # Show most recent
            files_with_time = [(f, os.path.getmtime(os.path.join(recordings_dir, f))) for f in files]
            files_with_time.sort(key=lambda x: x[1], reverse=True)
            print(f"  Latest: {files_with_time[0][0]}")
    else:
        print(f"  Recordings: (folder not yet created)")


def print_usage():
    """Print usage information."""
    print(f"""
Smart Motion Recorder - Scheduled Task Manager
===============================================

Usage: python {os.path.basename(__file__)} <command>

Commands:
  install     Install as scheduled task (starts at logon)
  remove      Remove the scheduled task
  start       Start recording now
  stop        Stop recording
  status      Show current status
  
Examples:
  python {os.path.basename(__file__)} install   # Install and configure
  python {os.path.basename(__file__)} start     # Start recording now
  python {os.path.basename(__file__)} status    # Check if running
""")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == 'install':
        success = do_install()
        sys.exit(0 if success else 1)
        
    elif command == 'remove':
        success = do_remove()
        sys.exit(0 if success else 1)
        
    elif command == 'start':
        success = do_start()
        sys.exit(0 if success else 1)
        
    elif command == 'stop':
        success = do_stop()
        sys.exit(0 if success else 1)
        
    elif command == 'status':
        do_status()
        sys.exit(0)
        
    elif command in ('--help', '-h', 'help'):
        print_usage()
        sys.exit(0)
        
    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)

