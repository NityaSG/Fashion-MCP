#!/usr/bin/env python3
"""
Setup Script for Fashion Trends MCP Server

Automates installation and configuration.
"""

import os
import sys
import subprocess
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent


def print_header(text):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def check_python_version():
    """Ensure Python 3.10+"""
    print("1️⃣ Checking Python version...")
    version = sys.version_info
    
    if version < (3, 10):
        print(f"   ❌ Python {version.major}.{version.minor} detected")
        print("   💡 Python 3.10 or higher required")
        print("   Install from: https://www.python.org/downloads/")
        return False
    
    print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def install_dependencies():
    """Install required packages"""
    print("\n2️⃣ Installing dependencies...")
    
    try:
        # Check if in virtual environment (recommended but not required)
        in_venv = hasattr(sys, 'real_prefix') or (
            hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
        )
        
        if not in_venv:
            print("   ⚠️  Not in a virtual environment")
            print("   💡 Recommended: python -m venv venv && source venv/bin/activate")
            response = input("   Continue anyway? (y/n): ")
            if response.lower() != 'y':
                return False
        
        # Install packages
        packages = ["fastmcp>=2.14.0", "asyncpg>=0.29.0", "python-dotenv"]
        
        for package in packages:
            print(f"   Installing {package}...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                capture_output=True
            )
        
        print("   ✅ All dependencies installed")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Installation failed: {e}")
        return False


def create_env_file():
    """Create .env file with user input"""
    print("\n3️⃣ Creating environment configuration...")
    
    env_path = REPO_ROOT / ".env"
    
    if env_path.exists():
        print("   ⚠️  .env file already exists")
        response = input("   Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("   Skipping .env creation")
            return True
    
    print("\n   Enter your Supabase credentials:")
    host = input("   Host (e.g., your-project.supabase.co): ").strip()
    db = input("   Database [postgres]: ").strip() or "postgres"
    user = input("   User [postgres]: ").strip() or "postgres"
    password = input("   Password: ").strip()
    port = input("   Port [5432]: ").strip() or "5432"
    
    env_content = f"""# Fashion Trends MCP Server Configuration

SUPABASE_HOST={host}
SUPABASE_PORT={port}
SUPABASE_DB={db}
SUPABASE_USER={user}
SUPABASE_PASSWORD={password}
"""
    
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print("   ✅ .env file created")
    return True


def test_connection():
    """Test database connection"""
    print("\n4️⃣ Testing database connection...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "test_connection.py")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        
        print(result.stdout)
        
        if result.returncode == 0:
            print("   ✅ Connection test passed")
            return True
        else:
            print("   ❌ Connection test failed")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
        return False


def configure_claude_desktop():
    """Guide user through Claude Desktop configuration"""
    print("\n5️⃣ Claude Desktop Configuration...")
    
    print("   Would you like to configure Claude Desktop?")
    print("   Options:")
    print("   1. Automatic installation (using fastmcp CLI)")
    print("   2. Manual configuration (show instructions)")
    print("   3. Skip")
    
    choice = input("\n   Enter choice (1/2/3): ").strip()
    
    if choice == "1":
        print("\n   Running automatic installation...")
        
        # Get absolute path to server
        server_path = (REPO_ROOT / "fashion_trends_mcp_server.py").resolve()
        
        # Load env for credentials
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
        
        cmd = [
            "fastmcp", "install", "claude-desktop", str(server_path),
            "--server-name", "fashion-trends",
            "--with", "asyncpg"
        ]
        
        # Add env vars
        env_vars = ["SUPABASE_HOST", "SUPABASE_PORT", "SUPABASE_DB", 
                   "SUPABASE_USER", "SUPABASE_PASSWORD"]
        
        for var in env_vars:
            value = os.getenv(var)
            if value:
                cmd.extend(["--env", f"{var}={value}"])
        
        try:
            subprocess.run(cmd, check=True)
            print("   ✅ Claude Desktop configured")
            print("\n   🔄 Restart Claude Desktop to activate the server")
        except subprocess.CalledProcessError:
            print("   ❌ Automatic installation failed")
            print("   💡 Try manual configuration instead")
            
    elif choice == "2":
        print_manual_config_instructions()
        
    else:
        print("   Skipped Claude Desktop configuration")


def print_manual_config_instructions():
    """Print manual configuration instructions"""
    
    server_path = (REPO_ROOT / "fashion_trends_mcp_server.py").resolve()
    
    # Load env vars
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    
    config = {
        "mcpServers": {
            "fashion-trends": {
                "command": "uv",
                "args": [
                    "run",
                    "--with", "fastmcp",
                    "--with", "asyncpg",
                    "fastmcp", "run",
                    str(server_path)
                ],
                "env": {
                    "SUPABASE_HOST": os.getenv("SUPABASE_HOST", "your-host"),
                    "SUPABASE_PORT": os.getenv("SUPABASE_PORT", "5432"),
                    "SUPABASE_DB": os.getenv("SUPABASE_DB", "postgres"),
                    "SUPABASE_USER": os.getenv("SUPABASE_USER", "postgres"),
                    "SUPABASE_PASSWORD": os.getenv("SUPABASE_PASSWORD", "your-password")
                }
            }
        }
    }
    
    print("\n   📝 Manual Configuration Instructions:")
    print("\n   1. Locate your Claude Desktop config file:")
    print("      macOS: ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("      Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
    
    print("\n   2. Add this configuration:\n")
    print(json.dumps(config, indent=2))
    
    print("\n   3. Save and restart Claude Desktop completely")
    print("   4. Look for the 🔨 hammer icon to confirm server loaded")


def main():
    """Run setup process"""
    
    print_header("Fashion Trends MCP Server - Setup")
    
    print("This script will:")
    print("  • Check Python version")
    print("  • Install required dependencies")
    print("  • Create .env configuration")
    print("  • Test database connection")
    print("  • Configure Claude Desktop (optional)")
    
    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("Setup cancelled")
        return
    
    # Step by step setup
    if not check_python_version():
        return
    
    if not install_dependencies():
        print("\n❌ Setup failed at dependency installation")
        return
    
    if not create_env_file():
        print("\n❌ Setup failed at environment configuration")
        return
    
    if not test_connection():
        print("\n⚠️  Database connection failed")
        print("💡 Check your credentials in .env file")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    configure_claude_desktop()
    
    # Final summary
    print_header("Setup Complete!")
    
    print("✅ Your Fashion Trends MCP Server is ready!\n")
    print("Next steps:")
    print("  1. Test the server: fastmcp dev fashion_trends_mcp_server.py")
    print("  2. Try examples: python scripts/example_usage.py")
    print("  3. Use with Claude Desktop (if configured)")
    print("\n📚 See docs/backend-server.md for full documentation")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
    except Exception as e:
        print(f"\n❌ Setup error: {e}")
        print("💡 See docs/backend-server.md for manual setup instructions")
