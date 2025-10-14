# winget-chocolatey-manager

Intelligent Windows app manager: identifies unmanaged apps and registers them with Chocolatey when not available in WinGet

## Description

This tool helps Windows users efficiently manage their applications by identifying which apps are not managed by WinGet and facilitating their registration with Chocolatey as a fallback package manager. Version 1.1 includes comprehensive error handling and direct registration capabilities.

## Features

- **Smart Detection**: Scans all installed Windows applications from Registry
- **WinGet Priority**: Checks which apps are already managed by WinGet (your primary package manager)
- **Chocolatey Integration**: Identifies apps that aren't managed by any package manager
- **Intelligent Matching**: Searches Chocolatey repository for matching packages
- **Direct Registration**: Register packages directly from the script with interactive options
- **Error Handling**: Comprehensive error checking at every step with detailed feedback
- **Flexible Workflow**: Choose to register all, select individually, or export to batch file
- **Admin Detection**: Automatic detection of administrator privileges
- **Progress Tracking**: Real-time progress indicators and status updates
- **Registration Summary**: Detailed success/failure reporting with retry commands

## Why This Tool?

**Avoid Duplicate Management**: Managing the same app with both WinGet and Chocolatey creates confusion and potential conflicts. This tool ensures apps are only registered with Chocolatey if they're not available in WinGet.

**WinGet First Philosophy**: WinGet is the native Windows package manager and should be your primary choice. Use Chocolatey only for apps that WinGet doesn't support.

**Automation**: Manually checking which apps need registration is tedious. This tool automates the entire discovery and registration process.

## Requirements

- **Windows 10/11**
- **Python 3.6 or higher**
- **WinGet** (pre-installed on Windows 11, [download for Windows 10](https://aka.ms/getwinget))
- **Chocolatey** (optional, [installation guide](https://chocolatey.org/install))
- **Administrator privileges** (recommended for registration)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/peterandree/winget-chocolatey-manager.git
cd winget-chocolatey-manager
```

### 2. Ensure WinGet is Installed

Windows 11 users already have WinGet. Windows 10 users should install it:

```powershell
# Install via winget itself (if you have an older version)
winget upgrade --id Microsoft.Winget.Source

# Or download from GitHub
# https://aka.ms/getwinget
```

### 3. Install Chocolatey (if not already installed)

Run PowerShell as Administrator:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

Verify installation:
```powershell
choco --version
```

## Usage

### Run as Administrator (Recommended)

Right-click PowerShell/Terminal → "Run as Administrator"

```bash
python register_unmanaged_apps.py
```

### Interactive Workflow

The script guides you through the process:

#### Step 1: Prerequisites Check
```
Checking Prerequisites
======================================================================

Checking WinGet...
✅ WinGet is installed (version: v1.6.3482)

Checking Chocolatey...
✅ Chocolatey is installed (version: 2.3.0)

Checking administrator privileges...
✅ Running with Administrator privileges
```

#### Step 2: System Scan (Automatic)
```
Step 1/5: Checking WinGet Managed Packages
✅ Found 47 apps managed by WinGet

Step 2/5: Scanning Installed Programs
✅ Found 124 installed programs

Step 3/5: Checking Chocolatey Packages
✅ Found 12 packages in Chocolatey

Step 4/5: Finding Unmanaged Apps
✅ Found 23 apps not managed by WinGet or Chocolatey

Step 5/5: Searching Chocolatey Repository
Progress: 23/23 apps processed...
✅ Found 8 matching packages in Chocolatey
```

#### Step 3: Review Results
```
RESULTS
======================================================================

Found 8 apps that can be registered with Chocolatey:

----------------------------------------------------------------------
Installed App                            Chocolatey Package            
----------------------------------------------------------------------
7-Zip 23.01                             7zip                          
VLC media player                         vlc                           
Notepad++ (64-bit)                       notepadplusplus               
----------------------------------------------------------------------
```

#### Step 4: Choose Registration Method
```
REGISTRATION
======================================================================

Registration options:
  1. Register all packages automatically
  2. Review and select packages individually
  3. Export to batch file (manual registration)
  4. Exit without registering

Select option (1-4): 2
```

#### Step 5: Interactive Registration (Option 2)
```
Select packages to register:
  [1/8] Register 7-Zip 23.01? (y/n): y
  [2/8] Register VLC media player? (y/n): y
  [3/8] Register Notepad++ (64-bit)? (y/n): n
  ...

Registering 2 Package(s)
======================================================================

[1/2] Registering: 7-Zip 23.01
    Chocolatey package: 7zip
    ✅ Successfully registered

[2/2] Registering: VLC media player
    Chocolatey package: vlc
    ✅ Successfully registered

REGISTRATION SUMMARY
======================================================================

✅ Successfully registered: 2
❌ Failed: 0

✅ Script completed successfully!
```

### Registration Options Explained

**Option 1 - Register All**: Best for trusted package lists. Registers all detected packages automatically without further prompts.

**Option 2 - Review Individually**: Recommended for first-time use. Review each package and choose which to register with y/n prompts.

**Option 3 - Export to Batch**: Creates a `.bat` file with registration commands. Useful if you want to review or modify commands before running.

**Option 4 - Exit**: Just scan and display results without registering anything.

## Command Flags Explained

The script uses these Chocolatey flags for safe registration:

- `-y`: Automatic yes to prompts (non-interactive mode)
- `-n`: Skip installation scripts (prevents reinstallation of already-installed software)
- `--force`: Force registration even with version mismatches
- `--limit-output`: Machine-parsable output format (used internally)

## Error Handling

The script includes comprehensive error handling:

### Common Issues

**"WinGet is not available"**
- Windows 11: Update Windows or reinstall via `winget upgrade --id Microsoft.Winget.Source`
- Windows 10: Install from https://aka.ms/getwinget

**"Chocolatey is not installed"**
- Follow the installation instructions in the Installation section above

**"Not running as Administrator"**
- The script will still work but may prompt for elevation for each package
- For best experience, run as Administrator from the start

**"Failed to retrieve installed programs"**
- Usually indicates insufficient permissions
- Try running as Administrator

**"No matching Chocolatey packages found"**
- Your apps might be too specialized or not available in Chocolatey
- Consider using WinGet exclusively or installing those apps manually

### Registration Failures

If some packages fail to register, the script provides:
- List of failed packages
- Manual commands to retry registration
- Error messages for troubleshooting

Example:
```
Failed packages:
  - SomeApp (someapp-package)

You can try registering these manually with:
  choco install someapp-package -y -n --force
```

## Architecture

### Object-Oriented Design

The script uses a `PackageManager` class with clearly separated methods:

- `check_prerequisites()`: Validates required tools and permissions
- `get_winget_packages()`: Queries WinGet for managed apps
- `get_installed_programs()`: Scans Windows Registry
- `get_chocolatey_packages()`: Lists Chocolatey-managed packages
- `find_unmanaged_apps()`: Filters out managed apps
- `search_chocolatey_matches()`: Searches Chocolatey repository
- `register_packages_interactive()`: Handles user interaction and registration

### Error Handling Pattern

Each method returns a boolean success status:
```python
if not self.check_prerequisites():
    return 1  # Exit with error code
```

The script stops immediately if critical steps fail, preventing cascading errors.

## Troubleshooting

### Script hangs during "Searching Chocolatey Repository"
This step queries the Chocolatey API for each unmanaged app. It can take 2-5 minutes for 20+ apps. Progress indicators show it's working.

### "Registration failed" for specific packages
- Package might not exist in Chocolatey repository (search manually: `choco search <appname>`)
- Network connectivity issues
- Chocolatey repository temporarily unavailable
- Package name mismatch (the script tries fuzzy matching but isn't perfect)

### Installed app not detected
- App might be installed in non-standard location
- App doesn't create proper registry entries
- App is a portable/standalone executable (not "installed")

### Version mismatch warnings
The `--force` flag allows registration even when versions don't match exactly. Chocolatey will track its repository version, and future updates will work correctly.

## Best Practices

1. **Run as Administrator**: Prevents elevation prompts for each package
2. **Use Option 2 first**: Review packages individually on first run
3. **Keep WinGet primary**: Only register with Chocolatey what WinGet can't handle
4. **Regular updates**: Run `winget upgrade --all` and `choco upgrade all -y` periodically
5. **Review matches**: Not all automatic matches are perfect—verify before registering

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Make your changes with proper error handling
4. Test on Windows 10 and Windows 11
5. Update documentation if needed
6. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
7. Push to the branch (`git push origin feature/AmazingFeature`)
8. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Use type hints for function signatures
- Include docstrings for all methods
- Add error handling for all external commands
- Test both success and failure paths

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

peterandree

## Version History

- **1.1.0** (2025-10-14)
  - Added comprehensive error handling
  - Direct registration from script (interactive mode)
  - Individual package selection option
  - Admin privilege detection
  - Progress indicators and status tracking
  - Registration summary with success/failure counts
  - Object-oriented architecture with PackageManager class
  - Proper exit codes and interrupt handling

- **1.0.0** (2025-10-14)
  - Initial release
  - WinGet integration
  - Chocolatey registration automation
  - Batch file generation

## Support

If you encounter any issues or have questions:
- **Open an issue** on GitHub with detailed error messages
- **Check existing issues** for solutions
- **Review the Troubleshooting section** above
- **Include your environment**: Windows version, Python version, WinGet version, Chocolatey version

## Acknowledgments

- Microsoft WinGet team for the native Windows package manager
- Chocolatey community for the extensive package repository and robust tooling
- Windows community for feedback and testing
- Contributors who help improve this tool

---

**Note**: This tool is designed to help manage Windows applications efficiently by preventing duplicate management between WinGet and Chocolatey. Always review commands before executing them, especially when running with administrative privileges.

## FAQ

**Q: Do I need both WinGet and Chocolatey?**  
A: WinGet should be your primary package manager. Install Chocolatey only if you have apps that aren't available in WinGet.

**Q: Will this reinstall my applications?**  
A: No. The `-n` flag tells Chocolatey to skip installation scripts, so it only registers the app without reinstalling.

**Q: What if I already have some apps in Chocolatey?**  
A: The script automatically detects and skips apps already registered with Chocolatey.

**Q: Can I unregister apps from Chocolatey later?**  
A: Yes, use `choco uninstall <packagename> -n` to unregister without uninstalling the actual application.

**Q: How often should I run this script?**  
A: Run it whenever you install new applications outside of WinGet/Chocolatey, or if you want to audit your package management coverage.
