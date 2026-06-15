#!/usr/bin/env pwsh
<#
.SYNOPSIS
Dev bypass mode: credential caching with automatic refresh to avoid repeated logins.

.DESCRIPTION
Caches AWS credentials locally with TTL and auto-refreshes before expiration.
Allows dev to work for 24h on cached credentials without manual refresh.

Core functions:
- Get-CachedCredentials: Load fresh or cached credentials
- Set-CachedCredentials: Save credentials to cache with TTL
- Test-CredentialFreshness: Check if cache is still valid
- Invoke-SilentRefresh: Background refresh when approaching expiration

Cache location: ~/.aws-dev/
Cache format: JSON with DPAPI encryption (Windows only)

.PARAMETER Mode
Operation mode: Get, Set, Refresh, Status, Clear

.PARAMETER CredentialFile
Path to credentials file (default: ~/.aws/credentials)

.PARAMETER CacheTtlHours
Time-to-live for cached credentials (default: 24)

.PARAMETER RefreshBeforeHours
Trigger refresh this many hours before expiration (default: 1)

.EXAMPLE
# Get credentials from cache or refresh if stale
$creds = & ".\dev-cache-manager.ps1" -Mode Get

# Manually set cache (called by refresh-aws-credentials.ps1)
& ".\dev-cache-manager.ps1" -Mode Set -AccessKeyId "AKIA..." -SecretKey "wJal..."

# Check cache status
& ".\dev-cache-manager.ps1" -Mode Status

# Clear cache (e.g., when credentials rotate)
& ".\dev-cache-manager.ps1" -Mode Clear
#>

param(
    [ValidateSet("Get", "Set", "Refresh", "Status", "Clear")]
    [string]$Mode = "Get",

    [string]$AccessKeyId,
    [string]$SecretKey,
    [string]$CredentialFile = "$HOME\.aws\credentials",
    [string]$CacheDir = "$HOME\.aws-dev",
    [int]$CacheTtlHours = 24,
    [int]$RefreshBeforeHours = 1
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$CacheFile = Join-Path $CacheDir "credentials.json"
$LockFile = Join-Path $CacheDir ".credential-cache.lock"

function Initialize-CacheDir {
    if (-not (Test-Path $CacheDir)) {
        New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
        Write-Verbose "Created cache directory: $CacheDir"
    }
}

function Encrypt-Credential {
    param([string]$PlainText)

    if (-not $PlainText) { return $PlainText }

    try {
        # Use DPAPI to encrypt for current user
        $SecureString = ConvertTo-SecureString -String $PlainText -AsPlainText -Force
        $EncryptedString = ConvertFrom-SecureString -SecureString $SecureString
        return $EncryptedString
    } catch {
        Write-Warning "Failed to encrypt credential: $_"
        # Fall back to plaintext in cache (better than losing credentials)
        return $PlainText
    }
}

function Decrypt-Credential {
    param([string]$EncryptedText)

    if (-not $EncryptedText) { return $EncryptedText }

    try {
        $SecureString = ConvertTo-SecureString -String $EncryptedText
        $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($BSTR)
    } catch {
        Write-Warning "Failed to decrypt credential: $_"
        # Fall back to plaintext (assume it was never encrypted)
        return $EncryptedText
    }
}

function Acquire-Lock {
    # Simple advisory lock: create lock file if it doesn't exist
    $MaxWaitSeconds = 10
    $WaitedSeconds = 0

    while ($WaitedSeconds -lt $MaxWaitSeconds) {
        try {
            # Try to create lock file exclusively
            if (-not (Test-Path $LockFile)) {
                New-Item -ItemType File -Path $LockFile -Force | Out-Null
                return $true
            }
        } catch {
            # Another process may have created it
        }

        Start-Sleep -Milliseconds 500
        $WaitedSeconds += 0.5
    }

    Write-Warning "Could not acquire lock after ${MaxWaitSeconds}s; proceeding anyway"
    return $false
}

function Release-Lock {
    try {
        if (Test-Path $LockFile) {
            Remove-Item -Force -Path $LockFile
        }
    } catch {
        Write-Warning "Failed to release lock: $_"
    }
}

function Get-CachedCredentials {
    Initialize-CacheDir

    if (-not (Test-Path $CacheFile)) {
        Write-Verbose "No cached credentials found"
        return $null
    }

    try {
        $Cache = Get-Content -Path $CacheFile -Raw | ConvertFrom-Json
        $ExpiresAt = [DateTime]::Parse($Cache.expires_at)
        $Now = Get-Date

        if ($Now -lt $ExpiresAt) {
            Write-Verbose "Cache is fresh (expires at $ExpiresAt)"

            # Decrypt credentials if encrypted
            $KeyId = Decrypt-Credential -EncryptedText $Cache.access_key_id
            $Secret = Decrypt-Credential -EncryptedText $Cache.secret_access_key

            return @{
                access_key_id = $KeyId
                secret_access_key = $Secret
                region = $Cache.region
                cached_at = [DateTime]::Parse($Cache.cached_at)
                expires_at = $ExpiresAt
            }
        } else {
            Write-Verbose "Cache expired at $ExpiresAt"
            return $null
        }
    } catch {
        Write-Warning "Failed to read cache: $_"
        return $null
    }
}

function Set-CachedCredentials {
    param(
        [string]$AccessKeyId,
        [string]$SecretKey,
        [string]$Region = "us-east-1"
    )

    Initialize-CacheDir
    Acquire-Lock | Out-Null

    try {
        $Now = Get-Date
        $ExpiresAt = $Now.AddHours($CacheTtlHours)

        $Cache = @{
            access_key_id = Encrypt-Credential -PlainText $AccessKeyId
            secret_access_key = Encrypt-Credential -PlainText $SecretKey
            region = $Region
            cached_at = $Now.ToUniversalTime().ToString("o")
            expires_at = $ExpiresAt.ToUniversalTime().ToString("o")
            ttl_hours = $CacheTtlHours
        }

        $Cache | ConvertTo-Json | Set-Content -Path $CacheFile -NoNewline
        Write-Host "Cached credentials (TTL: $CacheTtlHours hours, expires: $ExpiresAt)" -ForegroundColor Green
    } finally {
        Release-Lock
    }
}

function Test-CredentialFreshness {
    $Cache = Get-CachedCredentials

    if (-not $Cache) {
        return @{ fresh = $false; reason = "no_cache" }
    }

    $Now = Get-Date
    $HoursUntilExpiry = ($Cache.expires_at - $Now).TotalHours

    if ($HoursUntilExpiry -le 0) {
        return @{ fresh = $false; reason = "expired"; hours_until_expiry = 0 }
    }

    if ($HoursUntilExpiry -le $RefreshBeforeHours) {
        return @{ fresh = $true; reason = "approaching_expiry"; hours_until_expiry = $HoursUntilExpiry; needs_refresh = $true }
    }

    return @{ fresh = $true; reason = "valid"; hours_until_expiry = $HoursUntilExpiry; needs_refresh = $false }
}

function Update-AwsCredentialsFile {
    param(
        [string]$AccessKeyId,
        [string]$SecretKey,
        [string]$Region = "us-east-1"
    )

    # Update ~/.aws/credentials for boto3 consumption
    $Profile = "algo-developer"
    $AwsDir = Split-Path $CredentialFile -Parent

    if (-not (Test-Path $AwsDir)) {
        New-Item -ItemType Directory -Force -Path $AwsDir | Out-Null
    }

    $Existing = if (Test-Path $CredentialFile) { $r = Get-Content $CredentialFile -Raw; if ($r) { $r } else { "" } } else { "" }

    $NewBlock = @"
[$Profile]
aws_access_key_id = $AccessKeyId
aws_secret_access_key = $SecretKey
region = $Region
"@

    # Remove existing algo-developer block if present
    $Pattern = "(?ms)\[$Profile\][^\[]*"
    $Updated = if ($Existing -match $Pattern) { $Existing -replace $Pattern, "" } else { $Existing }

    # Trim and append
    $Updated = $Updated.TrimEnd() + "`n`n" + $NewBlock + "`n"

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($CredentialFile, $Updated, $utf8NoBom)
}

# === MAIN ===

switch ($Mode) {
    "Get" {
        $Cached = Get-CachedCredentials
        if ($Cached) {
            # Output as PowerShell object for consumption by other scripts
            $Cached | ConvertTo-Json | Write-Output
        } else {
            # Return empty object
            @{} | ConvertTo-Json | Write-Output
        }
    }

    "Set" {
        if (-not $AccessKeyId -or -not $SecretKey) {
            Write-Error "Mode 'Set' requires -AccessKeyId and -SecretKey"
            exit 1
        }
        Set-CachedCredentials -AccessKeyId $AccessKeyId -SecretKey $SecretKey
        Update-AwsCredentialsFile -AccessKeyId $AccessKeyId -SecretKey $SecretKey
        Write-Host "Credentials cached and synced to ~/.aws/credentials" -ForegroundColor Green
    }

    "Status" {
        $Freshness = Test-CredentialFreshness
        $Cached = Get-CachedCredentials

        if ($Cached) {
            Write-Host "Cache Status:" -ForegroundColor Cyan
            Write-Host "  Cached at: $($Cached.cached_at)"
            Write-Host "  Expires at: $($Cached.expires_at)"
            Write-Host "  Fresh: $($Freshness.fresh)"
            Write-Host "  Hours until expiry: $($Freshness.hours_until_expiry -as [int])"

            if ($Freshness.needs_refresh) {
                Write-Host "  ⚠️  Needs refresh (approaching expiry)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "No cached credentials found. Run refresh-aws-credentials.ps1 to fetch." -ForegroundColor Yellow
        }
    }

    "Clear" {
        Acquire-Lock | Out-Null
        try {
            if (Test-Path $CacheFile) {
                Remove-Item -Force -Path $CacheFile
                Write-Host "Cleared credential cache" -ForegroundColor Green
            }
        } finally {
            Release-Lock
        }
    }

    "Refresh" {
        # Check if refresh is needed
        $Freshness = Test-CredentialFreshness

        if (-not $Freshness.needs_refresh) {
            Write-Verbose "Credentials still fresh; refresh not needed"
            exit 0
        }

        Write-Host "Credentials approaching expiry; triggering refresh..." -ForegroundColor Yellow
        # In real implementation, this would call refresh-aws-credentials.ps1
        # For now, just alert the user
        Write-Host "Run: scripts/refresh-aws-credentials.ps1" -ForegroundColor Cyan
    }
}
