#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

print("\n========== VITA Environment Test ==========\n")

# Test 1: Basic imports
print("[1] Testing basic imports...")
try:
    import streamlit
    print(f"  ✓ streamlit: {streamlit.__version__}")
except Exception as e:
    print(f"  ✗ streamlit: {e}")
    sys.exit(1)

try:
    import pandas
    print(f"  ✓ pandas: OK")
except Exception as e:
    print(f"  ✗ pandas: {e}")
    sys.exit(1)

try:
    import numpy
    print(f"  ✓ numpy: OK")
except Exception as e:
    print(f"  ✗ numpy: {e}")
    sys.exit(1)

try:
    import requests
    print(f"  ✓ requests: OK")
except Exception as e:
    print(f"  ✗ requests: {e}")
    sys.exit(1)

try:
    import faiss
    print(f"  ✓ faiss: OK")
except Exception as e:
    print(f"  ✗ faiss: {e}")
    sys.exit(1)

print()

# Test 2: Database imports (may fail but shouldn't block startup)
print("[2] Testing database packages...")
try:
    import oracledb
    print(f"  ✓ oracledb: OK")
except Exception as e:
    print(f"  ⚠ oracledb: {e}")
    print(f"    (This is non-critical for Streamlit startup)")

print()

# Test 3: Check config files
print("[3] Checking configuration files...")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if os.path.exists(".env"):
    print(f"  ✓ .env found")
else:
    print(f"  ⚠ .env not found")

if os.path.exists("vita.py"):
    print(f"  ✓ vita.py found")
else:
    print(f"  ✗ vita.py not found")
    sys.exit(1)

if os.path.exists("kb_zhipu.index"):
    print(f"  ✓ kb_zhipu.index found")
else:
    print(f"  ⚠ kb_zhipu.index not found (knowledge base won't work)")

if os.path.exists("kb_zhipu_id_map.npy"):
    print(f"  ✓ kb_zhipu_id_map.npy found")
else:
    print(f"  ⚠ kb_zhipu_id_map.npy not found (knowledge base won't work)")

print()
print("========== Test Complete ==========")
print("\nYou can now start the service with: start_vita.bat")
print()
