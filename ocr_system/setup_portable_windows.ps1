param(
  [string]$Model = "gemini-3.1-flash-lite"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $scriptDir ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$runCmd = Join-Path $scriptDir "run_ocr.cmd"
$envFile = Join-Path $scriptDir ".env"

Write-Host "[1/4] Creo ambiente virtuale locale..."
if (!(Test-Path $pythonExe)) {
  py -3 -m venv $venvPath
}

Write-Host "[2/4] Installo dipendenze nel venv locale..."
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install -r (Join-Path $scriptDir "requirements.txt")

Write-Host "[3/4] Salvo API key locale (.env)..."
if (Test-Path $envFile) {
  $existing = Get-Content $envFile -Raw
} else {
  $existing = ""
}

if ($existing -notmatch "GOOGLE_API_KEY=") {
  $apiKey = Read-Host "Inserisci GOOGLE_API_KEY (AI Studio)"
  @(
    "GOOGLE_API_KEY=$apiKey"
    "GEMINI_MODEL=$Model"
  ) | Set-Content -Path $envFile -Encoding UTF8
} else {
  Write-Host "GOOGLE_API_KEY già presente in .env (nessuna modifica)."
}

Write-Host "[4/4] Registro menu contestuale (solo utente corrente, no admin)..."
$extensions = @(".pdf", ".jpg", ".jpeg", ".png")
$base = "Registry::HKEY_CURRENT_USER\Software\Classes\SystemFileAssociations"

foreach ($ext in $extensions) {
  $shellKey = Join-Path $base "$ext\shell\OCR_to_MD_HTML"
  $cmdKey = Join-Path $shellKey "command"
  New-Item -Path $shellKey -Force | Out-Null
  New-ItemProperty -Path $shellKey -Name "(default)" -Value "Converti con OCR (MD/HTML/DOCX/PDF)" -Force | Out-Null
  New-ItemProperty -Path $shellKey -Name "Icon" -Value "imageres.dll,-5302" -Force | Out-Null
  New-Item -Path $cmdKey -Force | Out-Null
  $command = "cmd /c \"\"$runCmd\" \"%1\"\""
  New-ItemProperty -Path $cmdKey -Name "(default)" -Value $command -Force | Out-Null
}

Write-Host "Setup completato. Ora usa click destro su file -> Converti con OCR (MD/HTML/DOCX/PDF)."
