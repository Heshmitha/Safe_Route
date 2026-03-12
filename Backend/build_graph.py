import osmnx as ox
import pandas as pd
import networkx as nx
from scipy.spatial import cKDTree
import numpy as np
import os

# --- PATH CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, 'dataset', 'clean_crime_data_.csv')
GRAPH_FILE = os.path.join(BASE_DIR, 'Backend', 'models', 'chicago_downtown.graphml')

def build_graph():
    print("🏗️  Building Chicago Downtown Graph...")
    
    # Use ONLY the neighborhoods that worked
    neighborhoods = [
        'Loop, Chicago, Illinois',              # ✓ 393 nodes
        'Near North Side, Chicago, Illinois',   # ✓ 563 nodes
        'Near West Side, Chicago, Illinois'     # ✓ 1125 nodes
    ]
    
    print(f"📍 Downloading {len(neighborhoods)} neighborhoods...")
    graphs = []
    
    for i, neighborhood in enumerate(neighborhoods, 1):
        print(f"  {i}/{len(neighborhoods)}: {neighborhood}")
        G_neighborhood = ox.graph_from_place(neighborhood, network_type='drive')
        print(f"     → {len(G_neighborhood.nodes)} nodes")
        graphs.append(G_neighborhood)
    
    # Combine all graphs using networkx compose (works with OSMnx graphs)
    print("🔄 Merging neighborhood graphs using NetworkX...")
    G = graphs[0]
    for g in graphs[1:]:
        # Use networkx.compose instead of ox.compose
        G = nx.compose(G, g)
    
    print(f"✅ Combined Graph Ready!")
    print(f"   Total Nodes: {len(G.nodes)}")
    print(f"   Total Edges: {len(G.edges)}")

    print("📊 Loading Crime Data...")
    if not os.path.exists(DATA_FILE):
        print(f"❌ Error: Could not find {DATA_FILE}")
        return

    df = pd.read_csv(DATA_FILE)
    
    # Get graph bounds
    nodes = ox.graph_to_gdfs(G, nodes=True, edges=False)
    min_lat, max_lat = nodes.y.min(), nodes.y.max()
    min_lon, max_lon = nodes.x.min(), nodes.x.max()
    print(f"   Graph bounds: Lat({min_lat:.4f} to {max_lat:.4f}), Lon({min_lon:.4f} to {max_lon:.4f})")
    
    # Filter crimes to our area
    buffer = 0.01
    df_filtered = df[
        (df['Latitude'] >= min_lat - buffer) & 
        (df['Latitude'] <= max_lat + buffer) &
        (df['Longitude'] >= min_lon - buffer) & 
        (df['Longitude'] <= max_lon + buffer)
    ]
    
    crime_coords = df_filtered[['Latitude', 'Longitude']].dropna().values
    print(f"   Using {len(crime_coords)} crimes in this area")

    print("🔗 Mapping Crimes to Streets...")
    node_coords = np.array(list(zip(nodes.y, nodes.x)))
    tree = cKDTree(node_coords)
    distances, indices = tree.query(crime_coords, k=1)

    # Count crimes at each node
    node_crime_counts = pd.Series(indices).value_counts().sort_index()
    node_ids = nodes.index.tolist()
    crime_map = {}
    for i, count in node_crime_counts.items():
        crime_map[node_ids[i]] = count
    
    avg_crimes = np.mean(list(crime_map.values())) if crime_map else 0
    print(f"   Average crimes per node: {avg_crimes:.1f}")

    print("⚖️ Calculating Safety Weights...")
    CRIME_PENALTY_FACTOR = 15
    
    edge_count = 0
    total_edges = len(G.edges)
    for u, v, data in G.edges(data=True):
        length = data.get('length', 10)
        u_crimes = crime_map.get(u, 0)
        v_crimes = crime_map.get(v, 0)
        total_crimes = u_crimes + v_crimes
        
        data['safety_weight'] = length + (total_crimes * CRIME_PENALTY_FACTOR) + 1
        data['crime_count'] = total_crimes
        
        edge_count += 1
        if edge_count % 500 == 0:
            print(f"   Processed {edge_count}/{total_edges} edges...")

    print("💾 Saving Graph...")
    ox.save_graphml(G, GRAPH_FILE)
    
    # Get file size
    file_size = os.path.getsize(GRAPH_FILE) / (1024 * 1024)
    print(f"🎉 Success! Graph saved to: {GRAPH_FILE}")
    print(f"📁 File size: {file_size:.2f} MB")
    print(f"📊 Final Stats:")
    print(f"   • Nodes: {len(G.nodes)}")
    print(f"   • Edges: {len(G.edges)}")
    print(f"   • Area covers: Loop, Near North, Near West Chicago")

if __name__ == "__main__":
    build_graph()