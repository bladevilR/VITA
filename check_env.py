#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os

print("\n[TEST] VITA Environment Check")
print("="*50)

# Test 1: Check working directory
print(f"\n[1] Working directory: {os.getcwd()}")

# Test 2: Check Python version
print(f"[2] Python version: {sys.version}")

# Test 3: Check if we can import basic modules
print("\n[3] Testing imports...")

try:
    print("  - Importing streamlit...", end="")
    import streamlit as st
    print(" OK")
except Exception as e:
    print(f" FAILED: {e}")
    sys.exit(1)

try:
    print("  - Importing pandas...", end="")
    import pandas as pd
    print(" OK")
except Exception as e:
    print(f" FAILED: {e}")
    sys.exit(1)

try:
    print("  - Importing numpy...", end="")
    import numpy as np
    print(" OK")
except Exception as e:
    print(f" FAILED: {e}")
    sys.exit(1)

try:
    print("  - Importing faiss...", end="")
    import faiss
    print(" OK")
except Exception as e:
    print(f" FAILED: {e}")
    sys.exit(1)

try:
    print("  - Importing requests...", end="")
    import requests
    print(" OK")
except Exception as e:
    print(f" FAILED: {e}")
    sys.exit(1)

# Test 4: Check knowledge base files
print("\n[4] Checking files...")
if os.path.exists("kb_zhipu.index"):
    size = os.path.getsize("kb_zhipu.index") / (1024*1024)
    print(f"  - kb_zhipu.index: {size:.1f} MB")
else:
    print("  - kb_zhipu.index: NOT FOUND")

if os.path.exists("kb_zhipu_id_map.npy"):
    size = os.path.getsize("kb_zhipu_id_map.npy") / (1024*1024)
    print(f"  - kb_zhipu_id_map.npy: {size:.1f} MB")
else:
    print("  - kb_zhipu_id_map.npy: NOT FOUND")

if os.path.exists("vita.py"):
    print(f"  - vita.py: OK")
else:
    print("  - vita.py: NOT FOUND")

# Test 5: Try importing vita
print("\n[5] Testing vita.py import (this may take a moment)...")
try:
    import vita
    print("  - vita.py imported successfully!")
except Exception as e:
    print(f"  - vita.py import FAILED:")
    print(f"    {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*50)
print("[SUCCESS] All tests passed! You can now run Streamlit.")
print("="*50)
print()
