$ErrorActionPreference = "Stop"

$KeyPath    = "C:\Users\frank.wang\Downloads\genpano-deploy.pem"
$ServerUser = "root"
$ServerHost = "116.62.36.173"
$SshPort    = 22

Write-Host ""
Write-Host "=== VM-per-account noVNC tunnel ==="
Write-Host "  Key:    $KeyPath"
Write-Host "  Target: $ServerUser@$ServerHost`:$SshPort"
Write-Host ""
Write-Host "Local ports being forwarded:"
Write-Host "  http://localhost:6080/vnc.html  -> doubao-01 noVNC"
Write-Host "  http://localhost:6081/vnc.html  -> doubao-02 noVNC"
Write-Host "  CDP 9222 / 9223                 (for Celery worker / poc_runner.py)"
Write-Host ""
Write-Host "Keep this window open. Ctrl+C to close the tunnel."
Write-Host ""

if (-not (Test-Path $KeyPath)) {
    Write-Error "SSH key not found at $KeyPath"
    exit 1
}

$Acl = (Get-Acl $KeyPath).Access |
    Where-Object { $_.IdentityReference -notmatch "($env:USERNAME|SYSTEM|Administrators)" }
if ($Acl) {
    Write-Warning "SSH key has loose permissions — Windows OpenSSH may refuse to use it."
    Write-Warning "Run once in an admin PowerShell:"
    Write-Warning "  icacls `"$KeyPath`" /inheritance:r /grant:r `"$env:USERNAME`:R`""
    Write-Host ""
}

ssh `
    -i "$KeyPath" `
    -p $SshPort `
    -N `
    -o ServerAliveInterval=30 `
    -o ServerAliveCountMax=3 `
    -o StrictHostKeyChecking=accept-new `
    -L 6080:127.0.0.1:6080 `
    -L 6081:127.0.0.1:6081 `
    -L 9222:127.0.0.1:9222 `
    -L 9223:127.0.0.1:9223 `
    "$ServerUser@$ServerHost"
