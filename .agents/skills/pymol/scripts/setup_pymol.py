#!/usr/bin/env python3
"""
Cross-platform PyMOL + claudemol setup script.

Detects OS and guides installation of:
1. claudemol (Python package for socket communication)
2. PyMOL (molecular visualization software)
3. Plugin configuration

Usage:
    python setup_pymol.py [--check-only]
"""

import platform
import subprocess
import sys
import shutil
import socket
from pathlib import Path


def print_header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_step(step: int, text: str) -> None:
    print(f"[{step}] {text}")


def print_success(text: str) -> None:
    print(f"  [OK] {text}")


def print_warning(text: str) -> None:
    print(f"  [!!] {text}")


def print_error(text: str) -> None:
    print(f"  [ERROR] {text}")


def check_command(cmd: str) -> bool:
    """Check if a command is available in PATH."""
    return shutil.which(cmd) is not None


def check_python_package(package: str) -> bool:
    """Check if a Python package is installed."""
    try:
        __import__(package)
        return True
    except ImportError:
        return False


def check_port(port: int, host: str = 'localhost') -> bool:
    """Check if a port is listening."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.error, socket.timeout):
        return False


def run_command(cmd: list, capture: bool = False) -> tuple:
    """Run a command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            check=True
        )
        return True, result.stdout if capture else ""
    except subprocess.CalledProcessError as e:
        return False, str(e)
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"


def detect_environment() -> dict:
    """Detect the current environment."""
    system = platform.system()

    env = {
        'system': system,
        'python': sys.executable,
        'in_venv': sys.prefix != sys.base_prefix,
        'has_pip': check_command('pip') or check_command('pip3'),
        'has_brew': check_command('brew') if system == 'Darwin' else False,
        'has_conda': check_command('conda'),
        'claudemol_installed': check_python_package('claudemol'),
        'pymol_installed': check_command('pymol') or check_python_package('pymol'),
        'port_9880_open': check_port(9880),
    }

    return env


def install_claudemol() -> bool:
    """Install claudemol via pip."""
    print_step(1, "Installing claudemol...")

    cmd = [sys.executable, '-m', 'pip', 'install', 'claudemol']
    success, output = run_command(cmd)

    if success:
        print_success("claudemol installed successfully")
        return True
    else:
        print_error(f"Failed to install claudemol: {output}")
        return False


def setup_claudemol_plugin() -> bool:
    """Run claudemol setup to configure PyMOL plugin."""
    print_step(2, "Configuring claudemol plugin...")

    cmd = [sys.executable, '-m', 'claudemol', 'setup']
    success, output = run_command(cmd)

    if success:
        print_success("claudemol plugin configured")
        return True
    else:
        print_error(f"Failed to configure plugin: {output}")
        print("  Try running manually: claudemol setup")
        return False


def install_pymol_macos(env: dict) -> bool:
    """Install PyMOL on macOS."""
    print_step(3, "Installing PyMOL on macOS...")

    if env['has_brew']:
        print("  Using Homebrew (recommended for GUI support)...")
        success, output = run_command(['brew', 'install', 'pymol'])
        if success:
            print_success("PyMOL installed via Homebrew")
            return True
        else:
            print_warning(f"Homebrew install failed: {output}")
    else:
        print_warning("Homebrew not found")
        print("  Install Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")

    # Fallback to pip
    print("  Falling back to pip installation (headless only)...")
    success, output = run_command([sys.executable, '-m', 'pip', 'install', 'pymol-open-source'])

    if success:
        print_success("PyMOL installed via pip (note: may lack GUI on macOS)")
        print_warning("For full GUI support, install via Homebrew: brew install pymol")
        return True
    else:
        print_error(f"pip install failed: {output}")
        return False


def install_pymol_linux(env: dict) -> bool:
    """Install PyMOL on Linux."""
    print_step(3, "Installing PyMOL on Linux...")

    # Try pip first (most portable)
    print("  Installing via pip...")
    success, output = run_command([sys.executable, '-m', 'pip', 'install', 'pymol-open-source'])

    if success:
        print_success("PyMOL installed via pip")
        return True

    # Suggest system package
    print_warning("pip install failed")
    print("  Try installing system package:")
    print("    Ubuntu/Debian: sudo apt install pymol")
    print("    Fedora: sudo dnf install pymol")
    print("    Arch: sudo pacman -S pymol")
    return False


def install_pymol_windows(env: dict) -> bool:
    """Install PyMOL on Windows."""
    print_step(3, "Installing PyMOL on Windows...")

    print("  Installing via pip (headless mode)...")
    success, output = run_command([sys.executable, '-m', 'pip', 'install', 'pymol-open-source'])

    if success:
        print_success("PyMOL installed via pip")
        print()
        print("  NOTE: The pip version runs in HEADLESS mode (no GUI).")
        print("  This works for scripting and rendering via claudemol.")
        print()
        print("  For full GUI support on Windows:")
        print("    1. Download licensed PyMOL from https://pymol.org/")
        print("    2. Or use conda: conda install -c conda-forge pymol-open-source")
        return True
    else:
        print_error(f"pip install failed: {output}")
        print()
        print("  Alternative installation methods:")
        print("    1. Licensed PyMOL: https://pymol.org/")
        print("    2. Conda: conda install -c conda-forge pymol-open-source")
        return False


def verify_installation() -> bool:
    """Verify the complete installation."""
    print_header("Verifying Installation")

    all_ok = True

    # Check claudemol
    print("Checking claudemol...")
    if check_python_package('claudemol'):
        print_success("claudemol is installed")
    else:
        print_error("claudemol not found")
        all_ok = False

    # Check PyMOL command
    print("Checking PyMOL...")
    if check_command('pymol'):
        print_success("pymol command is available")
    elif check_python_package('pymol'):
        print_success("pymol Python module is available")
    else:
        print_warning("PyMOL not found in PATH or as Python module")
        all_ok = False

    # Check port (only if PyMOL might be running)
    print("Checking claudemol socket (port 9880)...")
    if check_port(9880):
        print_success("Port 9880 is listening - claudemol is active!")
    else:
        print_warning("Port 9880 not listening")
        print("  Start PyMOL to activate the claudemol plugin")

    return all_ok


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Setup PyMOL with claudemol')
    parser.add_argument('--check-only', action='store_true',
                        help='Only check installation status')
    args = parser.parse_args()

    print_header("PyMOL + claudemol Setup")

    # Detect environment
    print("Detecting environment...")
    env = detect_environment()

    print(f"  Platform: {env['system']}")
    print(f"  Python: {env['python']}")
    print(f"  Virtual env: {'Yes' if env['in_venv'] else 'No'}")
    print(f"  claudemol: {'Installed' if env['claudemol_installed'] else 'Not installed'}")
    print(f"  PyMOL: {'Installed' if env['pymol_installed'] else 'Not installed'}")
    print(f"  Port 9880: {'Active' if env['port_9880_open'] else 'Not listening'}")

    if args.check_only:
        verify_installation()
        return

    # Warn if not in venv
    if not env['in_venv']:
        print_warning("Not in a virtual environment")
        print("  Recommended: Create a venv first")
        print("  python -m venv .venv && source .venv/bin/activate")
        response = input("  Continue anyway? [y/N]: ").strip().lower()
        if response != 'y':
            print("Aborted.")
            return

    print_header("Installing Components")

    # Install claudemol
    if env['claudemol_installed']:
        print_step(1, "claudemol already installed")
        print_success("Skipping")
    else:
        if not install_claudemol():
            print_error("Cannot continue without claudemol")
            return

    # Setup plugin
    setup_claudemol_plugin()

    # Install PyMOL based on platform
    if env['pymol_installed']:
        print_step(3, "PyMOL already installed")
        print_success("Skipping")
    else:
        if env['system'] == 'Darwin':
            install_pymol_macos(env)
        elif env['system'] == 'Linux':
            install_pymol_linux(env)
        elif env['system'] == 'Windows':
            install_pymol_windows(env)
        else:
            print_warning(f"Unknown platform: {env['system']}")
            print("  Try: pip install pymol-open-source")

    # Verify
    verify_installation()

    print_header("Next Steps")
    print("1. Start PyMOL normally (e.g., 'pymol' command or GUI)")
    print("2. The claudemol plugin should load automatically")
    print("3. Verify connection: python -c \"import socket; s=socket.socket(); s.connect(('localhost', 9880)); print('OK')\"")
    print()
    print("Test command:")
    print("  python -c \"")
    print("  import socket, json")
    print("  s = socket.socket()")
    print("  s.connect(('localhost', 9880))")
    print("  s.send(json.dumps({'code': 'cmd.fetch(\\\"1ubq\\\"); cmd.show(\\\"cartoon\\\")'}).encode())")
    print("  print(s.recv(4096).decode())")
    print("  \"")


if __name__ == '__main__':
    main()
