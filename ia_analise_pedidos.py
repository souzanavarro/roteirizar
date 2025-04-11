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
from typing import List, Tuple, Optional, Dict

# Configuração de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configurações fixas
endereco_partida_coords = (-23.0838, -47.1336)  # Coordenadas do ponto de partida

@st.cache_data
def obter_coordenadas_com_fallback(endereco: str, cache: Dict[str, Tuple[float, float]]) -> Tuple[Optional[float], Optional[float]]:
    """
    Tenta obter coordenadas de um endereço utilizando um cache local como fallback.
    """
    if endereco in cache:
        return cache[endereco]
    
    coordenadas = obter_coordenadas_opencage(endereco)
    if coordenadas:
        cache[endereco] = coordenadas
    else:
        logging.warning(f"Coordenadas não encontradas para o endereço: {endereco}")
    return coordenadas or (None, None)

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
    if not (-90 <= coords_1[0] <= 90 and -180 <= coords_1[1] <= 180):
        raise ValueError(f"Coordenadas inválidas: {coords_1}")
    if not (-90 <= coords_2[0] <= 90 and -180 <= coords_2[1] <= 180):
        raise ValueError(f"Coordenadas inválidas: {coords_2}")
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

def resolver_tsp_genetico(G: nx.Graph) -> Tuple[List[str], float]:
    """
    Resolve o TSP utilizando um algoritmo genético simples.
    """
    def fitness(route):
        return sum(G.edges[route[i], route[i + 1]]['weight'] for i in range(len(route) - 1)) + \
               G.edges[route[-1], route[0]]['weight']

    def mutate(route):
        i, j = random.sample(range(len(route)), 2)
        route[i], route[j] = route[j], route[i]
        return route

    def crossover(route1, route2):
        size = len(route1)
        start, end = sorted(random.sample(range(size), 2))
        child = [None] * size
        child[start:end] = route1[start:end]
        pointer = 0
        for i in range(size):
            if route2[i] not in child:
                while child[pointer] is not None:
                    pointer += 1
                child[pointer] = route2[i]
        return child

    def genetic_algorithm(population, generations=100, mutation_rate=0.01):
        for _ in range(generations):
            population = sorted(population, key=lambda route: fitness(route))
            next_generation = population[:2]
            for _ in range(len(population) // 2 - 1):
                parents = random.sample(population[:10], 2)
                child = crossover(parents[0], parents[1])
                if random.random() < mutation_rate:
                    child = mutate(child)
                next_generation.append(child)
            population = next_generation
        return population[0], fitness(population[0])

    nodes = list(G.nodes)
    population = [random.sample(nodes, len(nodes)) for _ in range(100)]
    best_route, best_distance = genetic_algorithm(population)

    logging.info(f"Melhor rota TSP: {best_route}")
    st.write(f"Melhor rota TSP: {best_route}")
    st.write(f"Distância total: {best_distance:.2f} metros")
    
    return best_route, best_distance

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

def exportar_grafo(grafo: nx.Graph, formato: str = "json") -> str:
    """
    Exporta o grafo em formato JSON ou GML.
    """
    if formato == "json":
        return nx.node_link_data(grafo)
    elif formato == "gml":
        return nx.generate_gml(grafo)
    else:
        raise ValueError("Formato não suportado.")

def calcular_metricas_grafo(grafo: nx.Graph) -> dict:
    """
    Calcula métricas do grafo, como densidade, diâmetro e grau médio.
    """
    return {
        "densidade": nx.density(grafo),
        "diâmetro": nx.diameter(grafo) if nx.is_connected(grafo) else None,
        "grau_médio": sum(dict(grafo.degree()).values()) / grafo.number_of_nodes()
    }
