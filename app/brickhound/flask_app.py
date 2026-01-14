#!/usr/bin/env python3
"""
Flask-based Databricks App for BrickHound Security Analysis
Modeled after the successful TRP Compliance App pattern.
"""

from flask import Flask, render_template_string, request, jsonify
import os
from databricks import sql
from databricks.sdk.core import Config
import pandas as pd
from typing import Optional, Dict
import json

app = Flask(__name__)
app.secret_key = 'brickhound_secret_key_change_in_production'

# Load configuration
CATALOG = os.getenv("BRICKHOUND_CATALOG", "arunuc")
SCHEMA = os.getenv("BRICKHOUND_SCHEMA", "brickhound")
VERTICES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_vertices"
EDGES_TABLE = f"{CATALOG}.{SCHEMA}.brickhound_edges"


# Initialize Databricks connection
def get_databricks_connection():
    """Get Databricks SQL connection using workspace context"""
    cfg = Config()
    http_path = os.getenv("DATABRICKS_WAREHOUSE_HTTP_PATH")
    
    return sql.connect(
        server_hostname=cfg.host.replace("https://", ""),
        http_path=http_path,
        access_token=cfg.token
    )


class BrickHoundAnalyzer:
    """Core analyzer that powers all 7 interactive analyses"""
    
    def __init__(self):
        self._conn = None  # Lazy connection
        self.vertices_table = VERTICES_TABLE
        self.edges_table = EDGES_TABLE
        
        # Permission hierarchy
        self.permission_hierarchy = {
            'ALL PRIVILEGES': 100,
            'MANAGE': 80,
            'MODIFY': 60,
            'SELECT': 40,
            'USE SCHEMA': 30,
            'USE CATALOG': 20,
            'BROWSE': 10
        }
    
    @property
    def conn(self):
        """Lazy database connection - only connect when needed"""
        if self._conn is None:
            self._conn = get_databricks_connection()
        return self._conn
    
    def _execute_query(self, query: str) -> pd.DataFrame:
        """Execute SQL query and return pandas DataFrame"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=columns)
        finally:
            cursor.close()
    
    def _sanitize_input(self, value: str) -> str:
        """Sanitize input to prevent SQL injection"""
        if not value:
            return value
        return value.replace("'", "''")
    
    def _find_vertex_by_name(self, name: str) -> Optional[Dict]:
        """Find a vertex by name, display_name, or email"""
        safe_name = self._sanitize_input(name)
        query = f"""
        SELECT * FROM {self.vertices_table}
        WHERE name = '{safe_name}' 
           OR display_name = '{safe_name}'
           OR email = '{safe_name}'
        LIMIT 1
        """
        df = self._execute_query(query)
        return df.to_dict('records')[0] if not df.empty else None
    
    def get_graph_stats(self) -> Dict:
        """Get overall graph statistics"""
        stats_query = f"""
        SELECT 
            (SELECT COUNT(*) FROM {self.vertices_table}) as total_vertices,
            (SELECT COUNT(*) FROM {self.edges_table}) as total_edges,
            (SELECT COUNT(*) FROM {self.vertices_table} WHERE node_type = 'User') as total_users,
            (SELECT COUNT(*) FROM {self.vertices_table} WHERE node_type = 'ServicePrincipal') as total_sps,
            (SELECT COUNT(*) FROM {self.vertices_table} WHERE node_type = 'Group') as total_groups,
            (SELECT COUNT(*) FROM {self.vertices_table} WHERE node_type IN ('Catalog', 'Schema', 'Table', 'View')) as total_resources,
            (SELECT COUNT(*) FROM {self.edges_table} WHERE permission_level IS NOT NULL) as total_grants
        """
        
        df = self._execute_query(stats_query)
        return df.to_dict('records')[0] if not df.empty else {}
    
    def quick_check(self, principal: str, resource: str) -> Dict:
        """Quick yes/no check if principal can access resource"""
        principal_vertex = self._find_vertex_by_name(principal)
        if not principal_vertex:
            return {"success": False, "message": f"❌ Principal '{principal}' not found"}
        
        resource_vertex = self._find_vertex_by_name(resource)
        if not resource_vertex:
            return {"success": False, "message": f"❌ Resource '{resource}' not found"}
        
        query = f"""
        SELECT 
            e.permission_level,
            e.inherited,
            CASE WHEN e.inherited THEN 'Inherited' ELSE 'Direct' END as grant_type
        FROM {self.edges_table} e
        WHERE e.src = '{principal_vertex['id']}'
          AND e.dst = '{resource_vertex['id']}'
          AND e.permission_level IS NOT NULL
        LIMIT 5
        """
        
        df = self._execute_query(query)
        
        if df.empty:
            return {
                "success": True,
                "has_access": False,
                "message": f"❌ NO ACCESS - {principal_vertex.get('display_name', principal)} cannot access {resource_vertex['name']}",
                "data": []
            }
        
        return {
            "success": True,
            "has_access": True,
            "message": f"✅ YES - {principal_vertex.get('display_name', principal)} has {df['permission_level'].iloc[0]} on {resource_vertex['name']}",
            "data": df.to_dict('records')
        }
    
    def who_can_access(self, resource: str) -> Dict:
        """List all principals with access to a resource"""
        resource_vertex = self._find_vertex_by_name(resource)
        if not resource_vertex:
            return {"success": False, "message": f"❌ Resource '{resource}' not found"}
        
        query = f"""
        SELECT DISTINCT
            v.name as principal_name,
            v.display_name as principal_display_name,
            v.node_type as principal_type,
            e.permission_level,
            CASE WHEN e.inherited THEN 'Inherited' ELSE 'Direct' END as grant_type
        FROM {self.edges_table} e
        JOIN {self.vertices_table} v ON e.src = v.id
        WHERE e.dst = '{resource_vertex['id']}'
          AND e.permission_level IS NOT NULL
          AND v.node_type IN ('User', 'ServicePrincipal', 'Group')
        ORDER BY permission_level
        LIMIT 100
        """
        
        df = self._execute_query(query)
        
        return {
            "success": True,
            "message": f"📊 {len(df)} principal(s) have access to {resource_vertex['name']}",
            "resource_type": resource_vertex['node_type'],
            "data": df.to_dict('records')
        }
    
    def what_can_user_access(self, principal: str, resource_type: str = "All") -> Dict:
        """List all resources a principal can access"""
        principal_vertex = self._find_vertex_by_name(principal)
        if not principal_vertex:
            return {"success": False, "message": f"❌ Principal '{principal}' not found"}
        
        type_filter = "" if resource_type == "All" else f"AND v.node_type = '{resource_type}'"
        
        query = f"""
        SELECT DISTINCT
            v.name as resource_name,
            v.node_type as resource_type,
            e.permission_level,
            CASE WHEN e.inherited THEN 'Inherited' ELSE 'Direct' END as grant_type
        FROM {self.edges_table} e
        JOIN {self.vertices_table} v ON e.dst = v.id
        WHERE e.src = '{principal_vertex['id']}'
          AND e.permission_level IS NOT NULL
          {type_filter}
        ORDER BY v.node_type, v.name
        LIMIT 100
        """
        
        df = self._execute_query(query)
        
        return {
            "success": True,
            "message": f"📊 {len(df)} resource(s) accessible",
            "principal": principal_vertex.get('display_name', principal),
            "data": df.to_dict('records')
        }
    
    def effective_permissions(self, principal: str, resource: str) -> Dict:
        """Show effective permissions with all sources"""
        principal_vertex = self._find_vertex_by_name(principal)
        resource_vertex = self._find_vertex_by_name(resource)
        
        if not principal_vertex:
            return {"success": False, "message": f"❌ Principal '{principal}' not found"}
        if not resource_vertex:
            return {"success": False, "message": f"❌ Resource '{resource}' not found"}
        
        query = f"""
        WITH all_sources AS (
            SELECT 
                'DIRECT' as source,
                permission_level,
                FALSE as inherited
            FROM {self.edges_table}
            WHERE src = '{principal_vertex['id']}'
              AND dst = '{resource_vertex['id']}'
              AND permission_level IS NOT NULL
            
            UNION ALL
            
            SELECT 
                'GROUP_MEMBERSHIP' as source,
                e2.permission_level,
                TRUE as inherited
            FROM {self.edges_table} e1
            JOIN {self.edges_table} e2 ON e1.dst = e2.src
            WHERE e1.src = '{principal_vertex['id']}'
              AND e2.dst = '{resource_vertex['id']}'
              AND e1.relationship = 'MemberOf'
              AND e2.permission_level IS NOT NULL
            
            UNION ALL
            
            SELECT 
                'OWNERSHIP' as source,
                'ALL PRIVILEGES' as permission_level,
                FALSE as inherited
            FROM {self.vertices_table}
            WHERE id = '{resource_vertex['id']}'
              AND owner = '{principal_vertex['id']}'
        )
        SELECT * FROM all_sources
        """
        
        df = self._execute_query(query)
        
        if df.empty:
            return {"success": True, "has_permission": False, "message": "❌ NO ACCESS", "data": []}
        
        # Determine highest permission
        max_level = max([self.permission_hierarchy.get(p, 0) for p in df['permission_level']])
        highest = [k for k, v in self.permission_hierarchy.items() if v == max_level][0]
        
        return {
            "success": True,
            "has_permission": True,
            "effective_permission": highest,
            "message": f"🔐 Effective Permission: {highest}",
            "principal": principal_vertex.get('display_name', principal),
            "resource": resource_vertex['name'],
            "data": df.to_dict('records')
        }
    
    def privilege_escalation_risk(self, principal: str) -> Dict:
        """Analyze privilege escalation risk"""
        principal_vertex = self._find_vertex_by_name(principal)
        if not principal_vertex:
            return {"success": False, "message": f"❌ Principal '{principal}' not found"}
        
        query = f"""
        SELECT 
            v.name as target_resource,
            v.node_type as target_type,
            e.permission_level,
            CASE WHEN e.relationship = 'MemberOf' THEN 'VIA_GROUP' ELSE 'DIRECT' END as path_type
        FROM {self.edges_table} e
        JOIN {self.vertices_table} v ON e.dst = v.id
        WHERE e.src = '{principal_vertex['id']}'
          AND e.permission_level IN ('ALL PRIVILEGES', 'MANAGE')
          AND v.node_type IN ('Catalog', 'Schema')
        LIMIT 50
        """
        
        df = self._execute_query(query)
        
        if df.empty:
            return {"success": True, "risk_level": "LOW", "message": "✅ LOW RISK", "data": []}
        
        admin_count = len(df[df['permission_level'] == 'ALL PRIVILEGES'])
        manage_count = len(df[df['permission_level'] == 'MANAGE'])
        risk_score = (admin_count * 3) + (manage_count * 2)
        
        if risk_score > 10:
            risk_level = "CRITICAL"
            icon = "🔴"
        elif risk_score > 5:
            risk_level = "HIGH"
            icon = "🟠"
        elif risk_score > 0:
            risk_level = "MEDIUM"
            icon = "🟡"
        else:
            risk_level = "LOW"
            icon = "🟢"
        
        return {
            "success": True,
            "risk_level": risk_level,
            "message": f"{icon} {risk_level} RISK - {len(df)} admin-level access(es)",
            "principal": principal_vertex.get('display_name', principal),
            "admin_count": admin_count,
            "manage_count": manage_count,
            "data": df.to_dict('records')
        }


# Initialize analyzer (lazy - won't connect until first use)
analyzer = None

def get_analyzer():
    """Get or create analyzer instance"""
    global analyzer
    if analyzer is None:
        analyzer = BrickHoundAnalyzer()
    return analyzer


# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔴 BrickHound - Databricks Security Analysis</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { opacity: 0.9; font-size: 1.1em; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            padding: 30px;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-card .number { font-size: 2em; font-weight: bold; color: #667eea; }
        .stat-card .label { color: #666; font-size: 0.9em; margin-top: 5px; }
        .main-content { padding: 30px; }
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        .tab {
            padding: 12px 24px;
            background: #e9ecef;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s;
        }
        .tab:hover { background: #dee2e6; }
        .tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 6px;
            font-size: 1em;
            transition: border-color 0.3s;
        }
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #667eea;
        }
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 14px 32px;
            border: none;
            border-radius: 6px;
            font-size: 1.1em;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .result {
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            display: none;
        }
        .result.show { display: block; }
        .result-message {
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 6px;
            font-weight: 600;
        }
        .result-message.success { background: #d4edda; color: #155724; }
        .result-message.error { background: #f8d7da; color: #721c24; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }
        th {
            background: #667eea;
            color: white;
            font-weight: 600;
        }
        tr:hover { background: #f8f9fa; }
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }
        .loading.show { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔴 BrickHound</h1>
            <p>Databricks Security & Permission Analysis</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="number">{{ stats.total_vertices|default(0) }}</div>
                <div class="label">Vertices</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.total_edges|default(0) }}</div>
                <div class="label">Edges</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.total_users|default(0) }}</div>
                <div class="label">Users</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.total_groups|default(0) }}</div>
                <div class="label">Groups</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.total_resources|default(0) }}</div>
                <div class="label">Resources</div>
            </div>
            <div class="stat-card">
                <div class="number">{{ stats.total_grants|default(0) }}</div>
                <div class="label">Grants</div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="tabs">
                <button class="tab active" onclick="showTab('quick-check')">1️⃣ Quick Check</button>
                <button class="tab" onclick="showTab('who-can-access')">2️⃣ Who Can Access?</button>
                <button class="tab" onclick="showTab('what-access')">3️⃣ What Can Access?</button>
                <button class="tab" onclick="showTab('effective')">4️⃣ Effective Permissions</button>
                <button class="tab" onclick="showTab('escalation')">7️⃣ Escalation Risk</button>
            </div>
            
            <!-- Tab 1: Quick Check -->
            <div id="quick-check" class="tab-content active">
                <h2>🎯 Quick Access Check</h2>
                <p>Simple yes/no: Can a user access a resource?</p>
                <div class="form-row" style="margin-top: 20px;">
                    <div class="form-group">
                        <label>Principal (Email/Name)</label>
                        <input type="text" id="qc-principal" placeholder="user@company.com">
                    </div>
                    <div class="form-group">
                        <label>Resource (Full Name)</label>
                        <input type="text" id="qc-resource" placeholder="catalog.schema.table">
                    </div>
                </div>
                <button class="btn" onclick="runQuickCheck()">🔍 Check Access</button>
                <div class="loading" id="qc-loading">⏳ Checking...</div>
                <div class="result" id="qc-result"></div>
            </div>
            
            <!-- Tab 2: Who Can Access -->
            <div id="who-can-access" class="tab-content">
                <h2>👥 Who Can Access This Resource?</h2>
                <p>List all principals with access to a specific resource</p>
                <div class="form-group" style="margin-top: 20px;">
                    <label>Resource (Full Name)</label>
                    <input type="text" id="wca-resource" placeholder="catalog.schema.table">
                </div>
                <button class="btn" onclick="runWhoCanAccess()">🔍 Find Principals</button>
                <div class="loading" id="wca-loading">⏳ Searching...</div>
                <div class="result" id="wca-result"></div>
            </div>
            
            <!-- Tab 3: What Can Access -->
            <div id="what-access" class="tab-content">
                <h2>🔐 What Can This User Access?</h2>
                <p>List all resources accessible to a principal</p>
                <div class="form-row" style="margin-top: 20px;">
                    <div class="form-group">
                        <label>Principal (Email/Name)</label>
                        <input type="text" id="wa-principal" placeholder="user@company.com">
                    </div>
                    <div class="form-group">
                        <label>Resource Type Filter</label>
                        <select id="wa-type">
                            <option value="All">All</option>
                            <option value="Catalog">Catalog</option>
                            <option value="Schema">Schema</option>
                            <option value="Table">Table</option>
                            <option value="View">View</option>
                            <option value="Cluster">Cluster</option>
                        </select>
                    </div>
                </div>
                <button class="btn" onclick="runWhatAccess()">🔍 Find Resources</button>
                <div class="loading" id="wa-loading">⏳ Searching...</div>
                <div class="result" id="wa-result"></div>
            </div>
            
            <!-- Tab 4: Effective Permissions -->
            <div id="effective" class="tab-content">
                <h2>🔐 Effective Permissions Analysis</h2>
                <p>Show all permission sources and calculate effective access</p>
                <div class="form-row" style="margin-top: 20px;">
                    <div class="form-group">
                        <label>Principal (Email/Name)</label>
                        <input type="text" id="ep-principal" placeholder="user@company.com">
                    </div>
                    <div class="form-group">
                        <label>Resource (Full Name)</label>
                        <input type="text" id="ep-resource" placeholder="catalog.schema.table">
                    </div>
                </div>
                <button class="btn" onclick="runEffectivePermissions()">🔍 Analyze Permissions</button>
                <div class="loading" id="ep-loading">⏳ Analyzing...</div>
                <div class="result" id="ep-result"></div>
            </div>
            
            <!-- Tab 5: Escalation Risk -->
            <div id="escalation" class="tab-content">
                <h2>🔺 Privilege Escalation Risk Analysis</h2>
                <p>Identify attack paths to admin-level resources</p>
                <div class="form-group" style="margin-top: 20px;">
                    <label>Principal (Email/Name)</label>
                    <input type="text" id="esc-principal" placeholder="user@company.com">
                </div>
                <button class="btn" onclick="runEscalationRisk()">🔍 Analyze Risk</button>
                <div class="loading" id="esc-loading">⏳ Analyzing...</div>
                <div class="result" id="esc-result"></div>
            </div>
        </div>
    </div>
    
    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
        }
        
        function displayTable(data) {
            if (!data || data.length === 0) return '<p>No data to display</p>';
            
            const keys = Object.keys(data[0]);
            let html = '<table><thead><tr>';
            keys.forEach(key => html += `<th>${key}</th>`);
            html += '</tr></thead><tbody>';
            
            data.forEach(row => {
                html += '<tr>';
                keys.forEach(key => html += `<td>${row[key] || ''}</td>`);
                html += '</tr>';
            });
            html += '</tbody></table>';
            return html;
        }
        
        async function runQuickCheck() {
            const principal = document.getElementById('qc-principal').value;
            const resource = document.getElementById('qc-resource').value;
            const loading = document.getElementById('qc-loading');
            const result = document.getElementById('qc-result');
            
            loading.classList.add('show');
            result.classList.remove('show');
            
            try {
                const response = await fetch('/api/quick-check', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({principal, resource})
                });
                const data = await response.json();
                
                result.innerHTML = `
                    <div class="result-message ${data.success ? 'success' : 'error'}">
                        ${data.message}
                    </div>
                    ${data.data ? displayTable(data.data) : ''}
                `;
                result.classList.add('show');
            } catch (err) {
                result.innerHTML = `<div class="result-message error">Error: ${err.message}</div>`;
                result.classList.add('show');
            }
            loading.classList.remove('show');
        }
        
        async function runWhoCanAccess() {
            const resource = document.getElementById('wca-resource').value;
            const loading = document.getElementById('wca-loading');
            const result = document.getElementById('wca-result');
            
            loading.classList.add('show');
            result.classList.remove('show');
            
            try {
                const response = await fetch('/api/who-can-access', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({resource})
                });
                const data = await response.json();
                
                result.innerHTML = `
                    <div class="result-message success">${data.message}</div>
                    ${data.data ? displayTable(data.data) : ''}
                `;
                result.classList.add('show');
            } catch (err) {
                result.innerHTML = `<div class="result-message error">Error: ${err.message}</div>`;
                result.classList.add('show');
            }
            loading.classList.remove('show');
        }
        
        async function runWhatAccess() {
            const principal = document.getElementById('wa-principal').value;
            const resourceType = document.getElementById('wa-type').value;
            const loading = document.getElementById('wa-loading');
            const result = document.getElementById('wa-result');
            
            loading.classList.add('show');
            result.classList.remove('show');
            
            try {
                const response = await fetch('/api/what-can-access', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({principal, resource_type: resourceType})
                });
                const data = await response.json();
                
                result.innerHTML = `
                    <div class="result-message success">${data.message}</div>
                    ${data.data ? displayTable(data.data) : ''}
                `;
                result.classList.add('show');
            } catch (err) {
                result.innerHTML = `<div class="result-message error">Error: ${err.message}</div>`;
                result.classList.add('show');
            }
            loading.classList.remove('show');
        }
        
        async function runEffectivePermissions() {
            const principal = document.getElementById('ep-principal').value;
            const resource = document.getElementById('ep-resource').value;
            const loading = document.getElementById('ep-loading');
            const result = document.getElementById('ep-result');
            
            loading.classList.add('show');
            result.classList.remove('show');
            
            try {
                const response = await fetch('/api/effective-permissions', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({principal, resource})
                });
                const data = await response.json();
                
                result.innerHTML = `
                    <div class="result-message success">${data.message}</div>
                    ${data.data ? displayTable(data.data) : ''}
                `;
                result.classList.add('show');
            } catch (err) {
                result.innerHTML = `<div class="result-message error">Error: ${err.message}</div>`;
                result.classList.add('show');
            }
            loading.classList.remove('show');
        }
        
        async function runEscalationRisk() {
            const principal = document.getElementById('esc-principal').value;
            const loading = document.getElementById('esc-loading');
            const result = document.getElementById('esc-result');
            
            loading.classList.add('show');
            result.classList.remove('show');
            
            try {
                const response = await fetch('/api/escalation-risk', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({principal})
                });
                const data = await response.json();
                
                result.innerHTML = `
                    <div class="result-message ${data.risk_level === 'LOW' ? 'success' : 'error'}">
                        ${data.message}
                    </div>
                    ${data.data ? displayTable(data.data) : ''}
                `;
                result.classList.add('show');
            } catch (err) {
                result.innerHTML = `<div class="result-message error">Error: ${err.message}</div>`;
                result.classList.add('show');
            }
            loading.classList.remove('show');
        }
    </script>
</body>
</html>
"""


# Routes
@app.route('/')
def index():
    """Main page"""
    try:
        stats = get_analyzer().get_graph_stats()
    except Exception as e:
        print(f"Error getting stats: {e}")
        stats = {
            'total_vertices': 0,
            'total_edges': 0,
            'total_users': 0,
            'total_groups': 0,
            'total_resources': 0,
            'total_grants': 0
        }
    return render_template_string(HTML_TEMPLATE, stats=stats)


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "brickhound"})


@app.route('/api/quick-check', methods=['POST'])
def api_quick_check():
    """Quick check API"""
    try:
        data = request.json
        result = get_analyzer().quick_check(data['principal'], data['resource'])
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


@app.route('/api/who-can-access', methods=['POST'])
def api_who_can_access():
    """Who can access API"""
    try:
        data = request.json
        result = get_analyzer().who_can_access(data['resource'])
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


@app.route('/api/what-can-access', methods=['POST'])
def api_what_can_access():
    """What can access API"""
    try:
        data = request.json
        result = get_analyzer().what_can_user_access(data['principal'], data.get('resource_type', 'All'))
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


@app.route('/api/effective-permissions', methods=['POST'])
def api_effective_permissions():
    """Effective permissions API"""
    try:
        data = request.json
        result = get_analyzer().effective_permissions(data['principal'], data['resource'])
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


@app.route('/api/escalation-risk', methods=['POST'])
def api_escalation_risk():
    """Escalation risk API"""
    try:
        data = request.json
        result = get_analyzer().privilege_escalation_risk(data['principal'])
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    print(f"Starting BrickHound App on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

