import streamlit as st
import pandas as pd
from streamlit_folium import folium_static
import requests
import time
from gerenciamento_frota import cadastrar_caminhoes
from subir_pedidos import processar_pedidos, salvar_coordenadas
import ia_analise_pedidos as ia
from typing import Optional


def carregar_dados_pedidos() -> Optional[pd.DataFrame]:
    """
    Carrega e processa a planilha de pedidos.
    """
    pedidos_result = processar_pedidos()
    if pedidos_result is None:
        st.info("Aguardando envio da planilha de pedidos.")
        return None

    pedidos_df, coordenadas_salvas = pedidos_result

    # Verifica se a coluna 'Endereço Completo' existe
    if 'Endereço Completo' not in pedidos_df.columns:
        st.error("A coluna 'Endereço Completo' está ausente na planilha enviada. Verifique os dados.")
        return None

    with st.spinner("Obtendo coordenadas..."):
        try:
            pedidos_df['Latitude'] = pedidos_df['Endereço Completo'].apply(
                lambda x: ia.obter_coordenadas_com_fallback(x, coordenadas_salvas)[0] if pd.notnull(x) else None
            )
            pedidos_df['Longitude'] = pedidos_df['Endereço Completo'].apply(
                lambda x: ia.obter_coordenadas_com_fallback(x, coordenadas_salvas)[1] if pd.notnull(x) else None
            )
        except Exception as e:
            st.error(f"Erro ao obter coordenadas: {e}")
            return None

    salvar_coordenadas(coordenadas_salvas)

    # Verifica se alguma coordenada não foi encontrada
    if pedidos_df['Latitude'].isnull().any() or pedidos_df['Longitude'].isnull().any():
        st.error("Alguns endereços não obtiveram coordenadas. Verifique os dados.")
        return None

    return pedidos_df


def configurar_roterizacao(pedidos_df: pd.DataFrame, caminhoes_df: pd.DataFrame):
    """
    Configura as opções de roteirização usando sliders e checkboxes do Streamlit.
    """
    st.markdown("### Configurações para Roteirização")
    n_clusters = st.slider("Número de regiões para agrupar", min_value=1, max_value=10, value=3)
    percentual_frota = st.slider("Capacidade da frota a ser usada (%)", min_value=0, max_value=100, value=100)
    max_pedidos = st.slider("Número máximo de pedidos por veículo", min_value=1, max_value=30, value=12)
    aplicar_tsp = st.checkbox("Aplicar TSP")
    aplicar_vrp = st.checkbox("Aplicar VRP")

    if st.button("Executar Roteirização"):
        executar_roterizacao(pedidos_df, caminhoes_df, n_clusters, percentual_frota, max_pedidos, aplicar_tsp, aplicar_vrp)


def executar_roterizacao(pedidos_df: pd.DataFrame, caminhoes_df: pd.DataFrame, n_clusters: int,
                         percentual_frota: int, max_pedidos: int, aplicar_tsp: bool, aplicar_vrp: bool):
    """
    Executa a roteirização com base nas configurações fornecidas.
    """
    st.write("Roteirização em execução...")
    progress_bar = st.empty()
    for progresso in range(100):
        time.sleep(0.05)
        progress_bar.progress(progresso + 1)

    # Filtra pedidos válidos
    pedidos_df = pedidos_df[pedidos_df['Peso dos Itens'] > 0]

    # Agrupamento e otimização de frota
    pedidos_df = ia.agrupar_por_regiao(pedidos_df, n_clusters)
    pedidos_df = ia.otimizar_aproveitamento_frota(pedidos_df, caminhoes_df, percentual_frota, max_pedidos, n_clusters)

    # Aplicação do TSP
    if aplicar_tsp:
        G = ia.criar_grafo_tsp(pedidos_df)
        melhor_rota, menor_distancia = ia.resolver_tsp_genetico(G)
        st.write("Melhor rota TSP:")
        st.write("\n".join(melhor_rota))
        st.write(f"Menor distância TSP: {menor_distancia}")
        pedidos_df = ia.definir_ordem_por_carga(pedidos_df, melhor_rota)

    # Aplicação do VRP
    if aplicar_vrp:
        rota_vrp = ia.resolver_vrp(pedidos_df, caminhoes_df)
        if rota_vrp:
            for veiculo, rota in rota_vrp.items():
                st.write(f"{veiculo}: {rota}")
        else:
            st.error("Falha ao resolver o problema de roteirização de veículos.")

    # Exibição dos resultados
    st.write("Dados dos Pedidos:")
    st.dataframe(pedidos_df)
    mapa = ia.criar_mapa(pedidos_df)
    folium_static(mapa)

    # Salvar o resultado em Excel
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


def main():
    st.title("Roteirizador de Pedidos")

    # Menu lateral
    menu_opcao = st.sidebar.radio("Menu", options=[
        "Dashboard",
        "Cadastro da Frota",
        "IA Análise",
        "API REST"
    ])

    if menu_opcao == "Dashboard":
        st.header("Dashboard - Envio de Pedidos")
        st.write("Bem-vindo! Envie a planilha de pedidos para iniciar:")

        pedidos_df = carregar_dados_pedidos()
        if pedidos_df is not None:
            # Carrega a frota cadastrada
            try:
                caminhoes_df = pd.read_excel("database/caminhoes_frota.xlsx", engine="openpyxl")
            except FileNotFoundError:
                st.error("Nenhum caminhão cadastrado. Cadastre a frota na opção 'Cadastro da Frota'.")
                return

            configurar_roterizacao(pedidos_df, caminhoes_df)

    elif menu_opcao == "Cadastro da Frota":
        st.header("Cadastro da Frota")
        if st.checkbox("Cadastrar Caminhões"):
            cadastrar_caminhoes()

    elif menu_opcao == "IA Análise":
        st.header("IA Análise")
        st.write("Envie a planilha de pedidos para análise e edite os dados, se necessário:")
        pedidos_df = carregar_dados_pedidos()
        if pedidos_df is not None:
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
