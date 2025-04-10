import requests
import streamlit as st
import random
import networkx as nx
from itertools import permutations
from geopy.distance import geodesic
from sklearn.cluster import KMeans
import folium
from config import endereco_partida, endereco_partida_coords
from config import GRAPH_HOPPER_API_KEY
import math
import pandas as pd
import logging

def obter_coordenadas_opencage(endereco):
    """
    Obtém as coordenadas de um endereço utilizando a API do OpenCage.
    """
    try:
        api_key = "6f522c67add14152926990afbe127384"  # Substitua pela sua chave de API
        url = f"https://api.opencagedata.com/geocode/v1/json?q={endereco}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        if 'status' in data and data['status']['code'] == 200 and 'results' in data:
            location = data['results'][0]['geometry']
            return (location['lat'], location['lng'])
        else:
            st.error(f"Não foi possível obter as coordenadas para o endereço: {endereco}.")
            return None
    except Exception as e:
        st.error(f"Erro ao tentar obter as coordenadas: {e}")
        return None

def obter_coordenadas_com_fallback(endereco, coordenadas_salvas):
    """
    Retorna as coordenadas salvas para um endereço ou tenta obtê-las via OpenCage.
    Se não obtiver, utiliza um dicionário de coordenadas manuais pré-definido.
    """
    if endereco in coordenadas_salvas:
        return coordenadas_salvas[endereco]
    
    coords = obter_coordenadas_opencage(endereco)
    if coords is None:
        # Exemplo de coordenadas manuais para endereços específicos
        coordenadas_manuais = {
            "Rua Araújo Leite, 146, Centro, Piedade, São Paulo, Brasil": (-23.71241093449893, -47.41796911054548)
        }
        coords = coordenadas_manuais.get(endereco, (None, None))
    
    if coords:
        coordenadas_salvas[endereco] = coords
    return coords

def calcular_distancia(coords_1, coords_2):
    """
    Calcula a distância em metros entre duas coordenadas.
    """
    # Validação das coordenadas
    if not (-90 <= coords_1[0] <= 90 and -180 <= coords_1[1] <= 180):
        raise ValueError(f"Coordenadas inválidas: {coords_1}")
    if not (-90 <= coords_2[0] <= 90 and -180 <= coords_2[1] <= 180):
        raise ValueError(f"Coordenadas inválidas: {coords_2}")
    
    return geodesic(coords_1, coords_2).meters

def criar_grafo_tsp(pedidos_df):
    """
    Cria um grafo (usando NetworkX) para o problema do caixeiro viajante (TSP).
    O nó de partida é definido em config e os demais nós são os endereços únicos da planilha.
    """
    G = nx.Graph()
    enderecos = pedidos_df['Endereço Completo'].unique()
    # Nó de partida
    G.add_node(endereco_partida, pos=endereco_partida_coords)
    for endereco in enderecos:
        coords = (
            pedidos_df.loc[pedidos_df['Endereço Completo'] == endereco, 'Latitude'].values[0],
            pedidos_df.loc[pedidos_df['Endereço Completo'] == endereco, 'Longitude'].values[0]
        )
        G.add_node(endereco, pos=coords)
    for (end1, end2) in permutations([endereco_partida] + list(enderecos), 2):
        distancia = calcular_distancia(G.nodes[end1]['pos'], G.nodes[end2]['pos'])
        if distancia is not None:
            G.add_edge(end1, end2, weight=distancia)
    return G

def resolver_tsp_genetico(G):
    """
    Resolve o TSP utilizando um algoritmo genético simples.
    Retorna a melhor rota encontrada e sua distância total.
    """
    def fitness(route):
        return sum(G.edges[route[i], route[i+1]]['weight'] for i in range(len(route) - 1)) + \
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

    def genetic_algorithm(population, generations=1000, mutation_rate=0.01):
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

    # Aplicar a rota aos pedidos
    st.write(f"Melhor rota TSP: {best_route}")
    st.write(f"Distância total: {best_distance:.2f} metros")

    return best_route, best_distance

def obter_rota_graphhopper(pedidos_df, caminhoes_df, GRAPH_HOPPER_API_KEY):
    """
    Obtém uma rota otimizada usando a API do GraphHopper.
    
    Args:
        pedidos_df (DataFrame): DataFrame contendo os pedidos com Latitude e Longitude.
        caminhoes_df (DataFrame): DataFrame contendo os veículos com capacidade.
        chave_api (str): Chave de API do GraphHopper.
    
    Returns:
        dict: Dados da rota otimizada ou None em caso de erro.
    """
    base_url = "https://graphhopper.com/api/1/vrp"
    
    # Criar a estrutura de entrada para a API
    vehicles = []
    for _, caminhao in caminhoes_df.iterrows():
        vehicles.append({
            "vehicle_id": caminhao['Placa'],
            "start_address": {
                "location_id": "depot",
                "lon": endereco_partida_coords[1],
                "lat": endereco_partida_coords[0]
            },
            "capacity": [int(caminhao['Capac. Kg']), int(caminhao['Capac. Cx'])],
            "type_id": "default"
        })
    
    services = []
    for _, pedido in pedidos_df.iterrows():
        services.append({
            "id": str(pedido.name),
            "name": pedido['Endereço Completo'],
            "address": {
                "location_id": str(pedido.name),
                "lon": pedido['Longitude'],
                "lat": pedido['Latitude']
            },
            "size": [int(pedido['Peso dos Itens']), int(pedido['Qtde. dos Itens'])]
        })
    
    # Montar o payload
    payload = {
        "vehicles": vehicles,
        "services": services
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    params = {
        "key": chave_api
    }
    
    # Fazer a requisição
    response = requests.post(base_url, json=payload, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Erro na requisição: {response.status_code} - {response.text}")
        return None

def resolver_vrp(pedidos_df, caminhoes_df):
    """
    Resolve o problema do VRP utilizando OR-Tools.
    
    O algoritmo constrói uma matriz de distâncias com base nas coordenadas dos pedidos.
    O número de veículos é determinado pelo número de caminhões disponíveis.
    
    Retorna:
      dict: Rotas para cada veículo, ou
      str: Mensagem de erro se a solução não for encontrada ou se OR-Tools não estiver instalado.
    """
    try:
        from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    except ImportError:
        return "Erro: OR-Tools não está instalado. Instale com: pip3 install ortools"

    # Obtenha as coordenadas dos pedidos
    coords = list(zip(pedidos_df['Latitude'], pedidos_df['Longitude']))
    if not coords:
        return "Sem pedidos para roteirização."

    depot = 0  # Usando o primeiro pedido (ou defina um depot específico)

    def calcular_dist(i, j):
        return int(math.sqrt((coords[i][0] - coords[j][0])**2 + (coords[i][1] - coords[j][1])**2) * 1000)

    N = len(coords)
    distance_matrix = [[calcular_dist(i, j) for j in range(N)] for i in range(N)]

    num_vehicles = len(caminhoes_df)
    if num_vehicles < 1:
        return "Nenhum caminhão disponível para a roteirização."

    # Cria o index manager e o modelo de roteamento
    manager = pywrapcp.RoutingIndexManager(N, num_vehicles, depot)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Parâmetros de busca
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

    solution = routing.SolveWithParameters(search_parameters)
    if solution:
        routes = {}
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route = []
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                route.append(pedidos_df.iloc[node]['Endereço Completo'])
                index = solution.Value(routing.NextVar(index))
            routes[f"Veículo {vehicle_id + 1}"] = route

        # Exibir as rotas
        for veiculo, rota in routes.items():
            st.write(f"{veiculo}: {rota}")

        return routes
    else:
        return "Não foi encontrada solução para o problema VRP."

def otimizar_aproveitamento_frota(pedidos_df, caminhoes_df, percentual_frota, max_pedidos, n_clusters, chave_api):
    """
    Otimiza a alocação dos pedidos aos caminhões disponíveis, agrupando os pedidos em regiões,
    atribuindo números de carga e placas. Divide os pedidos entre vários veículos, se necessário.
    """
    pedidos_df['Carga'] = 0
    pedidos_df['Placa'] = ""
    carga_numero = 1

    # Ajustar a capacidade dos caminhões conforme o percentual informado
    caminhoes_df['Capac. Kg'] *= (percentual_frota / 100)
    caminhoes_df['Capac. Cx'] *= (percentual_frota / 100)
    caminhoes_df = caminhoes_df[caminhoes_df['Disponível'] == 'Ativo']

    # Agrupar os pedidos em regiões
    pedidos_df = agrupar_por_regiao(pedidos_df, n_clusters)

    # Iterar sobre cada região
    for regiao in pedidos_df['Regiao'].unique():
        pedidos_regiao = pedidos_df[pedidos_df['Regiao'] == regiao]
        chave_api = "251e3452-13e3-4229-807a-45760bdf1207"
        rota_otimizada = obter_rota_graphhopper(pedidos_df, caminhoes_df, chave_api)

        if rota_otimizada:
            for rota in rota_otimizada['solution']['routes']:
                veiculo_id = rota['vehicle_id']
                for atividade in rota['activities']:
                    pedido_id = int(atividade['id'])
                    pedidos_df.loc[pedido_id, 'Carga'] = carga_numero
                    pedidos_df.loc[pedido_id, 'Placa'] = veiculo_id
                carga_numero += 1
        else:
            st.error(f"Falha ao obter as rotas otimizadas para a região {regiao}.")

    return pedidos_df

def agrupar_por_regiao(pedidos_df, n_clusters):
    """
    Agrupa os pedidos em regiões usando K-Means com base em Latitude, Longitude,
    Cidade de Entrega e, se aplicável, Bairro de Entrega.
    """
    pedidos_df = pedidos_df.dropna(subset=['Latitude', 'Longitude', 'Cidade de Entrega'])
    pedidos_df['Regiao'] = -1  # Inicializa com -1 para pedidos não agrupados

    for cidade in pedidos_df['Cidade de Entrega'].unique():
        if cidade == "São Paulo":
            # Agrupar também por Bairro de Entrega
            for bairro in pedidos_df[pedidos_df['Cidade de Entrega'] == cidade]['Bairro de Entrega'].unique():
                bairro_df = pedidos_df[(pedidos_df['Cidade de Entrega'] == cidade) & 
                                        (pedidos_df['Bairro de Entrega'] == bairro)]
                coords = bairro_df[['Latitude', 'Longitude']].values
                clusters = min(n_clusters, len(coords)) if len(coords) > 1 else 1

                if clusters == 1:
                    pedidos_df.loc[bairro_df.index, 'Regiao'] = 0
                else:
                    kmeans = KMeans(n_clusters=clusters, random_state=42)
                    pedidos_df.loc[bairro_df.index, 'Regiao'] = kmeans.fit_predict(coords)
        else:
            # Agrupar apenas por Cidade de Entrega
            cidade_df = pedidos_df[pedidos_df['Cidade de Entrega'] == cidade]
            coords = cidade_df[['Latitude', 'Longitude']].values
            clusters = min(n_clusters, len(coords)) if len(coords) > 1 else 1

            if clusters == 1:
                pedidos_df.loc[cidade_df.index, 'Regiao'] = 0
            else:
                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                pedidos_df.loc[cidade_df.index, 'Regiao'] = kmeans.fit_predict(coords)

    return pedidos_df

def criar_mapa(pedidos_df):
    """
    Cria e retorna um mapa Folium com marcadores para cada pedido e para o endereço de partida.
    """
    mapa = folium.Map(location=endereco_partida_coords, zoom_start=12)
    for _, row in pedidos_df.iterrows():
        popup_text = f"<b>Placa: {row['Placa']}</b><br>Endereço: {row['Endereço Completo']}"
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=popup_text,
            icon=folium.Icon(color='blue')
        ).add_to(mapa)
    folium.Marker(
        location=endereco_partida_coords,
        popup="Endereço de Partida",
        icon=folium.Icon(color='red')
    ).add_to(mapa)
    return mapa

def analisar_roterizacao_manual():
    """
    Analisa o arquivo roterizacao_dados.xlsx na pasta database para entender o padrão de montagem de cargas.
    Retorna a última sequência de número de carga e o DataFrame analisado.
    """
    filepath = "./database/roterizacao_dados.xlsx"  # Caminho do arquivo
    try:
        df = pd.read_excel(filepath)
        ultima_carga = df['Carga'].max()  # Obtém o maior número de carga
        st.write(f"Última sequência de carga encontrada: {ultima_carga}")
        return ultima_carga, df
    except FileNotFoundError:
        st.error(f"Arquivo {filepath} não encontrado. Certifique-se de que ele está na pasta correta.")
        return None, None
    except Exception as e:
        st.error(f"Erro ao analisar o arquivo: {e}")
        return None, None