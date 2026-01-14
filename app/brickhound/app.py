#!/usr/bin/env python3
"""
Entry point for the BrickHound Security Analysis App
"""

import os

# Use working app - simple HTML that renders correctly
from working_app import app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    print(f"Starting BrickHound App (Working HTML) on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)  # Auto-reload on code changes
