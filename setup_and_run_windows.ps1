$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "MedExplain 3.2 setup" -ForegroundColor Cyan

# Prescription image OCR needs the Tesseract desktop application in addition to pytesseract.
$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract -and (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")) {
    $env:Path += ";C:\Program Files\Tesseract-OCR"
    $tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
}
if (-not $tesseract -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Tesseract OCR for prescription reading..." -ForegroundColor Yellow
    winget install --id UB-Mannheim.TesseractOCR --exact --silent --accept-package-agreements --accept-source-agreements
    if (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") {
        $env:Path += ";C:\Program Files\Tesseract-OCR"
    }
}
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue) -and -not (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")) {
    Write-Warning "Tesseract OCR was not detected. Prescription reader needs Tesseract. Install it from https://github.com/UB-Mannheim/tesseract/wiki, then reopen this terminal and run the setup script again."
}

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    py -3 -m venv venv
}
$python = ".\venv\Scripts\python.exe"
& $python -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw "Could not initialize pip in the project venv." }
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& $python -m pip install -r ".\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed. Check internet access and retry." }
& $python ".\app.py"
