import subprocess
import sys
import time

sites = ['lazada', 'shopee', 'ebay', 'amazon']
results = {}

for site in sites:
    print(f"Testing {site}...", end=" ", flush=True)
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'axelo.ui.main', site, '--auto'],
            cwd='E:\\Test_Project\\Axelo_JSReverse',
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=120  # 2 minutes per site
        )
        elapsed = time.time() - start
        if "Done!" in result.stdout:
            results[site] = f"SUCCESS ({elapsed:.0f}s)"
        elif "Reverse complete" in result.stdout:
            results[site] = f"COMPLETED ({elapsed:.0f}s)"
        else:
            results[site] = f"UNKNOWN ({elapsed:.0f}s)"
        print(results[site])
    except subprocess.TimeoutExpired:
        results[site] = "TIMEOUT"
        print("TIMEOUT")
    except Exception as e:
        results[site] = f"ERROR"
        print(f"ERROR: {e}")

print("\n" + "="*40)
print("FINAL RESULTS:")
print("="*40)
for site, result in results.items():
    status = "OK" if "SUCCESS" in result or "COMPLETED" in result else "FAIL"
    print(f"[{status}] {site}: {result}")