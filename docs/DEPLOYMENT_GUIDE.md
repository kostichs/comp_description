# CompanyCanvas Application Deployment Guide Using Docker

This guide describes the steps to prepare a Docker image of your CompanyCanvas FastAPI application, test it locally, and subsequently deploy it on an Ubuntu virtual machine.

## 1. Project Preparation and Docker Files Locally

Before starting, ensure that your CompanyCanvas project is ready and the main functionality works correctly when run locally.

### 1.1. File `requirements.txt`

This file should contain all Python dependencies required for your application to work in production.
- If you are using Poetry, create it with the command: `poetry export -f requirements.txt --output requirements.txt --without-hashes`
- If you are using `pip freeze`: `pip freeze > requirements.txt`. In this case **make sure** to review the file and remove:
    - Packages specific to your OS (e.g., `pywin32`).
    - Packages used only for development and testing (e.g., `pytest`, `flake8`, `black`, `fastapi-cli`, `watchdog`, `watchfiles`, `typer`, `rich`, etc.).
    - Unnecessary dependencies (e.g., if a `Flask` package accidentally included its dependencies, but your application uses `FastAPI`).

**Key dependencies that should remain (example list):**
`fastapi`, `uvicorn`, `openai`, `python-dotenv`, `aiofiles`, `openpyxl`, `python-multipart`, `requests`, `beautifulsoup4`, `lxml`, `pandas` (if used for Excel processing), `scrapingbee` (if used), `google-search-results` (for Serper, if used) and other, directly used by your application.

### 1.2. File `.dockerignore`

Create a `.dockerignore` file in the root of your project to exclude unnecessary files and directories from the Docker context and image. This will reduce the image size and speed up the build.

Example content of `.dockerignore`:
```
# Git
.git
.gitignore
.gitattributes

# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.env
dist/
build/
*.log
output/ # Data sessions should not be included in the image

# Virtual environments
.venv/
venv/
env/

# IDE / Editors
.vscode/
.idea/
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# OS specific
.DS_Store
Thumbs.db
```

### 1.3. File `Dockerfile`

Create a `Dockerfile` (without extension) in the root of your project. This file describes how your Docker image will be built.

Example content of `Dockerfile`:
```dockerfile
# Use the official Python image as a base
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy the dependencies file
COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy necessary directories and files of the project to the working directory
COPY ./backend /app/backend
COPY ./frontend /app/frontend
COPY ./src /app/src
# Copy configuration files if they exist in the root and are needed by the application
COPY llm_config.yaml /app/llm_config.yaml
# If there are other important files/directories in the root, add them here
# COPY main_script_if_any.py /app/

# Open the port on which the application will run inside the container
EXPOSE 8000

# Command to run the application
# Make sure the path to your FastAPI application (instance app) is correct
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- **Check the paths in the `COPY` commands**: they should match the structure of your project.
- **Check the `CMD` command**: `backend.main:app` means that in the `backend` directory there is a file `main.py`, in which a FastAPI `app = FastAPI()` is created. Adjust if necessary.

## 2. Local Build and Test Docker Image

### 2.1. Build Image
Open a terminal in the root directory of your project and run:
```bash
docker build -t company-canvas-app .
```
- `company-canvas-app` is the name of your local image. You can choose another one.
- `.` indicates that the Dockerfile is in the current directory.
If errors occur, carefully read them. Often they are related to problems in `requirements.txt` or incorrect paths in `Dockerfile`.

### 2.2. Local Run and Test Container
After successful build, start the container:
```bash
docker run --rm -p 8080:8000 \
  -e OPENAI_API_KEY="YOUR_OPENAI_KEY" \
  -e SCRAPINGBEE_API_KEY="YOUR_SCRAPINGBEE_KEY" \
  -e SERPER_API_KEY="YOUR_SERPER_KEY" \
  company-canvas-app
```
- **Replace placeholders** (`YOUR_..._KEY`) with your actual API keys.
- Add other environment variables with the `-e VARIABLE_NAME="VALUE"` flag if your application requires them.
- `--rm`: automatically removes the container after stopping (convenient for tests).
- `-p 8080:8000`: forwards port 8080 of your computer to port 8000 inside the container.

**Testing:**
1. Open in your browser `http://localhost:8080`.
2. Ensure that the web interface loads.
3. Test the main functionality: upload a file, run processing.
4. Watch the terminal where `docker run` is running. There should be no errors related to configuration or API keys.
5. Ensure that the results are correct.
6. To stop the container, press `Ctrl+C` in the terminal.

## 3. Publishing Docker Image to Docker Hub

This allows you to easily download the image to your server.

### 3.1. Create Docker Hub Account
If you don't have one, register on [hub.docker.com](https://hub.docker.com/).

### 3.2. Log in to Docker Hub from Terminal
```bash
docker login
```
Enter your Docker ID and password (or Personal Access Token if 2FA is enabled).

### 3.3. Tag Local Image
Assign a tag to your local image in the format `YOUR_DOCKERHUB_USERNAME/REPOSITORY_NAME:VERSION`.
```bash
docker tag company-canvas-app YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06
```
- Replace `YOUR_DOCKERHUB_USERNAME` with your username.
- `company-canvas-app` after the slash is the name of the repository that will be created on Docker Hub.
- **IMPORTANT**: Always use versioned tags (v01, v02, v03...), never use `latest` for production.

### 3.4. Upload Image to Docker Hub
```bash
docker push YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06
```
Wait for the upload to complete.

## 4. Deploy Docker Container to Ubuntu VM

Connect to your Ubuntu VM via SSH.

### 4.1. Install Docker Engine (if not already installed)
If the command `docker --version` is not found or available only through `sudo` and your user is not in the `docker` group:
1. **Install Docker (official method):**
   ```bash
   sudo apt-get update
   sudo apt-get install ca-certificates curl
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
   ```
2. **Add your user to the `docker` group:**
   ```bash
   sudo usermod -aG docker $USER
   ```
3. **IMPORTANT: Exit SSH session and log in again**, so changes to group membership take effect.
4. **Check after re-login:**
   ```bash
   docker --version  # Should work without sudo
   groups $USER      # Should have group 'docker'
   ```

### 4.2. Download Image from Docker Hub to VM
```bash
docker pull YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06
```
- Replace `YOUR_DOCKERHUB_USERNAME` with your username.

### 4.3. Create Directory for Data Sessions
This directory on the server will be mounted into the container to prevent data sessions from being lost during container restart.
```bash
sudo mkdir -p /srv/company-canvas/output 
# Give write permissions (e.g., to your user if they will run docker run)
# Or, if you run Docker as root (not recommended for docker run without rootless mode), 
# then Docker can write there. 
# Safer to give permissions to a specific user or docker group:
sudo chown -R $USER:$USER /srv/company-canvas/output 
# (Or another path you choose)
```

### 4.4. Configure UFW Firewall
Allow incoming connections on SSH and HTTP.
```bash
sudo ufw allow ssh
sudo ufw allow 80/tcp  # For HTTP
# sudo ufw allow 443/tcp # If you plan to set up HTTPS later
sudo ufw enable        # Enable if not already enabled
sudo ufw status        # Check rules
```

### 4.5. Run Docker Container on VM
```bash
docker run -d --restart unless-stopped -p 80:8000 \
  -e OPENAI_API_KEY="YOUR_REAL_OPENAI_KEY" \
  -e SCRAPINGBEE_API_KEY="YOUR_REAL_SCRAPINGBEE_KEY" \
  -e SERPER_API_KEY="YOUR_REAL_SERPER_KEY" \
  --name company-canvas-prod \
  -v /srv/company-canvas/output:/app/output \
  YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06
```
- **Replace placeholders** for API keys with your actual values.
- `-d`: run in background (detached) mode.
- `--restart unless-stopped`: automatic container restart.
- `-p 80:8000`: forward port 80 of the server to port 8000 of the container. The application will be accessible via the server's IP address without specifying the port.
- `--name company-canvas-prod`: name for your "production" container.
- `-v /srv/company-canvas/output:/app/output`: mount directory for data. Make sure the path `/srv/company-canvas/output` (or your chosen path) exists on the server and permissions are correct.

## 5. Check Work on Server

1.  **Check Container Status:**
    ```bash
    docker ps 
    ```
    You should see the container `company-canvas-prod` with status `Up ...`.
2.  **Check Container Logs:**
    ```bash
    docker logs company-canvas-prod
    ```
    For real-time monitoring: `docker logs -f company-canvas-prod` (`Ctrl+C` to exit).
    Ensure that Uvicorn started without errors.
3.  **Access via Browser:**
    Open in your browser `http://YOUR_SERVER_IP_ADDRESS` (e.g., `http://202.78.163.133`).
    Your application should be accessible.
4.  **Test Functionality:** Upload a file, run processing.
5.  **Check Data Preservation:** Ensure that session files appear in the directory `/srv/company-canvas/output/sessions/` (or in your chosen path) on the server.

## 6. Application Update

If you made changes to the code and want to update the application on the server:
1. Make changes to the code locally.
2. Rebuild the Docker image locally: `docker build -t company-canvas-app .`
3. Tag the new image: `docker tag company-canvas-app YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06` (or with a new version tag, e.g., `...:1.0.1`)
4. Upload the new image to Docker Hub: `docker push YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06` (or with a new tag).
5. **On the Ubuntu VM:**
   a. Download the updated image: `docker pull YOUR_DOCKERHUB_USERNAME/company-canvas-app:v06`
   b. Stop the old container: `docker stop company-canvas-prod`
   c. Delete the old container: `docker rm company-canvas-prod`
   d. Start a new container with the same parameters `docker run ...`, using the updated image. (See point 4.5). Data in the mounted volume (`-v`) will remain unchanged.

**Consider using Docker Compose for easier management of updates.**

This guide should help you in the future to deploy the project independently! 

# Quick Deployment Instructions (Version 6)

This quick step-by-step guide is for quick deployment without unnecessary details.

## 1. Local Build and Publish Image

```bash
# Log in to Docker Hub
docker login

# Build local image
docker build -t company-canvas-app .

# Tag image with correct repository name and version
docker tag company-canvas-app sergeykostichev/company-canvas-app:v06

# Send image to Docker Hub
docker push sergeykostichev/company-canvas-app:v06
```

## 2. Deployment on Virtual Machine

```bash
# Delete previous container (if exists)
docker stop company-canvas-prod
docker rm company-canvas-prod

# Download new image
docker pull sergeykostichev/company-canvas-app:v06

# Create directory for data (if not created)
sudo mkdir -p /srv/company-canvas/output
sudo chown -R $USER:$USER /srv/company-canvas/output

# Start new container with FULL image name
docker run -d --restart unless-stopped -p 80:8000 \
  -e OPENAI_API_KEY="your_openai_key" \
  -e SERPER_API_KEY="your_serper_key" \
  -e SCRAPINGBEE_API_KEY="your_scrapingbee_key" \
  -e HUBSPOT_API_KEY="your_hubspot_key" \
  -e HUBSPOT_BASE_URL="https://app.hubspot.com/contacts/your_portal_id/record/0-2/" \
  -e DEBUG="false" \
  --name company-canvas-prod \
  -v /srv/company-canvas/output:/app/output \
  sergeykostichev/company-canvas-app:v06
```

## 3. Check Work

```bash
# Check running containers
docker ps

# Check container logs
docker logs company-canvas-prod

# Watch logs in real time
docker logs -f company-canvas-prod
```

Now the application should be accessible via the IP address of the virtual machine on port 80.

## 4. Important Points

**IMPORTANT**: 
- Always use FULL image name: `sergeykostichev/company-canvas-app:v06`
- DO NOT use abbreviated names like `company-canvas-app` - this will cause an error
- When updating version, change tag number: v06 → v07 → v08 and so on
- For production ALWAYS use `-d` (background mode) and port 80

## 5. Web Interface Information

- Web interface automatically updates result table every 2 seconds
- Update parameter is in file `frontend/app.js` (line 326, value 2000 ms)
- Table automatically displays results when processing is successful 