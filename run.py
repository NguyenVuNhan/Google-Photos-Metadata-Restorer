#!/usr/bin/env python3
"""
Build script entry point for PyInstaller.
This file serves as the main entry point when building the executable.
"""

import sys
import os

# Add the parent directory to the path so we can import src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import main

if __name__ == "__main__":
    main()
