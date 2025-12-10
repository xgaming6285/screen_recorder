# ============================================================================
# SERVER SHARE SETUP SCRIPT
# Run this ON the server (192.168.50.128) to create the Recordings share
# Must be run as Administrator!
# ============================================================================

$ErrorActionPreference = "Stop"

# === CONFIGURATION ===
$SHARE_NAME = "Recordings"
$SHARE_PATH = "E:\Recordings"  # Physical folder on the server
$SHARE_DESCRIPTION = "Screen Recordings Storage"

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

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ============================================================================
# MAIN
# ============================================================================

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   SERVER SHARE SETUP" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check admin rights
if (-not (Test-Administrator)) {
    Write-Status "This script must be run as Administrator!" "ERROR"
    Write-Host ""
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

try {
    # Step 1: Create the folder
    Write-Status "Step 1/3: Creating folder: $SHARE_PATH"
    if (-not (Test-Path $SHARE_PATH)) {
        New-Item -ItemType Directory -Path $SHARE_PATH -Force | Out-Null
        Write-Status "Folder created!" "SUCCESS"
    } else {
        Write-Status "Folder already exists" "SUCCESS"
    }
    
    # Step 2: Remove existing share if present
    Write-Status "Step 2/3: Configuring share..."
    $existingShare = Get-SmbShare -Name $SHARE_NAME -ErrorAction SilentlyContinue
    if ($existingShare) {
        Write-Status "Removing existing share..." "WARNING"
        Remove-SmbShare -Name $SHARE_NAME -Force
    }
    
    # Step 3: Create the share with full access
    Write-Status "Step 3/3: Creating network share..."
    
    # Method 1: Using net share (most compatible)
    $result = net share $SHARE_NAME=$SHARE_PATH /grant:Everyone,FULL /remark:"$SHARE_DESCRIPTION" 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Status "Share created successfully!" "SUCCESS"
    } else {
        # Fallback: Try PowerShell cmdlet
        Write-Status "Trying alternate method..." "WARNING"
        New-SmbShare -Name $SHARE_NAME -Path $SHARE_PATH -FullAccess "Everyone" -Description $SHARE_DESCRIPTION
        Write-Status "Share created successfully!" "SUCCESS"
    }
    
    # Set NTFS permissions on the folder (allow Everyone to write)
    Write-Status "Setting folder permissions..."
    $acl = Get-Acl $SHARE_PATH
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "Everyone", 
        "FullControl", 
        "ContainerInherit,ObjectInherit", 
        "None", 
        "Allow"
    )
    $acl.SetAccessRule($rule)
    Set-Acl -Path $SHARE_PATH -AclObject $acl
    Write-Status "Permissions set!" "SUCCESS"
    
    # Display results
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "   SHARE CREATED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    
    # Get local IP addresses
    $ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" } | Select-Object -ExpandProperty IPAddress
    
    Write-Status "Share Details:" "INFO"
    Write-Host "  Share Name:    $SHARE_NAME" -ForegroundColor White
    Write-Host "  Local Path:    $SHARE_PATH" -ForegroundColor White
    Write-Host "  Access:        Everyone (Full Control)" -ForegroundColor White
    Write-Host ""
    Write-Status "Access from other computers using:" "INFO"
    foreach ($ip in $ips) {
        Write-Host "  \\$ip\$SHARE_NAME" -ForegroundColor Yellow
    }
    Write-Host "  \\$env:COMPUTERNAME\$SHARE_NAME" -ForegroundColor Yellow
    Write-Host ""
    
    # Verify share exists
    Write-Status "Verifying share..." "INFO"
    net share $SHARE_NAME
    
} catch {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "   SETUP FAILED!" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Status "Error: $_" "ERROR"
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

