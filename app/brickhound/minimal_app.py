#!/usr/bin/env python3
"""
Minimal Flask app - just plain text, no templates
"""

from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def index():
    return "BrickHound Minimal Test - If you see this text, Flask routing works!"

@app.route('/health')
def health():
    return '{"status":"healthy","service":"minimal"}'

@app.route('/test')
def test():
    env_info = f"""
    BRICKHOUND_CATALOG: {os.getenv('BRICKHOUND_CATALOG', 'not set')}
    BRICKHOUND_SCHEMA: {os.getenv('BRICKHOUND_SCHEMA', 'not set')}
    DATABRICKS_WAREHOUSE_HTTP_PATH: {os.getenv('DATABRICKS_WAREHOUSE_HTTP_PATH', 'not set')}
    PORT: {os.getenv('PORT', 'not set')}
    """
    return env_info

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    print(f"Starting Minimal Flask App on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

