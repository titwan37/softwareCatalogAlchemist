$malwarePath = Read-Host "Enter the full file path to destroy (e.g., \\SyNAS\path\to\file.exe)"

if (Test-Path -LiteralPath $malwarePath) {
    Remove-Item -LiteralPath $malwarePath -Force
    Write-Host "Threat successfully destroyed." -ForegroundColor Green
} else {
    Write-Host "Target file not found. It may have already been removed." -ForegroundColor Yellow
}