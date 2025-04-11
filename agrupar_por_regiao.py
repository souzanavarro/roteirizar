def agrupar_por_regiao(pedidos_df, n_clusters=3):
    """
    Agrupa os pedidos em regiões utilizando K-Means com base em Latitude e Longitude.
    Adiciona a coluna 'Regiao' no DataFrame.
    """
    required_columns = ['Latitude', 'Longitude']
    
    # Verifica se as colunas necessárias estão presentes
    if not all(col in pedidos_df.columns for col in required_columns):
        raise ValueError(f"As colunas necessárias {required_columns} não foram encontradas no DataFrame.")
    
    # Remove linhas com valores nulos nas colunas necessárias
    pedidos_df = pedidos_df.dropna(subset=required_columns)
    
    if pedidos_df.empty:
        raise ValueError("O DataFrame está vazio após remover valores nulos.")
    
    coords = pedidos_df[required_columns].values

    try:
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        pedidos_df['Regiao'] = kmeans.fit_predict(coords)
    except Exception as e:
        raise RuntimeError(f"Erro ao executar o K-Means: {e}")
    
    return pedidos_df
