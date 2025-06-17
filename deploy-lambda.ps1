# PowerShell script to package and deploy Lambda function
Write-Host "Packaging Lambda function for deployment..."

# Set the Lambda directory
$lambdaDir = "C:\code\deploy\loadfundamentals\webapp\lambda"
$tempDir = "$env:TEMP\lambda-package"
$zipFile = "$lambdaDir\function.zip"

# Create temporary directory
if (Test-Path $tempDir) {
    Remove-Item $tempDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {    # Copy Lambda files to temp directory, excluding development files
    Write-Host "Copying files to temporary directory..."
    
    # Copy all files except excluded ones
    robocopy $lambdaDir $tempDir /E /XD node_modules\.cache tests coverage .git /XF *.zip test-* *.log /NP /NDL /NJH /NJS
    
    # Change to temp directory for packaging
    Push-Location $tempDir
    
    # Create zip file using PowerShell
    Write-Host "Creating zip package..."
    
    if (Test-Path $zipFile) {
        Remove-Item $zipFile -Force
    }
    
    # Use .NET compression
    Add-Type -AssemblyName "System.IO.Compression.FileSystem"
    [System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $zipFile)
    
    # Pop back to original directory
    Pop-Location
    
    Write-Host "Package created: $zipFile"
    $fileSize = (Get-Item $zipFile).Length / 1MB
    Write-Host "Package size: $([math]::Round($fileSize, 2)) MB"
    
    # Deploy to AWS Lambda
    Write-Host "Deploying to AWS Lambda..."
    $deployCommand = "aws lambda update-function-code --function-name financial-dashboard-api --zip-file fileb://$($zipFile.Replace('\', '/'))"
    
    Write-Host "Running: $deployCommand"
    
    # Execute deployment
    $result = cmd /c "aws lambda update-function-code --function-name financial-dashboard-api --zip-file `"fileb://$zipFile`""
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Deployment successful!"
        Write-Host $result
    } else {
        Write-Host "❌ Deployment failed with exit code: $LASTEXITCODE"
        Write-Host $result
    }
    
} catch {
    Write-Host "❌ Error during packaging/deployment: $($_.Exception.Message)"
} finally {
    # Cleanup temp directory
    if (Test-Path $tempDir) {
        Remove-Item $tempDir -Recurse -Force
    }
}
