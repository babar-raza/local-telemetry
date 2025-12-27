# Self-Hosted GitHub Actions Runner Setup

This guide shows how to set up a GitHub Actions runner on your local Windows machine that can execute workflows for any repository.

## Prerequisites

- Windows 10/11 or Windows Server
- PowerShell 5.1 or later
- .NET Core 3.1+ (will be installed automatically)
- Docker Desktop (for contract tests)
- Administrator access

## Quick Start

### 1. Create Runner Directory

```powershell
# Create a directory for the runner
mkdir C:\actions-runner
cd C:\actions-runner
```

### 2. Download Runner

Visit your GitHub repository:
1. Go to **Settings** → **Actions** → **Runners**
2. Click **New self-hosted runner**
3. Select **Windows** as the operating system
4. Copy and run the download commands shown

Or download directly:

```powershell
# Download latest runner
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-win-x64-2.321.0.zip -OutFile actions-runner-win-x64-2.321.0.zip

# Extract
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD\actions-runner-win-x64-2.321.0.zip", "$PWD")
```

### 3. Configure Runner

**For a specific repository:**

```powershell
# Replace with your repository URL
.\config.cmd --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_REGISTRATION_TOKEN
```

**For organization-wide runner (any repo):**

```powershell
# Replace with your org URL
.\config.cmd --url https://github.com/YOUR_ORG --token YOUR_ORG_TOKEN
```

**Configuration prompts:**
- Runner group: Press Enter (default)
- Runner name: Enter a name (e.g., `windows-local-runner`)
- Runner labels: Enter labels (e.g., `windows,local,docker`) or press Enter
- Work folder: Press Enter (default `_work`)

### 4. Run the Runner

**Interactive mode (for testing):**

```powershell
.\run.cmd
```

**As a Windows Service (recommended for production):**

```powershell
# Install as service (requires admin)
.\svc.cmd install

# Start the service
.\svc.cmd start

# Check status
.\svc.cmd status
```

### 5. Verify Runner

1. Go to your GitHub repository
2. Navigate to **Settings** → **Actions** → **Runners**
3. You should see your runner listed with a green "Idle" status

## Testing the Contract Tests Workflow

Once your runner is set up, test the contract tests workflow:

### Option 1: Manual Trigger

1. Go to your repository on GitHub
2. Navigate to **Actions** tab
3. Select **Contract Tests** workflow
4. Click **Run workflow** → **Run workflow**
5. Watch it execute on your local runner

### Option 2: Push to Trigger

```bash
# Commit the workflow files
git add .github/workflows/contract_tests.yml
git add README.md
git commit -m "ci: add contract test workflow"

# Push to trigger workflow
git push origin main
```

The workflow will automatically run on your self-hosted runner.

## Runner Management

### Start/Stop Service

```powershell
# Start
.\svc.cmd start

# Stop
.\svc.cmd stop

# Restart
.\svc.cmd stop
.\svc.cmd start
```

### View Logs

```powershell
# Service logs
Get-Content C:\actions-runner\_diag\Runner_*.log -Tail 50

# Workflow logs are also visible in GitHub Actions UI
```

### Update Runner

```powershell
# Stop the runner
.\svc.cmd stop

# Download new version
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/vX.X.X/actions-runner-win-x64-X.X.X.zip -OutFile actions-runner-update.zip

# Extract (will prompt to overwrite)
Expand-Archive -Path .\actions-runner-update.zip -DestinationPath . -Force

# Restart
.\svc.cmd start
```

### Remove Runner

```powershell
# Stop and uninstall service
.\svc.cmd stop
.\svc.cmd uninstall

# Remove runner from GitHub
.\config.cmd remove --token YOUR_REMOVAL_TOKEN
```

## Environment Variables for Contract Tests

The contract tests workflow needs these environment variables. The runner will use values from your local environment or the workflow file.

**Set system environment variables** (optional, for customization):

```powershell
# Set for current user
[System.Environment]::SetEnvironmentVariable('TEST_API_BASE_URL', 'http://localhost:8765', 'User')
[System.Environment]::SetEnvironmentVariable('TEST_DB_PATH', 'C:\temp\telemetry_test.sqlite', 'User')

# Restart the runner service to pick up changes
.\svc.cmd stop
.\svc.cmd start
```

## Using Runner for Multiple Repositories

### Organization Runner

If you configured the runner at the organization level, it can be used by any repository in the organization.

**In each repository's workflow:**

```yaml
jobs:
  test:
    runs-on: self-hosted  # Uses any available self-hosted runner
    # OR
    runs-on: [self-hosted, windows, docker]  # Uses runners with these labels
```

### Repository Runner

If configured for a specific repository, it only works for that repository.

## Troubleshooting

### Runner Not Picking Up Jobs

**Check runner status:**
```powershell
.\svc.cmd status
```

**Check labels:** Ensure your workflow's `runs-on` matches the runner labels.

**Check logs:**
```powershell
Get-Content _diag\Runner_*.log -Tail 100
```

### Docker Issues

**Ensure Docker Desktop is running:**
```powershell
docker ps
```

**Add runner user to docker-users group:**
```powershell
# Run as admin
net localgroup docker-users "NT AUTHORITY\NETWORK SERVICE" /add
```

### Permission Issues

**Run as Administrator:** The initial setup and service installation require admin rights.

**File permissions:** Ensure the runner directory has appropriate permissions:
```powershell
icacls C:\actions-runner /grant "NT AUTHORITY\NETWORK SERVICE:(OI)(CI)F" /T
```

### Workflow Fails at Checkout

**Ensure Git is installed:**
```powershell
git --version
```

If not installed, download from https://git-scm.com/download/win

## Advanced Configuration

### Ephemeral Runners

For security, you can configure the runner to accept only one job then remove itself:

```powershell
.\config.cmd --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_TOKEN --ephemeral
```

### Disable Automatic Updates

```powershell
.\config.cmd --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_TOKEN --disableupdate
```

### Custom Work Directory

```powershell
.\config.cmd --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_TOKEN --work D:\runner-work
```

## Security Considerations

1. **Private repositories only:** Don't use self-hosted runners for public repos (security risk)
2. **Firewall:** Ensure runner can reach github.com (443)
3. **Regular updates:** Keep the runner software updated
4. **Least privilege:** Run service with minimal necessary permissions
5. **Dedicated machine:** Use a dedicated VM/machine for runners if possible

## Resources

- [GitHub Docs: Self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [Runner releases](https://github.com/actions/runner/releases)
- [Security hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)

## Next Steps

After setting up the runner:

1. ✅ Verify runner appears in GitHub UI (green "Idle")
2. ✅ Test with a simple workflow (Hello World)
3. ✅ Run the contract tests workflow
4. ✅ Monitor logs for any issues
5. ✅ Set up as Windows service for persistent operation
