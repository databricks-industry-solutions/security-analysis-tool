#!/usr/bin/env python3
"""
Simple Flask app to test rendering
"""

from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>BrickHound Test</title>
        <style>
            body { font-family: Arial; padding: 50px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
            .container { background: white; color: black; padding: 30px; border-radius: 10px; }
            h1 { color: #ff6b6b; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔴 BrickHound - Simple Test</h1>
            <p>If you see this, HTML rendering works!</p>
            <p><strong>Next step:</strong> Debug why full template fails</p>
            <hr>
            <p>Environment:</p>
            <ul>
                <li>Catalog: """ + os.getenv('BRICKHOUND_CATALOG', 'not set') + """</li>
                <li>Schema: """ + os.getenv('BRICKHOUND_SCHEMA', 'not set') + """</li>
                <li>Warehouse: """ + os.getenv('DATABRICKS_WAREHOUSE_HTTP_PATH', 'not set') + """</li>
            </ul>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return '{"status":"healthy","service":"brickhound-simple"}'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    print(f"Starting Simple Flask App on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

