import sqlite3
import logging
from typing import List, Tuple, Optional

# Configuração de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def conectar_banco() -> sqlite3.Connection:
    """
    Conecta ao banco de dados SQLite.
    """
    try:
        conn = sqlite3.connect('banco_de_dados.db')
        logging.info("Conexão ao banco de dados estabelecida.")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

def criar_tabelas() -> None:
    """
    Cria as tabelas necessárias no banco de dados.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endereco TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                peso_itens REAL,
                ordem_entrega INTEGER
            )
            ''')
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS frota (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modelo TEXT NOT NULL,
                capacidade REAL NOT NULL
            )
            ''')
            conn.commit()
            logging.info("Tabelas criadas ou já existentes.")
    except sqlite3.Error as e:
        logging.error(f"Erro ao criar tabelas: {e}")
        raise

def inserir_pedido(endereco: str, latitude: float, longitude: float, peso_itens: float, ordem_entrega: int) -> None:
    """
    Insere um novo pedido na tabela `pedidos`.

    Args:
        endereco (str): Endereço do pedido.
        latitude (float): Latitude do endereço.
        longitude (float): Longitude do endereço.
        peso_itens (float): Peso dos itens do pedido.
        ordem_entrega (int): Ordem de entrega do pedido.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO pedidos (endereco, latitude, longitude, peso_itens, ordem_entrega)
            VALUES (?, ?, ?, ?, ?)
            ''', (endereco, latitude, longitude, peso_itens, ordem_entrega))
            conn.commit()
            logging.info(f"Pedido inserido com sucesso: {endereco}")
    except sqlite3.Error as e:
        logging.error(f"Erro ao inserir pedido: {e}")
        raise

def inserir_caminhao(modelo: str, capacidade: float) -> None:
    """
    Insere um novo caminhão na tabela `frota`.

    Args:
        modelo (str): Modelo do caminhão.
        capacidade (float): Capacidade do caminhão.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO frota (modelo, capacidade)
            VALUES (?, ?)
            ''', (modelo, capacidade))
            conn.commit()
            logging.info(f"Caminhão inserido com sucesso: {modelo}")
    except sqlite3.Error as e:
        logging.error(f"Erro ao inserir caminhão: {e}")
        raise

def consultar_pedidos() -> List[Tuple]:
    """
    Consulta todos os pedidos na tabela `pedidos`.

    Returns:
        List[Tuple]: Lista de tuplas contendo os registros dos pedidos.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM pedidos')
            resultados = cursor.fetchall()
            logging.info(f"{len(resultados)} pedidos encontrados.")
            return resultados
    except sqlite3.Error as e:
        logging.error(f"Erro ao consultar pedidos: {e}")
        raise

def consultar_frota() -> List[Tuple]:
    """
    Consulta todos os caminhões na tabela `frota`.

    Returns:
        List[Tuple]: Lista de tuplas contendo os registros dos caminhões.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM frota')
            resultados = cursor.fetchall()
            logging.info(f"{len(resultados)} caminhões encontrados.")
            return resultados
    except sqlite3.Error as e:
        logging.error(f"Erro ao consultar frota: {e}")
        raise

def atualizar_pedido(pedido_id: int, novos_dados: Dict[str, Optional]) -> None:
    """
    Atualiza os dados de um pedido na tabela `pedidos`.

    Args:
        pedido_id (int): ID do pedido a ser atualizado.
        novos_dados (Dict[str, Optional]): Dicionário com os campos a serem atualizados.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            set_clause = ", ".join([f"{campo} = ?" for campo in novos_dados.keys()])
            valores = list(novos_dados.values())
            valores.append(pedido_id)

            cursor.execute(f'''
            UPDATE pedidos
            SET {set_clause}
            WHERE id = ?
            ''', valores)
            conn.commit()
            logging.info(f"Pedido {pedido_id} atualizado com sucesso.")
    except sqlite3.Error as e:
        logging.error(f"Erro ao atualizar pedido {pedido_id}: {e}")
        raise

def deletar_pedido(pedido_id: int) -> None:
    """
    Remove um pedido da tabela `pedidos`.

    Args:
        pedido_id (int): ID do pedido a ser removido.
    """
    try:
        with conectar_banco() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM pedidos WHERE id = ?', (pedido_id,))
            conn.commit()
            logging.info(f"Pedido {pedido_id} removido com sucesso.")
    except sqlite3.Error as e:
        logging.error(f"Erro ao deletar pedido {pedido_id}: {e}")
        raise

# Inicializa as tabelas ao carregar o módulo
if __name__ == "__main__":
    criar_tabelas()
