param(
  [string]$ApiBaseUrl = "http://127.0.0.1:8000/api/v1",
  [int]$Workers = 1,
  [int]$ThreadLimit = 80,
  [int]$TotalRequests = 300,
  [int]$Concurrency = 10,
  [double]$RequestTimeout = 60,
  [string]$Prompt = "Ignore all previous instructions"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
  $PSNativeCommandUseErrorActionPreference = $false
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
Set-Location $backendDir

$logDir = Join-Path $backendDir "perf_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$uvOut = Join-Path $logDir "uvicorn_out.log"
$uvErr = Join-Path $logDir "uvicorn_err.log"
$runLog = Join-Path $logDir "run_trace.log"
$summaryPath = Join-Path $logDir "smoke_profile_summary.json"
$dbBodyPath = Join-Path $logDir "db_check_body.txt"
$dbStatusPath = Join-Path $logDir "db_check_status.txt"

"Starting perf profile run" | Tee-Object -FilePath $runLog -Append

if ($Workers -gt 1) {
  "Warning: workers > 1 on Windows can cause unstable shutdown/child-process errors; use 1 for stable profiling." | Tee-Object -FilePath $runLog -Append
}

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  throw "Python virtualenv executable not found at .venv\\Scripts\\python.exe"
}

& ".\.venv\Scripts\python.exe" "-m" "scripts.db_check" --output-body "$dbBodyPath" --output-status "$dbStatusPath"
$dbStatus = Get-Content $dbStatusPath -Raw
if (-not ($dbStatus -match "^200")) {
  throw "Database health check failed before perf run. Status=$dbStatus"
}

Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

$env:ANYIO_THREAD_LIMIT = "$ThreadLimit"
$env:PERF_TRACE_ENABLED = "true"
$env:PERF_TRACE_SAMPLE_RATE = "1.0"

$uvicornArgs = if ($Workers -gt 1) {
  "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers $Workers"
} else {
  "-m uvicorn app.main:app --host 0.0.0.0 --port 8000"
}

$uvicorn = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList $uvicornArgs `
  -RedirectStandardOutput $uvOut `
  -RedirectStandardError $uvErr `
  -PassThru

"uvicorn pid=$($uvicorn.Id) workers=$Workers thread_limit=$ThreadLimit" | Tee-Object -FilePath $runLog -Append

$healthy = $false
1..40 | ForEach-Object {
  if ($uvicorn.HasExited) {
    throw "uvicorn exited early with code $($uvicorn.ExitCode)"
  }

  try {
    $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    if ($health.status -eq "healthy") {
      $healthy = $true
      return
    }
  }
  catch {
    "health wait attempt failed: $($_.Exception.Message)" | Tee-Object -FilePath $runLog -Append
  }
  Start-Sleep -Milliseconds 500
}

if (-not $healthy) {
  throw "Backend did not become healthy in time"
}

$suffix = [guid]::NewGuid().ToString("N")
$signupBody = @{
  company_name = "Perf Profile Co"
  email = "perf-profile-$suffix@example.com"
  password = "TestPass123!"
} | ConvertTo-Json

$signup = Invoke-RestMethod -Method Post -Uri "$ApiBaseUrl/auth/signup" -ContentType "application/json" -Body $signupBody
$apiKey = $signup.api_key
if (-not $apiKey) {
  throw "Signup did not return api_key"
}

"Created tenant for perf profile" | Tee-Object -FilePath $runLog -Append

"Running smoke profile: requests=$TotalRequests concurrency=$Concurrency timeout=$RequestTimeout" | Tee-Object -FilePath $runLog -Append

$smokeOutput = & ".\.venv\Scripts\python.exe" "scripts/load_validate_smoke.py" `
  --mode smoke `
  --api-base-url "$ApiBaseUrl" `
  --api-key "$apiKey" `
  --total-requests $TotalRequests `
  --concurrency $Concurrency `
  --request-timeout $RequestTimeout `
  --max-server-errors 999999 `
  --max-p95-ms 999999 `
  --max-ok-p95-ms 999999 `
  --summary-json "$summaryPath" 2>&1

$smokeOutput | Tee-Object -FilePath $runLog -Append
$smokeExitCode = $LASTEXITCODE
"Smoke exit code: $smokeExitCode" | Tee-Object -FilePath $runLog -Append

if (-not (Test-Path $summaryPath)) {
  "Smoke command output:" | Tee-Object -FilePath $runLog -Append
  $smokeOutput | Tee-Object -FilePath $runLog -Append
  throw "Smoke summary file not found: $summaryPath"
}

"Summary: $summaryPath" | Tee-Object -FilePath $runLog -Append
"Uvicorn out: $uvOut" | Tee-Object -FilePath $runLog -Append
"Uvicorn err: $uvErr" | Tee-Object -FilePath $runLog -Append

if ($uvicorn -and -not $uvicorn.HasExited) {
  Stop-Process -Id $uvicorn.Id -ErrorAction SilentlyContinue
  Start-Sleep -Milliseconds 600
}

if ($uvicorn -and -not $uvicorn.HasExited) {
  Stop-Process -Id $uvicorn.Id -Force -ErrorAction SilentlyContinue
}
"Perf profile run complete" | Tee-Object -FilePath $runLog -Append

Get-Content $summaryPath -Raw
