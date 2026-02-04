#!/usr/bin/env python3
"""
Build script for creating PyInstaller executable
"""
import subprocess
import sys
import os
import argparse

def build_executable(onefile=True):
    """Build the executable using PyInstaller"""
    build_type = "single file" if onefile else "directory"
    print(f"Building {build_type} executable with PyInstaller...")
    
    # Make sure we have all dependencies
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Choose the appropriate spec file
    spec_file = "app_onefile.spec" if onefile else "app.spec"
    
    # Run PyInstaller with the spec file
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        spec_file
    ]
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("Build successful!")
        exe_name = f"kachaka_cmd_center{'.exe' if os.name == 'nt' else ''}"
        print(f"Executable created at: dist/{exe_name}")
        
        if onefile:
            print("\nTo run the single-file executable:")
            print("1. Copy your .env.local file to the same directory as the executable")
            print("2. Run the executable")
            print("\nNote: Single-file executables are slower to start but easier to distribute.")
        else:
            print("\nTo run the directory-based executable:")
            print("1. Copy your .env.local file to the dist/kachaka_cmd_center/ directory")
            print("2. Run the executable from the dist/kachaka_cmd_center/ directory")
            print("\nNote: Directory-based executables start faster but require all files.")
    else:
        print("Build failed!")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        return False
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Kachaka Command Center executable")
    parser.add_argument("--onedir", action="store_true", 
                       help="Build as directory instead of single file")
    
    args = parser.parse_args()
    onefile = not args.onedir
    
    success = build_executable(onefile=onefile)
    sys.exit(0 if success else 1)