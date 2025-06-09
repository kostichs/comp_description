# PowerShell deployment script for Company Canvas
# Author: AI Assistant
# Version: 1.0

param(
    [string]$Version = "v07",
    [string]$DockerHubUser = "sergeykostichev",
    [switch]$SkipBuild,
    [switch]$SkipPush,
    [switch]$TestLocal
)

$ImageName = "company-canvas-app"
$FullImageName = "$DockerHubUser/$ImageName`:$Version"

Write-Host "=== Company Canvas Deployment ===" -ForegroundColor Green
Write-Host "Version: $Version" -ForegroundColor Yellow
Write-Host "Full image name: $FullImageName" -ForegroundColor Yellow

# Check Docker
Write-Host "`n1. Checking Docker..." -ForegroundColor Cyan
try {
    $dockerVersion = docker --version
    Write-Host "✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker not found or not running. Start Docker Desktop!" -ForegroundColor Red
    exit 1
}

# Stop local server
Write-Host "`n2. Stopping local server..." -ForegroundColor Cyan
try {
    taskkill /F /IM python.exe 2>$null
    Write-Host "✓ Local server stopped" -ForegroundColor Green
} catch {
    Write-Host "! Local server not running" -ForegroundColor Yellow
}

# Remove old containers
Write-Host "`n3. Cleaning old containers..." -ForegroundColor Cyan
try {
    docker stop company-canvas-test 2>$null
    docker rm company-canvas-test 2>$null
    Write-Host "✓ Test containers removed" -ForegroundColor Green
} catch {
    Write-Host "! Test containers not found" -ForegroundColor Yellow
}

# Build image
if (-not $SkipBuild) {
    Write-Host "`n4. Building image..." -ForegroundColor Cyan
    docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Image build failed!" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Image built successfully" -ForegroundColor Green
} else {
    Write-Host "`n4. Build skipped" -ForegroundColor Yellow
}

# Local testing
if ($TestLocal) {
    Write-Host "`n5. Local testing..." -ForegroundColor Cyan
    Write-Host "Starting test container on port 8080..." -ForegroundColor White
    
    # Check port availability
    $portInUse = Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-Host "✗ Port 8080 is busy! Free the port and try again." -ForegroundColor Red
        exit 1
    }
    
    # Start test container
    docker run --rm -d --name company-canvas-test -p 8080:8000 `
        -e OPENAI_API_KEY="test" `
        -e SERPER_API_KEY="test" `
        -e SCRAPINGBEE_API_KEY="test" `
        $ImageName
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Test container start failed!" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✓ Test container started" -ForegroundColor Green
    Write-Host "Open browser: http://localhost:8080" -ForegroundColor Yellow
    Write-Host "Press any key to continue..." -ForegroundColor White
    Read-Host
    
    # Stop test container
    docker stop company-canvas-test
    Write-Host "✓ Test container stopped" -ForegroundColor Green
}

# Tag image
Write-Host "`n6. Tagging image..." -ForegroundColor Cyan
docker tag $ImageName $FullImageName
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Tagging failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Image tagged: $FullImageName" -ForegroundColor Green

# Publish to Docker Hub
if (-not $SkipPush) {
    Write-Host "`n7. Publishing to Docker Hub..." -ForegroundColor Cyan
    
    # Check authorization
    $loginStatus = docker info 2>$null | Select-String "Username"
    if (-not $loginStatus) {
        Write-Host "! Docker Hub login required" -ForegroundColor Yellow
        docker login
        if ($LASTEXITCODE -ne 0) {
            Write-Host "✗ Login failed!" -ForegroundColor Red
            exit 1
        }
    }
    
    # Push image
    docker push $FullImageName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Push failed!" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Image published to Docker Hub" -ForegroundColor Green
} else {
    Write-Host "`n7. Push skipped" -ForegroundColor Yellow
}

# VM instructions
Write-Host "`n=== VM DEPLOYMENT INSTRUCTIONS ===" -ForegroundColor Green
Write-Host "Execute these commands on your VM:" -ForegroundColor White
Write-Host ""
Write-Host "# Stop old container" -ForegroundColor Gray
Write-Host "docker stop company-canvas-prod" -ForegroundColor White
Write-Host "docker rm company-canvas-prod" -ForegroundColor White
Write-Host ""
Write-Host "# Pull new image" -ForegroundColor Gray
Write-Host "docker pull $FullImageName" -ForegroundColor White
Write-Host ""
Write-Host "# Run new container" -ForegroundColor Gray
Write-Host "docker run -d --restart unless-stopped -p 80:8000 \\" -ForegroundColor White
Write-Host "  -e OPENAI_API_KEY=`"your_key`" \\" -ForegroundColor White
Write-Host "  -e SERPER_API_KEY=`"your_key`" \\" -ForegroundColor White
Write-Host "  -e SCRAPINGBEE_API_KEY=`"your_key`" \\" -ForegroundColor White
Write-Host "  -e HUBSPOT_API_KEY=`"your_key`" \\" -ForegroundColor White
Write-Host "  --name company-canvas-prod \\" -ForegroundColor White
Write-Host "  -v /srv/company-canvas/output:/app/output \\" -ForegroundColor White
Write-Host "  $FullImageName" -ForegroundColor White
Write-Host ""
Write-Host "✓ Deployment completed!" -ForegroundColor Green

# Calculate next version
$NextVersionNumber = if ($Version -match 'v(\d+)') { [int]$Matches[1] + 1 } else { 8 }
$NextVersion = "v{0:D2}" -f $NextVersionNumber
Write-Host "Next version will be: $NextVersion" -ForegroundColor Yellow 