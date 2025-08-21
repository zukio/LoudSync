# LoudSync - Audio Loudness Normalization Tool

param(
	[string]$InputDir = ".",
	[string]$OutputDir = "normalized",
	[string]$OutExt = "wav",
	[int]$SampleRate = 48000,
	[string[]]$Ext = @("*.wav", "*.mp3", "*.m4a"),
	[string]$Mode = "normalize",
	[string]$Preset = "Interactive",
	[string]$RefPath = "",
	[switch]$TwoPass,
	[switch]$Overwrite
)# Logging functions
function Write-Log([string]$msg) {
	$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
	$logEntry = "[$timestamp] $msg"
	Add-Content -Path (Join-Path $OutputDir "LoudSync.log") -Value $logEntry -ErrorAction SilentlyContinue
}

function Write-Info([string]$msg) {
	Write-Host "[INFO] $msg" -ForegroundColor Cyan
	Write-Log "INFO: $msg"
}

function Write-Warn([string]$msg) {
	Write-Host "[WARN] $msg" -ForegroundColor Yellow
	Write-Log "WARN: $msg"
}

function Write-Err([string]$msg) {
	Write-Host "[ERROR] $msg" -ForegroundColor Red
	Write-Log "ERROR: $msg"
}

# Measurement function
function Measure-Loudness([string]$filePath) {
	try {
		# Get loudness info with simpler approach
		$stderr = & $FFMPEG -hide_banner -nostats -i $filePath -af "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json" -f null - 2>&1
        
		# Convert stderr to string and extract JSON
		$output = $stderr -join "`n"
        
		# Find JSON block
		if ($output -match '\{[^}]*"input_i"[^}]*\}') {
			$jsonText = $matches[0]
			$json = $jsonText | ConvertFrom-Json
            
			return @{
				File           = $filePath
				IntegratedLUFS = [double]$json.input_i
				TruePeakdBTP   = [double]$json.input_tp
				LRAdB          = [double]$json.input_lra
				Status         = "OK"
			}
		}
		else {
			return @{
				File           = $filePath
				IntegratedLUFS = $null
				TruePeakdBTP   = $null
				LRAdB          = $null
				Status         = "NO_JSON"
			}
		}
	}
	catch {
		return @{
			File           = $filePath
			IntegratedLUFS = $null
			TruePeakdBTP   = $null
			LRAdB          = $null
			Status         = "ERROR: $($_.Exception.Message)"
		}
	}
}

# Reference file analysis
function Get-RefLUFS([string]$refPath) {
	if (-not (Test-Path $refPath)) {
		throw "Reference file not found: $refPath"
	}
    
	$result = Measure-Loudness $refPath
	if ($result.Status -eq "OK") {
		return [math]::Round($result.IntegratedLUFS, 1)
	}
 else {
		throw "Failed to analyze reference file"
	}
}

# FFmpeg path
$FFMPEG = ""

# Find FFmpeg
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegCmd) {
	$FFMPEG = $ffmpegCmd.Source
}
else {
	$localFFmpeg = ".\bin\ffmpeg.exe"
	if (Test-Path $localFFmpeg) {
		$FFMPEG = $localFFmpeg
	}
 else {
		Write-Host "ERROR: ffmpeg not found" -ForegroundColor Red
		exit 1
	}
}

Write-Host "Using ffmpeg: $FFMPEG" -ForegroundColor Green

# Find files
$files = @()
foreach ($e in $Ext) {
	$files += Get-ChildItem -Path $InputDir -File -Include $e -Recurse
}

if ($files.Count -eq 0) {
	Write-Host "No audio files found in $InputDir" -ForegroundColor Red
	exit 1
}

Write-Host "Found $($files.Count) files" -ForegroundColor Cyan

# Set target
$targetI = -16.0
$targetTP = -1.5

if ($Preset -eq "Interactive") {
	Write-Host ""
	Write-Host "=== Select Target ==="
	Write-Host "1) Reference file"
	Write-Host "2) Podcast: -16 LUFS"
	Write-Host "3) BGM: -18 LUFS"
	Write-Host "4) BGM: -19 LUFS"
	Write-Host "5) BGM: -20 LUFS"
	Write-Host "6) Broadcast: -23 LUFS"
	$sel = Read-Host "Enter number"
    
	if ($sel -eq "1") {
		$RefPath = Read-Host "Reference file path"
		if (Test-Path $RefPath) {
			try {
				$targetI = Get-RefLUFS $RefPath
				Write-Info "Reference file LUFS: $targetI"
			}
			catch {
				Write-Warn "Reference file analysis failed. Using -16 LUFS."
				$targetI = -16.0
			}
		}
		else {
			Write-Warn "Reference file not found. Using -16 LUFS."
			$targetI = -16.0
		}
	}
	elseif ($sel -eq "2") { $targetI = -16.0 }
	elseif ($sel -eq "3") { $targetI = -18.0 }
	elseif ($sel -eq "4") { $targetI = -19.0 }
	elseif ($sel -eq "5") { $targetI = -20.0 }
	elseif ($sel -eq "6") { $targetI = -23.0; $targetTP = -1.0 }
}
elseif ($Preset -eq "RefFile") {
	if ($RefPath -and (Test-Path $RefPath)) {
		try {
			$targetI = Get-RefLUFS $RefPath
			Write-Info "Reference file LUFS: $targetI"
		}
		catch {
			Write-Err "Reference file analysis failed"
			exit 1
		}
	}
 else {
		Write-Err "Reference file not specified or not found"
		exit 1
	}
}
elseif ($Preset -eq "-16") { $targetI = -16.0 }
elseif ($Preset -eq "-18") { $targetI = -18.0 }
elseif ($Preset -eq "-19") { $targetI = -19.0 }
elseif ($Preset -eq "-20") { $targetI = -20.0 }
elseif ($Preset -eq "-23") { $targetI = -23.0; $targetTP = -1.0 }Write-Host "Target: $targetI LUFS / TP $targetTP dBTP" -ForegroundColor Yellow

# Create output directory
New-Item -ItemType Directory -Force $OutputDir | Out-Null

# Measurement mode
$measureResults = @()
if ($Mode -eq "measure") {
	Write-Info "Running in measurement mode..."
}

# Process files
$ok = 0
$fail = 0

foreach ($f in $files) {
	if ($Mode -eq "measure") {
		# Measurement only
		Write-Host "Measuring: $($f.Name)" -ForegroundColor Green
		$result = Measure-Loudness $f.FullName
		$measureResults += New-Object PSObject -Property $result
        
		if ($result.Status -eq "OK") {
			Write-Host "  LUFS: $($result.IntegratedLUFS) | TP: $($result.TruePeakdBTP) | LRA: $($result.LRAdB)" -ForegroundColor Cyan
			$ok++
		}
		else {
			Write-Host "  Measurement failed" -ForegroundColor Red
			$fail++
		}
	}
 else {
		# Normalization mode
		$base = [IO.Path]::GetFileNameWithoutExtension($f.Name)
		$outPath = Join-Path $OutputDir "$base.$OutExt"
        
		if ((Test-Path $outPath) -and -not $Overwrite) {
			$outPath = Join-Path $OutputDir ($base + "_norm." + $OutExt)
		}

		Write-Host "Processing: $($f.Name)" -ForegroundColor Green
        
		try {
			if ($TwoPass) {
				# 2-pass normalization
				$cmd1 = "& `"$FFMPEG`" -hide_banner -nostats -i `"$($f.FullName)`" -af `"loudnorm=I=${targetI}:TP=${targetTP}:LRA=11:print_format=json`" -f null - 2>&1"
				$output = Invoke-Expression $cmd1
                
				# Extract JSON (simplified)
				$jsonLine = $output | Where-Object { $_ -match '\{.*\}' } | Select-Object -Last 1
                
				if ($jsonLine) {
					$json = $jsonLine | ConvertFrom-Json
					$cmd2 = "& `"$FFMPEG`" -hide_banner -y -i `"$($f.FullName)`" -af `"loudnorm=I=${targetI}:TP=${targetTP}:LRA=11:measured_I=$($json.input_i):measured_TP=$($json.input_tp):measured_LRA=$($json.input_lra):measured_thresh=$($json.input_thresh):offset=$($json.target_offset):linear=true`" -ar $SampleRate -c:a pcm_s16le `"$outPath`""
					Invoke-Expression $cmd2 | Out-Null
				}
				else {
					# Fallback to 1-pass
					$cmd = "& `"$FFMPEG`" -hide_banner -y -i `"$($f.FullName)`" -af `"loudnorm=I=${targetI}:TP=${targetTP}:LRA=11`" -ar $SampleRate -c:a pcm_s16le `"$outPath`""
					Invoke-Expression $cmd | Out-Null
				}
			}
			else {
				# 1-pass normalization
				$cmd = "& `"$FFMPEG`" -hide_banner -y -i `"$($f.FullName)`" -af `"loudnorm=I=${targetI}:TP=${targetTP}:LRA=11`" -ar $SampleRate -c:a pcm_s16le `"$outPath`""
				Invoke-Expression $cmd | Out-Null
			}
            
			$ok++
			Write-Host "OK: $($f.Name)" -ForegroundColor Green
		}
		catch {
			$fail++
			Write-Host "FAIL: $($f.Name) - $($_.Exception.Message)" -ForegroundColor Red
			Write-Log "ERROR processing $($f.FullName): $($_.Exception.Message)"
		}
	}
}

# Save measurement results to CSV
if ($Mode -eq "measure" -and $measureResults.Count -gt 0) {
	$csvPath = Join-Path $OutputDir "loudness_measurement.csv"
	$measureResults | Export-Csv -Path $csvPath -NoTypeInformation
	Write-Info "Measurement results saved to CSV: $csvPath"
}

Write-Host ""
Write-Host "Complete: Success=$ok / Fail=$fail" -ForegroundColor Cyan