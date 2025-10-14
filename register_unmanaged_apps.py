#!/usr/bin/env python3
"""
Chocolatey Registration Script for Apps Not Managed by WinGet
This script finds apps that aren't in WinGet and registers them with Chocolatey
Version 1.0 - Checks for unregistered apps and creates registration script
Version 1.1 - Added error handling and direct registration
"""

import subprocess
import json
import re
import sys
import time
from typing import List, Dict, Set, Tuple, Optional

class PackageManager:
    """Main package manager class with error handling"""

    def __init__(self):
        self.winget_apps = {}
        self.choco_packages = set()
        self.installed_programs = []
        self.unmanaged_apps = []
        self.matches = []

    @staticmethod
    def run_command(cmd: List[str], capture_output=True, shell=False) -> Tuple[str, str, int]:
        """Run a command and return stdout, stderr, and return code"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                encoding='utf-8',
                errors='ignore',
                shell=shell
            )
            return result.stdout, result.stderr, result.returncode
        except FileNotFoundError as e:
            return "", f"Command not found: {cmd[0]}", 1
        except Exception as e:
            return "", str(e), 1

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize app name for comparison"""
        if not name:
            return ""
        # Remove version numbers, special characters, convert to lowercase
        normalized = re.sub(r'\d+\.\d+.*', '', name)
        normalized = re.sub(r'[^a-z0-9]', '', normalized.lower())
        return normalized

    def check_prerequisites(self) -> bool:
        """Check if required tools are available"""
        print("\n" + "="*70)
        print("  Checking Prerequisites")
        print("="*70)

        # Check WinGet
        print("\nChecking WinGet...")
        stdout, stderr, code = self.run_command(['winget', '--version'])
        if code != 0:
            print("❌ WinGet is not available!")
            print("   WinGet should be pre-installed on Windows 11.")
            print("   For Windows 10, install from: https://aka.ms/getwinget")
            return False
        print(f"✅ WinGet is installed (version: {stdout.strip()})")

        # Check Chocolatey
        print("\nChecking Chocolatey...")
        stdout, stderr, code = self.run_command(['choco', '--version'])
        if code != 0:
            print("❌ Chocolatey is not installed!")
            print("   Install from: https://chocolatey.org/install")
            print("   Or run: Set-ExecutionPolicy Bypass -Scope Process -Force; ")
            print("   [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; ")
            print("   iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))")
            return False
        print(f"✅ Chocolatey is installed (version: {stdout.strip()})")

        # Check for admin privileges
        print("\nChecking administrator privileges...")
        if sys.platform == 'win32':
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                print("⚠️  Warning: Not running as Administrator")
                print("   Registration will require elevation for each package")
                print("   Consider running this script as Administrator for better experience")
            else:
                print("✅ Running with Administrator privileges")

        return True

    def get_winget_packages(self) -> bool:
        """Get all packages managed by WinGet"""
        print("\n" + "="*70)
        print("  Step 1/5: Checking WinGet Managed Packages")
        print("="*70)

        stdout, stderr, code = self.run_command(['winget', 'list', '--accept-source-agreements'])

        if code != 0:
            print(f"❌ Failed to get WinGet packages!")
            print(f"   Error: {stderr}")
            return False

        lines = stdout.split('\n')
        data_started = False

        for line in lines:
            if '---' in line:
                data_started = True
                continue

            if not data_started or not line.strip():
                continue

            # Parse WinGet output
            parts = line.split()
            if len(parts) >= 2:
                name = ' '.join(parts[:-3]) if len(parts) >= 3 else parts[0]
                normalized = self.normalize_name(name)
                if normalized:
                    self.winget_apps[normalized] = {
                        'name': name.strip(),
                        'line': line.strip()
                    }

        if not self.winget_apps:
            print("⚠️  Warning: No WinGet packages detected")
            print("   This is unusual. Continuing anyway...")
        else:
            print(f"✅ Found {len(self.winget_apps)} apps managed by WinGet")

        return True

    def get_installed_programs(self) -> bool:
        """Get all installed programs from Windows Registry"""
        print("\n" + "="*70)
        print("  Step 2/5: Scanning Installed Programs")
        print("="*70)

        ps_script = """
        $UninstallKeys = @(
            "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
            "HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
            "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
        )

        Get-ItemProperty $UninstallKeys -ErrorAction SilentlyContinue | 
            Where-Object { $_.DisplayName -and $_.DisplayName -notmatch '^(Microsoft|Windows|Update|Hotfix|KB[0-9]|Security)' } | 
            Select-Object DisplayName, DisplayVersion, Publisher | 
            ConvertTo-Json -Compress
        """

        stdout, stderr, code = self.run_command(
            ['powershell', '-Command', ps_script]
        )

        if code != 0:
            print(f"❌ Failed to retrieve installed programs!")
            print(f"   Error: {stderr}")
            return False

        if not stdout.strip():
            print("❌ No installed programs found!")
            print("   This might indicate a permission issue.")
            return False

        try:
            programs = json.loads(stdout)
            if isinstance(programs, dict):
                programs = [programs]

            self.installed_programs = programs
            print(f"✅ Found {len(self.installed_programs)} installed programs")
            return True

        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse installed programs data!")
            print(f"   Error: {e}")
            return False

    def get_chocolatey_packages(self) -> bool:
        """Get packages already registered with Chocolatey"""
        print("\n" + "="*70)
        print("  Step 3/5: Checking Chocolatey Packages")
        print("="*70)

        stdout, stderr, code = self.run_command(['choco', 'list', '--limit-output'])

        if code != 0:
            print(f"❌ Failed to get Chocolatey packages!")
            print(f"   Error: {stderr}")
            return False

        for line in stdout.split('\n'):
            line = line.strip()
            if not line:
                continue

            parts = line.split('|')
            if len(parts) >= 2:
                normalized = self.normalize_name(parts[0])
                if normalized:
                    self.choco_packages.add(normalized)

        print(f"✅ Found {len(self.choco_packages)} packages in Chocolatey")
        return True

    def find_unmanaged_apps(self) -> bool:
        """Find apps not managed by WinGet or Chocolatey"""
        print("\n" + "="*70)
        print("  Step 4/5: Finding Unmanaged Apps")
        print("="*70)

        for program in self.installed_programs:
            display_name = program.get('DisplayName', '')
            if not display_name:
                continue

            normalized = self.normalize_name(display_name)

            # Skip if managed by WinGet or Chocolatey
            if normalized in self.winget_apps or normalized in self.choco_packages:
                continue

            self.unmanaged_apps.append({
                'name': display_name,
                'version': program.get('DisplayVersion', 'Unknown'),
                'publisher': program.get('Publisher', 'Unknown'),
                'normalized': normalized
            })

        print(f"✅ Found {len(self.unmanaged_apps)} apps not managed by WinGet or Chocolatey")

        if not self.unmanaged_apps:
            print("\n🎉 All your apps are already managed!")
            print("   No action needed.")
            return False  # Nothing to do, but not an error

        return True

    def search_chocolatey_matches(self) -> bool:
        """Search for Chocolatey packages for unmanaged apps"""
        print("\n" + "="*70)
        print("  Step 5/5: Searching Chocolatey Repository")
        print("="*70)
        print("\nThis may take a few minutes...")

        total = len(self.unmanaged_apps)
        for i, app in enumerate(self.unmanaged_apps, 1):
            if i % 5 == 0 or i == total:
                print(f"Progress: {i}/{total} apps processed...")

            # Try exact search first
            stdout, stderr, code = self.run_command(
                ['choco', 'search', app['name'], '--exact', '--limit-output']
            )

            package_id = None
            package_version = None

            if code == 0 and stdout.strip():
                lines = stdout.strip().split('\n')
                if lines:
                    parts = lines[0].split('|')
                    if len(parts) >= 2:
                        package_id = parts[0]
                        package_version = parts[1]

            # Try approximate search if exact failed
            if not package_id:
                stdout, stderr, code = self.run_command(
                    ['choco', 'search', app['name'], '--limit-output']
                )

                if code == 0 and stdout.strip():
                    lines = stdout.strip().split('\n')
                    if lines:
                        parts = lines[0].split('|')
                        if len(parts) >= 2:
                            package_id = parts[0]
                            package_version = parts[1]

            if package_id:
                self.matches.append({
                    'app_name': app['name'],
                    'app_version': app['version'],
                    'choco_id': package_id,
                    'choco_version': package_version
                })

        if not self.matches:
            print("\n⚠️  No matching Chocolatey packages found.")
            print("   Your apps might be too specialized or not available in Chocolatey.")
            return False

        print(f"\n✅ Found {len(self.matches)} matching packages in Chocolatey")
        return True

    def display_results(self):
        """Display the discovered matches"""
        print("\n" + "="*70)
        print("  RESULTS")
        print("="*70)
        print(f"\nFound {len(self.matches)} apps that can be registered with Chocolatey:\n")

        print("-"*70)
        print(f"{'Installed App':<40} {'Chocolatey Package':<30}")
        print("-"*70)

        for match in self.matches:
            app_display = f"{match['app_name'][:37]}..." if len(match['app_name']) > 40 else match['app_name']
            print(f"{app_display:<40} {match['choco_id']:<30}")

        print("-"*70)

    def register_packages_interactive(self) -> bool:
        """Interactively register packages with Chocolatey"""
        print("\n" + "="*70)
        print("  REGISTRATION")
        print("="*70)

        print("\nRegistration options:")
        print("  1. Register all packages automatically")
        print("  2. Review and select packages individually")
        print("  3. Export to batch file (manual registration)")
        print("  4. Exit without registering")

        while True:
            choice = input("\nSelect option (1-4): ").strip()
            if choice in ['1', '2', '3', '4']:
                break
            print("Invalid choice. Please enter 1, 2, 3, or 4.")

        if choice == '4':
            print("\nExiting without registration.")
            return True

        if choice == '3':
            return self.export_to_batch()

        packages_to_register = []

        if choice == '1':
            packages_to_register = self.matches
            print(f"\nRegistering all {len(packages_to_register)} packages...")

        elif choice == '2':
            print("\nSelect packages to register:")
            for i, match in enumerate(self.matches, 1):
                while True:
                    response = input(f"  [{i}/{len(self.matches)}] Register {match['app_name']}? (y/n): ").strip().lower()
                    if response in ['y', 'n']:
                        break
                    print("      Please enter 'y' or 'n'")

                if response == 'y':
                    packages_to_register.append(match)

            if not packages_to_register:
                print("\nNo packages selected. Exiting.")
                return True

        # Register selected packages
        print(f"\n{'='*70}")
        print(f"  Registering {len(packages_to_register)} Package(s)")
        print("="*70)

        successful = []
        failed = []

        for i, match in enumerate(packages_to_register, 1):
            print(f"\n[{i}/{len(packages_to_register)}] Registering: {match['app_name']}")
            print(f"    Chocolatey package: {match['choco_id']}")

            cmd = ['choco', 'install', match['choco_id'], '-y', '-n', '--force']
            stdout, stderr, code = self.run_command(cmd)

            if code == 0:
                print("    ✅ Successfully registered")
                successful.append(match)
            else:
                print("    ❌ Registration failed")
                if stderr:
                    print(f"    Error: {stderr[:200]}")  # Show first 200 chars of error
                failed.append(match)

            # Brief pause to avoid overwhelming the system
            if i < len(packages_to_register):
                time.sleep(0.5)

        # Summary
        print("\n" + "="*70)
        print("  REGISTRATION SUMMARY")
        print("="*70)
        print(f"\n✅ Successfully registered: {len(successful)}")
        print(f"❌ Failed: {len(failed)}")

        if failed:
            print("\nFailed packages:")
            for match in failed:
                print(f"  - {match['app_name']} ({match['choco_id']})")
            print("\nYou can try registering these manually with:")
            for match in failed:
                print(f"  choco install {match['choco_id']} -y -n --force")

        return len(failed) == 0

    def export_to_batch(self) -> bool:
        """Export registration commands to a batch file"""
        batch_file = 'register_unmanaged_apps.bat'

        try:
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write('@echo off\r\n')
                f.write('echo Registering unmanaged apps with Chocolatey...\r\n')
                f.write('echo.\r\n')

                for match in self.matches:
                    f.write(f'echo Registering: {match["app_name"]}\r\n')
                    f.write(f'choco install {match["choco_id"]} -y -n --force\r\n')
                    f.write('echo.\r\n')

                f.write('echo.\r\n')
                f.write('echo Registration complete!\r\n')
                f.write('pause\r\n')

            print(f"\n✅ Batch file saved: {batch_file}")
            print("   Run this file as Administrator to register all apps")
            return True

        except Exception as e:
            print(f"\n❌ Failed to create batch file: {e}")
            return False

    def run(self) -> int:
        """Main execution flow"""
        print("="*70)
        print("  Chocolatey Registration for Apps Not Managed by WinGet")
        print("  Version 1.1 - With Error Handling & Direct Registration")
        print("="*70)

        # Check prerequisites
        if not self.check_prerequisites():
            return 1

        # Step 1: Get WinGet packages
        if not self.get_winget_packages():
            print("\n❌ Failed at Step 1. Cannot continue.")
            return 1

        # Step 2: Get installed programs
        if not self.get_installed_programs():
            print("\n❌ Failed at Step 2. Cannot continue.")
            return 1

        # Step 3: Get Chocolatey packages
        if not self.get_chocolatey_packages():
            print("\n❌ Failed at Step 3. Cannot continue.")
            return 1

        # Step 4: Find unmanaged apps
        if not self.find_unmanaged_apps():
            # This is not necessarily an error - might just mean everything is managed
            return 0

        # Step 5: Search for matches
        if not self.search_chocolatey_matches():
            # No matches found, but not an error
            return 0

        # Display results
        self.display_results()

        # Registration
        if not self.register_packages_interactive():
            print("\n⚠️  Registration completed with some errors.")
            return 1

        print("\n" + "="*70)
        print("✅ Script completed successfully!")
        print("="*70)
        return 0

def main():
    """Entry point"""
    try:
        manager = PackageManager()
        exit_code = manager.run()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Exiting...")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
