"""
Windows Service Installer for Smart Motion-Activated Recorder
==============================================================
Features:
  - Wraps recorder_simple.py as a Windows Service
  - Auto-recovery on failure (immediate restart)
  - ACL hardening to prevent Administrators from stopping/deleting

Usage:
  python service_install.py install       # Install and harden the service
  python service_install.py remove        # Remove (must unlock first)
  python service_install.py start         # Start the service
  python service_install.py stop          # Stop the service (if unlocked)
  python service_install.py remove_protection  # Unlock for maintenance
  python service_install.py status        # Check service status

IMPORTANT: Run this script as Administrator!
"""

import sys
import os
import time
import ctypes
import logging
from ctypes import wintypes

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

import win32serviceutil
import win32service
import win32event
import win32api
import win32con
import win32security
import servicemanager
import socket
import subprocess

# === SERVICE CONFIGURATION ===
SERVICE_NAME = "SmartMotionRecorder"
SERVICE_DISPLAY_NAME = "Smart Motion-Activated Screen Recorder"
SERVICE_DESCRIPTION = "Records screen activity using motion detection. Optimized for monitoring."

# Get the directory where this script lives
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDER_SCRIPT = os.path.join(SCRIPT_DIR, "recorder_simple.py")
LOG_FILE = os.path.join(SCRIPT_DIR, "service.log")

# === SDDL SECURITY DESCRIPTORS ===
# Hardened SDDL: 
#   - SYSTEM (SY): Full control
#   - Administrators (BA): Read-only (query status, enumerate dependents)
#   - DENY Administrators: Stop, Pause, Delete
#
# Rights used:
#   CC = SERVICE_QUERY_CONFIG, DC = SERVICE_CHANGE_CONFIG
#   LC = SERVICE_QUERY_STATUS, SW = SERVICE_ENUMERATE_DEPENDENTS
#   RP = SERVICE_START, WP = SERVICE_STOP, DT = SERVICE_PAUSE_CONTINUE
#   LO = SERVICE_INTERROGATE, CR = SERVICE_USER_DEFINED_CONTROL
#   SD = DELETE, RC = READ_CONTROL, WD = WRITE_DAC, WO = WRITE_OWNER

SDDL_HARDENED = (
    "D:"
    "(D;;WPDTSD;;;BA)"           # DENY Administrators: Stop (WP), Pause (DT), Delete (SD)
    "(A;;CCLCSWLORPRC;;;BA)"     # ALLOW Administrators: Query, Enumerate, Interrogate, Start (RP), Read
    "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)"  # ALLOW SYSTEM: Full control
)

# Default SDDL (unlocked - normal admin access)
SDDL_DEFAULT = (
    "D:"
    "(A;;CCLCSWRPWPDTLOCRRC;;;SY)"  # SYSTEM: Full control
    "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"  # Administrators: Full control
    "(A;;CCLCSWLOCRRC;;;IU)"        # Interactive Users: Read access
)


# ============================================================================
# SERVICE CLASS
# ============================================================================
class SmartRecorderService(win32serviceutil.ServiceFramework):
    """Windows Service wrapper for the Smart Motion Recorder."""
    
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.process = None
        
        # Setup logging
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('SmartRecorderService')
    
    def SvcStop(self):
        """Called when the service is asked to stop."""
        self.logger.info("Service stop requested")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False
        
        # Terminate the recorder subprocess
        if self.process and self.process.poll() is None:
            self.logger.info("Terminating recorder subprocess...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
    
    def SvcDoRun(self):
        """Main service entry point."""
        self.logger.info(f"Service starting. Script: {RECORDER_SCRIPT}")
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        self.main()
    
    def main(self):
        """Main service logic - runs the recorder script."""
        python_exe = sys.executable
        
        while self.running:
            try:
                self.logger.info("Starting recorder subprocess...")
                
                # Start the recorder as a subprocess
                self.process = subprocess.Popen(
                    [python_exe, RECORDER_SCRIPT],
                    cwd=SCRIPT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                self.logger.info(f"Recorder started with PID: {self.process.pid}")
                
                # Wait for either stop signal or process exit
                while self.running:
                    # Check if process is still running
                    if self.process.poll() is not None:
                        self.logger.warning(f"Recorder exited with code: {self.process.returncode}")
                        break
                    
                    # Check for stop event (wait 1 second)
                    result = win32event.WaitForSingleObject(self.stop_event, 1000)
                    if result == win32event.WAIT_OBJECT_0:
                        self.logger.info("Stop event received")
                        break
                
                # If we're still running but process died, wait before restart
                if self.running and self.process.poll() is not None:
                    self.logger.info("Will restart recorder in 5 seconds...")
                    time.sleep(5)
                    
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                if self.running:
                    time.sleep(5)  # Wait before retry
        
        self.logger.info("Service main loop exited")


# ============================================================================
# SERVICE CONFIGURATION FUNCTIONS
# ============================================================================

def configure_recovery(service_name):
    """
    Configure service recovery options using ChangeServiceConfig2.
    Sets immediate restart (0 delay) for all failures.
    """
    print("  Configuring auto-recovery...")
    
    # Open Service Control Manager
    scm = win32service.OpenSCManager(
        None, 
        None, 
        win32service.SC_MANAGER_ALL_ACCESS
    )
    
    try:
        # Open the service
        service = win32service.OpenService(
            scm, 
            service_name, 
            win32service.SERVICE_ALL_ACCESS
        )
        
        try:
            # Define failure actions
            # SC_ACTION_RESTART = 1, delay in milliseconds
            restart_action = (win32service.SC_ACTION_RESTART, 0)  # 0ms delay
            
            # Set recovery options:
            # - Reset fail count after 86400 seconds (24 hours)
            # - Actions: restart, restart, restart (for 1st, 2nd, subsequent)
            failure_actions = {
                'ResetPeriod': 86400,  # seconds
                'RebootMsg': '',
                'Command': '',
                'Actions': [restart_action, restart_action, restart_action]
            }
            
            win32service.ChangeServiceConfig2(
                service,
                win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
                failure_actions
            )
            
            print("  ✓ Recovery configured: Restart immediately on any failure")
            
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(scm)


def set_service_security(service_name, sddl_string):
    """
    Apply a Security Descriptor (SDDL) to the service.
    """
    print(f"  Applying security descriptor...")
    
    # Convert SDDL to Security Descriptor
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        sddl_string,
        win32security.SDDL_REVISION_1
    )
    
    # Open Service Control Manager
    scm = win32service.OpenSCManager(
        None, 
        None, 
        win32service.SC_MANAGER_ALL_ACCESS
    )
    
    try:
        # Open the service with WRITE_DAC access
        service = win32service.OpenService(
            scm, 
            service_name, 
            win32con.WRITE_DAC
        )
        
        try:
            # Set the security descriptor
            win32service.SetServiceObjectSecurity(
                service,
                win32security.DACL_SECURITY_INFORMATION,
                sd
            )
            print("  ✓ Security descriptor applied")
            
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(scm)


def get_service_status(service_name):
    """Get the current status of the service."""
    try:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            service = win32service.OpenService(scm, service_name, win32service.SERVICE_QUERY_STATUS)
            try:
                status = win32service.QueryServiceStatus(service)
                states = {
                    win32service.SERVICE_STOPPED: "STOPPED",
                    win32service.SERVICE_START_PENDING: "START_PENDING",
                    win32service.SERVICE_STOP_PENDING: "STOP_PENDING",
                    win32service.SERVICE_RUNNING: "RUNNING",
                    win32service.SERVICE_CONTINUE_PENDING: "CONTINUE_PENDING",
                    win32service.SERVICE_PAUSE_PENDING: "PAUSE_PENDING",
                    win32service.SERVICE_PAUSED: "PAUSED",
                }
                return states.get(status[1], f"UNKNOWN ({status[1]})")
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(scm)
    except Exception as e:
        return f"ERROR: {e}"


def service_exists(service_name):
    """Check if a service exists."""
    try:
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            service = win32service.OpenService(scm, service_name, win32service.SERVICE_QUERY_STATUS)
            win32service.CloseServiceHandle(service)
            return True
        except:
            return False
        finally:
            win32service.CloseServiceHandle(scm)
    except:
        return False


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

def do_install():
    """Install the service with hardening."""
    print("\n" + "=" * 60)
    print("INSTALLING SMART MOTION RECORDER SERVICE")
    print("=" * 60)
    
    # Check if recorder script exists
    if not os.path.exists(RECORDER_SCRIPT):
        print(f"ERROR: Recorder script not found: {RECORDER_SCRIPT}")
        return False
    
    # Check if already installed
    if service_exists(SERVICE_NAME):
        print(f"Service '{SERVICE_NAME}' already exists.")
        print("Use 'remove' command first if you want to reinstall.")
        return False
    
    print(f"  Installing service '{SERVICE_NAME}'...")
    
    try:
        # Use HandleCommandLine with 'install' to properly register the service
        # Save original argv and restore after
        original_argv = sys.argv
        sys.argv = [sys.argv[0], '--startup', 'auto', 'install']
        
        try:
            win32serviceutil.HandleCommandLine(SmartRecorderService)
        except SystemExit:
            pass  # HandleCommandLine calls sys.exit, we catch it
        finally:
            sys.argv = original_argv
        
        # Verify installation succeeded
        if not service_exists(SERVICE_NAME):
            raise Exception("Service installation failed - service not found after install")
        
        print("  ✓ Service installed")
        
        # Configure recovery options
        configure_recovery(SERVICE_NAME)
        
        # Apply hardened security
        set_service_security(SERVICE_NAME, SDDL_HARDENED)
        
        print("\n" + "=" * 60)
        print("✅ INSTALLATION COMPLETE")
        print("=" * 60)
        print(f"  Service Name: {SERVICE_NAME}")
        print(f"  Status: {get_service_status(SERVICE_NAME)}")
        print(f"  Log File: {LOG_FILE}")
        print("\n  🔒 PROTECTION ENABLED:")
        print("     - Administrators CANNOT stop/pause/delete this service")
        print("     - Only SYSTEM can control the service")
        print("     - Use 'remove_protection' to unlock for maintenance")
        print("\n  To start the service:")
        print(f"     python {os.path.basename(__file__)} start")
        print("     OR: net start SmartMotionRecorder")
        
        return True
        
    except Exception as e:
        print(f"ERROR during installation: {e}")
        import traceback
        traceback.print_exc()
        return False


def do_remove():
    """Remove the service (must be unlocked first)."""
    print("\n" + "=" * 60)
    print("REMOVING SMART MOTION RECORDER SERVICE")
    print("=" * 60)
    
    if not service_exists(SERVICE_NAME):
        print(f"Service '{SERVICE_NAME}' is not installed.")
        return False
    
    print("  NOTE: Service must be unlocked before removal.")
    print("  If removal fails, run 'remove_protection' first.")
    
    try:
        # Try to stop the service first
        status = get_service_status(SERVICE_NAME)
        if status == "RUNNING":
            print("  Stopping service...")
            try:
                win32serviceutil.StopService(SERVICE_NAME)
                time.sleep(2)
            except Exception as e:
                print(f"  Could not stop service: {e}")
                print("  Run 'remove_protection' first!")
                return False
        
        # Remove the service using HandleCommandLine
        print("  Removing service...")
        original_argv = sys.argv
        sys.argv = [sys.argv[0], 'remove']
        
        try:
            win32serviceutil.HandleCommandLine(SmartRecorderService)
        except SystemExit:
            pass  # HandleCommandLine calls sys.exit
        finally:
            sys.argv = original_argv
        
        # Verify removal
        time.sleep(1)
        if service_exists(SERVICE_NAME):
            print("  ⚠️ Service may still exist")
        else:
            print("  ✓ Service removed")
        
        print("\n✅ Service successfully removed")
        return True
        
    except Exception as e:
        print(f"ERROR during removal: {e}")
        print("\nIf you see 'Access Denied', run:")
        print(f"  python {os.path.basename(__file__)} remove_protection")
        print("Then try removing again.")
        return False


def do_remove_protection():
    """Remove the ACL protection to allow normal admin access."""
    print("\n" + "=" * 60)
    print("REMOVING SERVICE PROTECTION")
    print("=" * 60)
    
    if not service_exists(SERVICE_NAME):
        print(f"Service '{SERVICE_NAME}' is not installed.")
        return False
    
    print("  Unlocking service...")
    
    try:
        # We need to use a workaround since the service is protected
        # Use SC command to reset security (runs as SYSTEM context)
        
        # First, try the direct Python approach
        try:
            set_service_security(SERVICE_NAME, SDDL_DEFAULT)
            print("  ✓ Protection removed via Python API")
        except Exception as e:
            print(f"  Python API failed: {e}")
            print("  Trying SC command...")
            
            # Use sc.exe sdset command
            result = subprocess.run(
                ['sc', 'sdset', SERVICE_NAME, SDDL_DEFAULT],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("  ✓ Protection removed via SC command")
            else:
                print(f"  SC command failed: {result.stderr}")
                raise Exception("Could not remove protection")
        
        print("\n✅ SERVICE UNLOCKED")
        print("   Administrators can now stop/remove the service")
        print("\n   To remove the service:")
        print(f"     python {os.path.basename(__file__)} remove")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nIf this fails, try from an elevated SYSTEM prompt:")
        print(f'  psexec -s cmd /c sc sdset {SERVICE_NAME} "{SDDL_DEFAULT}"')
        return False


def do_start():
    """Start the service using minimal permissions."""
    print(f"Starting service '{SERVICE_NAME}'...")
    
    if not service_exists(SERVICE_NAME):
        print(f"Service '{SERVICE_NAME}' is not installed.")
        return False
    
    try:
        # Open SCM with connect access
        scm = win32service.OpenSCManager(
            None, None, win32service.SC_MANAGER_CONNECT
        )
        
        try:
            # Open service with ONLY start permission (not SERVICE_ALL_ACCESS)
            service = win32service.OpenService(
                scm, SERVICE_NAME, win32service.SERVICE_START
            )
            
            try:
                # Start the service
                win32service.StartService(service, None)
                print("  Start command sent...")
                time.sleep(2)
                
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(scm)
        
        status = get_service_status(SERVICE_NAME)
        print(f"  Service status: {status}")
        
        if status == "RUNNING":
            print("✅ Service started successfully")
            return True
        else:
            print("⚠️ Service may still be starting...")
            return True
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def do_stop():
    """Stop the service (requires unlock first due to protection)."""
    print(f"Stopping service '{SERVICE_NAME}'...")
    
    if not service_exists(SERVICE_NAME):
        print(f"Service '{SERVICE_NAME}' is not installed.")
        return False
    
    try:
        # Open SCM with connect access
        scm = win32service.OpenSCManager(
            None, None, win32service.SC_MANAGER_CONNECT
        )
        
        try:
            # Open service with stop permission
            service = win32service.OpenService(
                scm, SERVICE_NAME, win32service.SERVICE_STOP
            )
            
            try:
                # Stop the service
                win32service.ControlService(service, win32service.SERVICE_CONTROL_STOP)
                print("  Stop command sent...")
                time.sleep(2)
                
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(scm)
        
        status = get_service_status(SERVICE_NAME)
        print(f"  Service status: {status}")
        
        if status == "STOPPED":
            print("✅ Service stopped successfully")
            return True
        else:
            print("⚠️ Service may still be stopping...")
            return True
            
    except Exception as e:
        print(f"ERROR: {e}")
        if "Access" in str(e) or "denied" in str(e).lower():
            print("\n🔒 Service is protected! Run 'remove_protection' first.")
        return False


def do_status():
    """Show service status."""
    print("\n" + "=" * 60)
    print("SERVICE STATUS")
    print("=" * 60)
    
    if not service_exists(SERVICE_NAME):
        print(f"Service '{SERVICE_NAME}' is NOT installed.")
        return
    
    status = get_service_status(SERVICE_NAME)
    print(f"  Service Name: {SERVICE_NAME}")
    print(f"  Status: {status}")
    print(f"  Log File: {LOG_FILE}")
    
    if os.path.exists(LOG_FILE):
        print("\n  Recent log entries:")
        try:
            with open(LOG_FILE, 'r') as f:
                lines = f.readlines()
                for line in lines[-5:]:
                    print(f"    {line.strip()}")
        except:
            pass


def print_usage():
    """Print usage information."""
    print(f"""
Smart Motion Recorder - Windows Service Manager
================================================

Usage: python {os.path.basename(__file__)} <command>

Commands:
  install            Install service with auto-recovery and protection
  remove             Remove the service (must unlock first)
  start              Start the service
  stop               Stop the service
  status             Show service status
  remove_protection  Unlock service for maintenance/removal
  
Examples:
  python {os.path.basename(__file__)} install   # Install and protect
  python {os.path.basename(__file__)} start     # Start recording
  
To uninstall:
  python {os.path.basename(__file__)} remove_protection
  python {os.path.basename(__file__)} remove
""")


# ============================================================================
# MAIN ENTRY POINT
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
        
    elif command == 'remove_protection':
        success = do_remove_protection()
        sys.exit(0 if success else 1)
        
    elif command in ('--help', '-h', 'help'):
        print_usage()
        sys.exit(0)
        
    else:
        # Pass through to win32serviceutil for debug/other commands
        # This allows 'python service_install.py debug' to work
        win32serviceutil.HandleCommandLine(SmartRecorderService)

