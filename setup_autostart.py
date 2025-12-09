"""
Setup Script - Add Screen Recorder to Windows Startup
Run this script ONCE to enable auto-start on Windows boot.
Run with --remove to disable auto-start.
"""

import os
import sys
import winreg
from pathlib import Path

def get_pythonw_path():
    """Get the path to pythonw.exe (Python without console window)"""
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if pythonw.exists():
        return str(pythonw)
    # Fallback to same directory as python.exe
    return str(python_dir / "pythonw.exe")

def get_script_path():
    """Get the path to the background recorder script"""
    script_dir = Path(__file__).parent.resolve()
    return str(script_dir / "recorder_background.pyw")

def add_to_startup():
    """Add the recorder to Windows startup via Registry"""
    script_path = get_script_path()
    pythonw_path = get_pythonw_path()
    
    if not Path(script_path).exists():
        print(f"❌ Error: Script not found at {script_path}")
        return False
    
    # Command to run: pythonw.exe "path\to\recorder_background.pyw"
    command = f'"{pythonw_path}" "{script_path}"'
    
    try:
        # Open the Run key in the registry
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        
        # Set the value
        winreg.SetValueEx(key, "ScreenRecorder", 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        
        print("=" * 60)
        print("✅ SUCCESS! Screen Recorder added to Windows Startup")
        print("=" * 60)
        print(f"\n📍 Script location: {script_path}")
        print(f"🐍 Python: {pythonw_path}")
        print(f"\n📝 Registry entry added to:")
        print(r"   HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run")
        print(f"\n🔄 The recorder will now start automatically when Windows boots.")
        print(f"📁 Recordings will be saved to: {Path(script_path).parent / 'recordings'}")
        print(f"📋 Logs will be saved to: {Path(script_path).parent / 'recorder.log'}")
        print(f"\n💡 To remove from startup, run: python setup_autostart.py --remove")
        return True
        
    except Exception as e:
        print(f"❌ Error adding to startup: {e}")
        return False

def remove_from_startup():
    """Remove the recorder from Windows startup"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        
        try:
            winreg.DeleteValue(key, "ScreenRecorder")
            print("=" * 60)
            print("✅ Screen Recorder REMOVED from Windows Startup")
            print("=" * 60)
            print("\n🔄 The recorder will no longer start automatically.")
        except FileNotFoundError:
            print("⚠️  Screen Recorder was not in startup (nothing to remove)")
        
        winreg.CloseKey(key)
        return True
        
    except Exception as e:
        print(f"❌ Error removing from startup: {e}")
        return False

def check_status():
    """Check if recorder is in startup"""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        
        try:
            value, _ = winreg.QueryValueEx(key, "ScreenRecorder")
            print(f"✅ Screen Recorder IS in startup")
            print(f"   Command: {value}")
            return True
        except FileNotFoundError:
            print("❌ Screen Recorder is NOT in startup")
            return False
        finally:
            winreg.CloseKey(key)
            
    except Exception as e:
        print(f"❌ Error checking status: {e}")
        return False

def start_now():
    """Start the recorder immediately (in background)"""
    import subprocess
    script_path = get_script_path()
    pythonw_path = get_pythonw_path()
    
    print("🚀 Starting Screen Recorder in background...")
    subprocess.Popen(
        [pythonw_path, script_path],
        creationflags=0x00000008  # DETACHED_PROCESS
    )
    print("✅ Recorder is now running in background!")
    print(f"📁 Check {Path(script_path).parent / 'recorder.log'} for status")

def stop_recorder():
    """Stop the recorder by killing pythonw and ffmpeg processes"""
    import subprocess
    print("🛑 Stopping Screen Recorder...")
    
    # Kill pythonw first (the parent process that restarts ffmpeg)
    try:
        result = subprocess.run(
            ['taskkill', '/F', '/IM', 'pythonw.exe'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("   Stopped pythonw.exe (recorder script)")
    except:
        pass
    
    # Then kill ffmpeg
    try:
        result = subprocess.run(
            ['taskkill', '/F', '/IM', 'ffmpeg.exe'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("   Stopped ffmpeg.exe (recording process)")
    except:
        pass
    
    print("✅ Recording fully stopped")

def main():
    print("\n🎬 Screen Recorder - Auto-Start Setup\n")
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['--remove', '-r', 'remove']:
            remove_from_startup()
        elif arg in ['--status', '-s', 'status']:
            check_status()
        elif arg in ['--start', 'start']:
            start_now()
        elif arg in ['--stop', 'stop']:
            stop_recorder()
        elif arg in ['--help', '-h', 'help']:
            print("Usage: python setup_autostart.py [option]")
            print("\nOptions:")
            print("  (no option)  - Add to Windows startup")
            print("  --remove     - Remove from Windows startup")
            print("  --status     - Check if in startup")
            print("  --start      - Start recorder now (background)")
            print("  --stop       - Stop recorder")
            print("  --help       - Show this help")
        else:
            print(f"Unknown option: {arg}")
            print("Use --help for usage info")
    else:
        add_to_startup()

if __name__ == "__main__":
    main()

