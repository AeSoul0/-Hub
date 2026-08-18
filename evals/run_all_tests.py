"""
@file evals/run_all_tests.py
@description Core module for A.U.R.O.R.A. System

Implements primary logic and architectural constraints.
Architectural constraints and responsibilities apply here.
Testability and dependency separation are enforced.
"""

import sys
import subprocess
import os

def main():
    print("==================================================")
    print(" A.U.R.O.R.A. FULL INFRASTRUCTURE TEST SUITE ")
    print("==================================================")
    
    # We execute pytest programmatically
    backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
    
    # Ensure pytest is available
    try:
        import pytest
    except ImportError:
        print("[!] Pytest is not installed in the current environment.")
        print("Run: pip install pytest pytest-cov httpx")
        sys.exit(1)

    print("[*] Running comprehensive test suites (Unit, Integration, Security, API, Agents)...")
    
    # Run pytest and point it to the tests/ directory
    # Using --tb=short for cleaner output
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "../tests/", "-v", "--tb=short"],
        cwd=backend_dir
    )
    
    print("\n==================================================")
    if result.returncode == 0:
        print("[SUCCESS] All infrastructure tests passed!")
        print("The Test Pyramid (M1-M16) is fully verified.")
    else:
        print("[FAILED] Some tests failed or placeholders need implementation.")
        print("Check the output above to see which tests are pending (TODO).")
    print("==================================================")

if __name__ == "__main__":
    main()
