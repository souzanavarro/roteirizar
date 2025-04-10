import requests
import streamlit as st
import random
import networkx as nx
from itertools import permutations
from geopy.distance import geodesic
from sklearn.cluster import KMeans
import folium
from config import endereco_partida, endereco_partida_coords
import math
import pandas as pd
import logging

# Configurações de partida
endereco_partida_coords = (-23.0838, -47.1336)  # Coordenadas do ponto de partida

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

def obter_rota_osrm(coordenadas):
    """
    Obtém uma rota otimizada usando a API pública do OSRM.
    
    Args:
        coordenadas (list): Lista de tuplas (latitude, longitude) representando os pontos.
    
    Returns:
        list: Sequência de coordenadas otimizadas ou None em caso de erro.
    """
    base_url = "https://router.project-osrm.org/route/v1/driving/"
    coords = ";".join([f"{lng},{lat}" for lat, lng in coordenadas])  # Formato esperado: longitude,latitude
    params = {
        "overview": "full",  # Retorna a rota completa
        "geometries": "geojson",  # Formato das coordenadas
        "steps": "false"  # Não incluir etapas detalhadas
    }
    response = requests.get(f"{base_url}{coords}", params=params)
    if response.status_code == 200:
        data = response.json()
        if "routes" in data and len(data["routes"]) > 0:
            rota = data["routes"][0]["geometry"]["coordinates"]
            return rota
        else:
            st.error("Não foi possível calcular a rota.")
    else:
        st.error(f"Erro na requisição: {response.status_code}")
    return None

def obter_rota_valhalla(coordenadas):
    """
    Obtém uma rota otimizada usando a API pública do Valhalla.
    
    Args:
        coordenadas (list): Lista de tuplas (latitude, longitude) representando os pontos.
    
    Returns:
        list: Sequência de coordenadas otimizadas ou None em caso de erro.
    """
    base_url = "https://valhalla1.openstreetmap.de/route"
    locations = [{"lat": lat, "lon": lng} for lat, lng in coordenadas]
    payload = {
        "locations": locations,
        "costing": "auto",  # Tipo de veículo (carro)
        "directions_options": {"units": "kilometers"}
    }
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(base_url, json=payload, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if "trip" in data and "legs" in data["trip"]:
            rota = []
            for leg in data["trip"]["legs"]:
                for step in leg["shape"]:
                    rota.append(step)
            return rota
        else:
            st.error("Não foi possível calcular a rota com Valhalla.")
    else:
        st.error(f"Erro na requisição: {response.status_code}")
    return None

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
                kmeans = KMeans(n_clusters=clusters, random_state=42)
                pedidos_df.loc[cidade_df.index, 'Regiao'] = kmeans.fit_predict(coords)

    return pedidos_df

def otimizar_aproveitamento_frota(pedidos_df, caminhoes_df, percentual_frota, max_pedidos, n_clusters):
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
        coordenadas = [(endereco_partida_coords[0], endereco_partida_coords[1])] + \
                      list(zip(pedidos_regiao['Latitude'], pedidos_regiao['Longitude']))
        
        # Obter rota otimizada com OSRM
        rota_otimizada = obter_rota_osrm(coordenadas)

        if rota_otimizada:
            st.write(f"Rota otimizada para a região {regiao}: {rota_otimizada}")
            
            # Atribuir os pedidos à rota com base na placa do veículo
            for i, pedido_index in enumerate(pedidos_regiao.index):
                if i < len(caminhoes_df):  # Garantir que há caminhões disponíveis
                    placa = caminhoes_df.iloc[i]['Placa']
                    pedidos_df.loc[pedido_index, 'Carga'] = carga_numero
                    pedidos_df.loc[pedido_index, 'Placa'] = placa
                else:
                    st.error("Não há caminhões suficientes para atender todos os pedidos.")
                    break
            carga_numero += 1
        else:
            st.error(f"Falha ao obter a rota otimizada para a região {regiao}.")

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

def resolver_vrp(pedidos_df, caminhoes_df):
    """
    Resolve o problema de roteirização de veículos (VRP) usando OSRM.
    
    Args:
        pedidos_df (DataFrame): DataFrame contendo os pedidos com Latitude e Longitude.
        caminhoes_df (DataFrame): DataFrame contendo os veículos com capacidade.
    
    Returns:
        dict: Rotas otimizadas para cada veículo ou mensagem de erro.
    """
    try:
        # Verificar se há pedidos e veículos disponíveis
        if pedidos_df.empty or caminhoes_df.empty:
            st.error("Nenhum pedido ou veículo disponível para roteirização.")
            return None

        # Tratar valores NaN em 'Peso dos Itens' e 'Capac. Kg'
        pedidos_df['Peso dos Itens'] = pedidos_df['Peso dos Itens'].fillna(0)  # Substituir NaN por 0
        caminhoes_df['Capac. Kg'] = caminhoes_df['Capac. Kg'].fillna(0)  # Substituir NaN por 0

        # Obter as coordenadas dos pedidos
        coordenadas_pedidos = list(zip(pedidos_df['Latitude'], pedidos_df['Longitude']))
        coordenadas_depot = [endereco_partida_coords]  # Coordenadas do ponto de partida

        # Criar a matriz de distância usando OSRM
        base_url = "https://router.project-osrm.org/table/v1/driving/"
        coords = ";".join([f"{lng},{lat}" for lat, lng in coordenadas_depot + coordenadas_pedidos])
        response = requests.get(f"{base_url}{coords}?annotations=distance")
        if response.status_code != 200:
            st.error(f"Erro ao obter a matriz de distância: {response.status_code}")
            return None

        data = response.json()
        distance_matrix = data['distances']

        # Configurar o problema de VRP
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2

        num_pedidos = int(len(coordenadas_pedidos))  # Garantir que seja um inteiro
        num_veiculos = int(len(caminhoes_df))  # Garantir que seja um inteiro
        depot_index = 0

        # Criar o gerenciador de índices
        manager = pywrapcp.RoutingIndexManager(len(distance_matrix), num_veiculos, depot_index)

        # Criar o modelo de roteirização
        routing = pywrapcp.RoutingModel(manager)

        # Função de custo (distância)
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Adicionar restrições de capacidade
        demands = [0] + list(map(int, pedidos_df['Peso dos Itens']))  # Converter para inteiros
        capacities = list(map(int, caminhoes_df['Capac. Kg']))  # Converter para inteiros

        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return demands[from_node]

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # Sem capacidade extra
            capacities,  # Capacidades dos veículos
            True,  # Início cumulativo
            "Capacity"
        )

        # Configurar parâmetros de busca
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

        # Resolver o problema
        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            st.error("Não foi possível encontrar uma solução para o VRP.")
            return None

        # Extrair as rotas
        rotas = {}
        for vehicle_id in range(num_veiculos):
            index = routing.Start(vehicle_id)
            rota = []
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                if node_index != depot_index:  # Ignorar o depósito
                    rota.append(pedidos_df.iloc[node_index - 1]['Endereço Completo'])
                index = solution.Value(routing.NextVar(index))
            rotas[f"Veículo {vehicle_id + 1}"] = rota

        return rotas

    except Exception as e:
        st.error(f"Erro ao resolver o VRP: {e}")
        return None