import os
import requests
import streamlit as st
import random
import networkx as nx
from itertools import permutations
from geopy.distance import geodesic
from sklearn.cluster import KMeans
import folium
import pandas as pd
import logging
from typing import List, Tuple, Optional

# Configuração de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configurações de partida
endereco_partida_coords = (-23.0838, -47.1336)  # Coordenadas do ponto de partida

@st.cache_data
def obter_coordenadas_opencage(endereco: str) -> Optional[Tuple[float, float]]:
    """
    Obtém as coordenadas de um endereço utilizando a API do OpenCage.
    """
    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key:
        logging.error("Chave da API OpenCage não configurada.")
        return None

    url = f"https://api.opencagedata.com/geocode/v1/json?q={endereco}&key={api_key}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if 'results' in data and len(data['results']) > 0:
            location = data['results'][0]['geometry']
            return location['lat'], location['lng']
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro na requisição à API OpenCage: {e}")
    return None

def calcular_distancia(coords_1: Tuple[float, float], coords_2: Tuple[float, float]) -> float:
    """
    Calcula a distância em metros entre duas coordenadas.
    """
    return geodesic(coords_1, coords_2).meters

def criar_grafo_tsp(pedidos_df: pd.DataFrame) -> nx.Graph:
    """
    Cria um grafo para o problema do caixeiro viajante (TSP).
    """
    G = nx.Graph()
    enderecos = pedidos_df['Endereço Completo'].unique()
    G.add_node("Partida", pos=endereco_partida_coords)
    
    for endereco in enderecos:
        coords = (
            pedidos_df.loc[pedidos_df['Endereço Completo'] == endereco, 'Latitude'].values[0],
            pedidos_df.loc[pedidos_df['Endereço Completo'] == endereco, 'Longitude'].values[0]
        )
        G.add_node(endereco, pos=coords)
    
    for (node1, node2) in permutations(["Partida"] + list(enderecos), 2):
        distancia = calcular_distancia(G.nodes[node1]['pos'], G.nodes[node2]['pos'])
        G.add_edge(node1, node2, weight=distancia)
    
    return G

def criar_mapa(pedidos_df: pd.DataFrame) -> folium.Map:
    """
    Cria e retorna um mapa Folium com marcadores para cada pedido.
    """
    mapa = folium.Map(location=endereco_partida_coords, zoom_start=12)
    for _, row in pedidos_df.iterrows():
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=f"Pedido: {row['Endereço Completo']}",
            icon=folium.Icon(color='blue')
        ).add_to(mapa)
    return mapa
