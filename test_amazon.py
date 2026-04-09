import subprocess
import sys
import os
import signal

# Set environment
os.environ['PYTHONPATH'] = 'E:\\Test_Project\\Axelo_JSReverse'

# Run with timeout
try:
    result = subprocess.run(
        [sys.executable, '-m', 'axelo.ui.main', 'amazon', '--auto'],
        cwd='E:\\Test_Project\\Axelo_JSReverse',
        capture_output=True,
        text=True,
        timeout=180  # 3 minutes
    )
    print("STDOUT:")
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    print("\nSTDERR:")
    print(result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr)
    print(f"\nReturn code: {result.returncode}")
except subprocess.TimeoutExpired:
    print("TIMEOUT - Amazon test took more than 3 minutes")
except Exception as e:
    print(f"ERROR: {e}")