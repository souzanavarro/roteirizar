import streamlit as st
import pandas as pd
from streamlit_folium import folium_static
import requests
import time

from gerenciamento_frota import cadastrar_caminhoes
from subir_pedidos import processar_pedidos, salvar_coordenadas
import ia_analise_pedidos as ia

# Exemplo de função para definir a ordem de entrega por carga
def definir_ordem_por_carga(pedidos_df, ordem_tsp):
    """
    Define a coluna 'Ordem de Entrega TSP' com base na ordem definida pelo TSP,
    agrupando os pedidos por 'Carga' e atribuindo uma sequência para cada entrega.
    
    Parâmetros:
      pedidos_df (DataFrame): DataFrame que contém a coluna 'Carga' e 'Endereço Completo'.
      ordem_tsp (list): Lista com os endereços na ordem definida pelo algoritmo TSP.
      
    Retorna:
      DataFrame: Com a coluna 'Ordem de Entrega TSP' atualizada.
    """
    # Cria um dicionário para mapeamento do endereço para sua posição na melhor rota
    rota_indices = {endereco: idx for idx, endereco in enumerate(ordem_tsp)}
    
    # Inicializa a coluna de ordem vazia
    pedidos_df['Ordem de Entrega TSP'] = ""
    
    # Para cada carga, ordena os pedidos conforme a posição na melhor rota e atribui uma sequência
    for carga in pedidos_df['Carga'].unique():
        mask = pedidos_df['Carga'] == carga
        df_carga = pedidos_df.loc[mask].copy()
        # Ordena os pedidos desta carga com base na posição encontrada na melhor rota.
        df_carga = df_carga.sort_values(
            by='Endereço Completo', 
            key=lambda col: col.map(lambda x: rota_indices.get(x, float('inf')))
        )
        # Atribui sequência numérica para cada pedido do grupo
        for seq, idx in enumerate(df_carga.index, start=1):
            pedidos_df.at[idx, 'Ordem de Entrega TSP'] = f"{carga}-{seq}"
    
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

def main():
    st.title("Roteirizador de Pedidos")
    
    st.markdown(
        """
        <style>
        div[data-baseweb="radio"] ul {
            list-style: none;
            padding-left: 0;
        }
        div[data-baseweb="radio"] li {
            margin-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Menu lateral
    menu_opcao = st.sidebar.radio("Menu", options=[
        "Dashboard", 
        "Cadastro da Frota", 
        "IA Analise",
        "API REST"
    ])
    
    if menu_opcao == "Dashboard":
        st.header("Dashboard - Envio de Pedidos")
        st.write("Bem-vindo! Envie a planilha de pedidos para iniciar:")
        pedidos_result = processar_pedidos()
        if pedidos_result is None:
            st.info("Aguardando envio da planilha de pedidos.")
        else:
            pedidos_df, coordenadas_salvas = pedidos_result
            
            with st.spinner("Obtendo coordenadas..."):
                pedidos_df['Latitude'] = pedidos_df['Endereço Completo'].apply(
                    lambda x: ia.obter_coordenadas_com_fallback(x, coordenadas_salvas)[0]
                )
                pedidos_df['Longitude'] = pedidos_df['Endereço Completo'].apply(
                    lambda x: ia.obter_coordenadas_com_fallback(x, coordenadas_salvas)[1]
                )
            pedidos_df['Latitude'] = pedidos_df['Latitude'].fillna(0)
            pedidos_df['Longitude'] = pedidos_df['Longitude'].fillna(0)
            salvar_coordenadas(coordenadas_salvas)
            
            pedidos_df['Latitude'] = pedidos_df['Latitude'].apply(
                lambda x: x if -90 <= x <= 90 else None
            )
            pedidos_df['Longitude'] = pedidos_df['Longitude'].apply(
                lambda x: x if -180 <= x <= 180 else None
            )
            
            st.dataframe(pedidos_df)
            st.write("Cabeçalho da planilha:", list(pedidos_df.columns))
            
            st.markdown("### Configurações para Roteirização")
            n_clusters = st.slider("Número de regiões para agrupar", min_value=1, max_value=10, value=3)
            percentual_frota = st.slider("Capacidade da frota a ser usada (%)", min_value=0, max_value=100, value=100)
            max_pedidos = st.slider("Número máximo de pedidos por veículo", min_value=1, max_value=30, value=12)
            aplicar_tsp = st.checkbox("Aplicar TSP")
            
            # Bloco para explicar o TSP
            st.markdown("""
            **Aplicar TSP:**  
            Utiliza um algoritmo genético para encontrar a rota que minimiza a distância total entre todos os pontos de entrega.
            """)

            aplicar_vrp = st.checkbox("Aplicar VRP")

            # Bloco para explicar o VRP
            st.markdown("""
            **Aplicar VRP:**  
            Distribui os pedidos entre os veículos disponíveis, respeitando as restrições de capacidade e minimizando a distância percorrida.
            """)
            
            if st.button("Roteirizar"):
                st.write("Roteirização em execução...")
                progress_bar = st.empty()
                for progresso in range(100):
                    time.sleep(0.05)
                    progress_bar.progress(progresso + 1)
                
                pedidos_df = pedidos_df[pedidos_df['Peso dos Itens'] > 0]
                
                try:
                    caminhoes_df = pd.read_excel("database/caminhoes_frota.xlsx", engine="openpyxl")
                except FileNotFoundError:
                    st.error("Nenhum caminhão cadastrado. Cadastre a frota na opção 'Cadastro da Frota'.")
                    return
                
                pedidos_df = ia.agrupar_por_regiao(pedidos_df, n_clusters)
                pedidos_df = ia.otimizar_aproveitamento_frota(pedidos_df, caminhoes_df, percentual_frota, max_pedidos, n_clusters)
                
                if aplicar_tsp:
                    G = ia.criar_grafo_tsp(pedidos_df)
                    melhor_rota, menor_distancia = ia.resolver_tsp_genetico(G)
                    st.write("Melhor rota TSP:")
                    st.write("\n".join(melhor_rota))
                    st.write(f"Menor distância TSP: {menor_distancia}")
                    
                    # Define a ordem de entrega baseada no campo 'Carga'
                    pedidos_df = definir_ordem_por_carga(pedidos_df, melhor_rota)
                
                if aplicar_vrp:
                    rota_vrp = ia.resolver_vrp(pedidos_df, caminhoes_df)

                    if rota_vrp:
                        for veiculo, rota in rota_vrp.items():
                            st.write(f"{veiculo}: {rota}")
                    else:
                        st.error("Falha ao resolver o problema de roteirização de veículos.")
                
                st.write("Dados dos Pedidos:")
                st.dataframe(pedidos_df)
                mapa = ia.criar_mapa(pedidos_df)
                folium_static(mapa)
                                        
                output_file_path = "database/roterizacao_resultado.xlsx"
                pedidos_df.to_excel(output_file_path, index=False)
                st.write(f"Arquivo salvo: {output_file_path}")
                with open(output_file_path, "rb") as file:
                    st.download_button(
                        "Baixar planilha",
                        data=file,
                        file_name="roterizacao_resultado.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                st.success("Roteirização concluída com sucesso!")
                st.balloons()
                st.write("Acesse o mapa interativo acima para visualizar as rotas.")
                st.write("Acesse a planilha de resultados para mais detalhes.")
    
    elif menu_opcao == "Cadastro da Frota":
        st.header("Cadastro da Frota")
        from gerenciamento_frota import cadastrar_caminhoes
        if st.checkbox("Cadastrar Caminhões"):
            cadastrar_caminhoes()
    
    elif menu_opcao == "IA Analise":
        st.header("IA Analise")
        st.write("Envie a planilha de pedidos para análise e edite os dados, se necessário:")
        pedidos_result = processar_pedidos()
        if pedidos_result is None:
            st.info("Aguardando envio da planilha de pedidos.")
        else:
            pedidos_df, coordenadas_salvas = pedidos_result
            with st.spinner("Obtendo coordenadas..."):
                pedidos_df['Latitude'] = pedidos_df['Endereço Completo'].apply(
                    lambda x: ia.obter_coordenadas_com_fallback(x, coordenadas_salvas)[0]
                )
                pedidos_df['Longitude'] = pedidos_df['Endereço Completo'].apply(
                    lambda x: ia.obter_coordenadas_com_fallback(x, coordenadas_salvas)[1]
                )
            pedidos_df['Latitude'] = pedidos_df['Latitude'].fillna(0)
            pedidos_df['Longitude'] = pedidos_df['Longitude'].fillna(0)       
            salvar_coordenadas(coordenadas_salvas)
            
            st.dataframe(pedidos_df)
            if st.button("Salvar alterações na planilha"):
                pedidos_df.to_excel("database/Pedidos.xlsx", index=False)
                st.success("Planilha editada e salva com sucesso!")
            with open("database/Pedidos.xlsx", "rb") as file:
                st.download_button(
                    "Baixar planilha de Pedidos",
                    data=file,
                    file_name="Pedidos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    elif menu_opcao == "API REST":
        st.header("Interação com API REST")
        st.write("Teste os endpoints:")
        st.markdown("""
        - **POST /upload**: Faz upload dos arquivos (Pedidos.xlsx, Caminhoes.xlsx, IA.xlsx).
        - **GET /resultado**: Retorna a solução do algoritmo genético.
        - **GET /mapa**: Exibe o mapa interativo.
        """)
        if st.button("Testar /resultado"):
            try:
                resposta = requests.get("http://localhost:5000/resultado")
                st.json(resposta.json())
            except Exception as e:
                st.error(f"Erro na requisição: {e}")

if __name__ == "__main__":
    main()