#!/usr/bin/env python3
"""
Minimal test app to diagnose deployment issues
"""

from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
    <head><title>BrickHound Test</title></head>
    <body style="font-family: Arial; padding: 50px; text-align: center;">
        <h1>✅ BrickHound Test App is Running!</h1>
        <p>If you see this, Flask is working correctly.</p>
        <p><a href="/health">Check Health Endpoint</a></p>
        <p><a href="/env">Check Environment</a></p>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "brickhound-test"})

@app.route('/env')
def env():
    return jsonify({
        "PORT": os.getenv("PORT"),
        "BRICKHOUND_CATALOG": os.getenv("BRICKHOUND_CATALOG"),
        "BRICKHOUND_SCHEMA": os.getenv("BRICKHOUND_SCHEMA"),
        "DATABRICKS_WAREHOUSE_HTTP_PATH": os.getenv("DATABRICKS_WAREHOUSE_HTTP_PATH")
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    print(f"Starting BrickHound Test App on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

