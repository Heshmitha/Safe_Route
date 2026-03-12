from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import networkx as nx
import osmnx as ox
import os
import requests
import tempfile
from dotenv import load_dotenv

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Google Drive direct download URL for the graph file
GRAPH_URL = "https://drive.google.com/uc?export=download&id=18UjvX-FJZ4nD1dX4CBiBxNfnwwjKgRxI"
# Use /tmp directory (writable on Vercel)
TEMP_DIR = tempfile.gettempdir()
GRAPH_FILE = os.path.join(TEMP_DIR, 'chicago_graph.graphml')

# Force Python to find the .env file right next to app.py
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)

MAPBOX_TOKEN = os.getenv('MAPBOX_TOKEN')
print("🔑 Loaded Mapbox Token:", MAPBOX_TOKEN)

app = Flask(__name__, template_folder='../Frontend', static_folder='../Frontend/static')

# FIXED: Configure CORS to allow your frontend domains
CORS(app, origins=[
    "https://safe-route-1-4r1q.onrender.com",  # Your frontend URL
    "http://localhost:5000",                    # Local development
    "http://127.0.0.1:5000"                     # Local development
])

G = None

def download_graph():
    """Download graph file from Google Drive to temp directory"""
    global G
    print(f"📥 Checking for graph file at: {GRAPH_FILE}")
    
    # Check if already downloaded
    if os.path.exists(GRAPH_FILE):
        file_size = os.path.getsize(GRAPH_FILE)
        print(f"✅ Graph already exists in temp: {file_size} bytes")
        return True
    
    # Download the file
    print(f"⏳ Downloading graph from Google Drive...")
    try:
        response = requests.get(GRAPH_URL, stream=True, timeout=60)
        response.raise_for_status()
        
        # Get file size for progress tracking
        total_size = int(response.headers.get('content-length', 0))
        print(f"📊 File size: {total_size / (1024*1024):.2f} MB")
        
        # Download with progress
        with open(GRAPH_FILE, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    if int(percent) % 10 == 0:  # Print every 10%
                        print(f"⏳ Download progress: {percent:.0f}%")
        
        print(f"✅ Graph downloaded successfully to temp: {GRAPH_FILE}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to download graph: {e}")
        return False

def load_graph():
    global G
    print("⏳ Loading Street Network...")
    
    # First ensure graph is downloaded
    if not download_graph():
        print("❌ Cannot proceed without graph file")
        return
    
    if os.path.exists(GRAPH_FILE):
        G = ox.load_graphml(GRAPH_FILE)
        # Convert attributes to numbers
        for u, v, data in G.edges(data=True):
            data['length'] = float(data.get('length', 10.0))
            data['safety_weight'] = float(data.get('safety_weight', 10.0))
        print(f"✅ Graph Ready! Nodes: {len(G.nodes)}")
    else:
        print("❌ Graph file not found!")

load_graph()

def get_path_stats(G, path, weight_col='safety_weight'):
    """Calculates Total Distance and Total Risk for a given path."""
    total_dist = 0
    total_risk = 0
    for i in range(len(path) - 1):
        u, v = path[i], path[i+1]
        # Get edge data (handle multi-edges)
        edge_data = G.get_edge_data(u, v)[0] 
        total_dist += edge_data.get('length', 0)
        # Risk is the 'safety_weight' minus the 'length' (pure crime penalty)
        risk = edge_data.get('safety_weight', 0) - edge_data.get('length', 0)
        total_risk += max(0, risk) # Ensure non-negative
        
    return int(total_dist), int(total_risk)


# ==========================================
# --- WEB ROUTES (Fixed for Multi-Page) ----
# ==========================================

@app.route('/')
def home():
    return render_template('index.html', mapbox_token=MAPBOX_TOKEN)

@app.route('/navigation')
def navigation():
    # THIS FIXES THE BLANK MAP: We pass the MAPBOX_TOKEN securely to the map page!
    return render_template('navigation.html', mapbox_token=MAPBOX_TOKEN)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


# ==========================================
# --- API ROUTE (AI Pathfinding) -----------
# ==========================================

@app.route('/api/get_safe_path', methods=['POST'])
def get_safe_path():
    data = request.json
    start_lat, start_lon = data.get('start_lat'), data.get('start_lon')
    end_lat, end_lon = data.get('end_lat'), data.get('end_lon')
    
    # Capture travel mode if passed from frontend
    mode = data.get('mode', 'walk')

    if not G: return jsonify({"error": "Graph not loaded"}), 500

    try:
        orig_node = ox.nearest_nodes(G, start_lon, start_lat)
        dest_node = ox.nearest_nodes(G, end_lon, end_lat)

        # 1. Calculate Risky Path (Shortest Distance)
        risky_path = nx.shortest_path(G, orig_node, dest_node, weight='length')
        risky_dist, risky_score = get_path_stats(G, risky_path)

        # 2. Calculate Safe Path (Lowest Safety Weight)
        safe_path = nx.shortest_path(G, orig_node, dest_node, weight='safety_weight')
        safe_dist, safe_score = get_path_stats(G, safe_path)

        return jsonify({
            "risky_path": [[G.nodes[n]['y'], G.nodes[n]['x']] for n in risky_path],
            "risky_dist": risky_dist,
            "risky_score": risky_score,
            
            "safe_path": [[G.nodes[n]['y'], G.nodes[n]['x']] for n in safe_path],
            "safe_dist": safe_dist,
            "safe_score": safe_score
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)