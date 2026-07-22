#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    # Add the src directory to the Python path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(script_dir, "src")
    sys.path.insert(0, src_dir)
    
    # Import and run the CLI
    from summarizer import cli_main
    sys.exit(cli_main()) 