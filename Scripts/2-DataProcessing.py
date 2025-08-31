# ==============================================================================
# SCRIPT: 2-DataProcessing.py
# DESCRIÇÃO: Lê os arquivos CSV individuais da pasta 'dados_historicos',
#            processa, ajusta, consolida e limpa os dados, salvando o
#            resultado em um único arquivo CSV final.
# AUTOR: Gemini
# DATA: 2024-05-21
# ==============================================================================

import pandas as pd
import os
import glob

def processar_e_consolidar_dados():
    """
    Função principal que orquestra todo o processo de tratamento e
    consolidação dos dados históricos.
    """
    # --- 1. CONFIGURAÇÃO INICIAL ---
    PASTA_DADOS = 'dados_historicos'
    ARQUIVO_SAIDA = 'dados_bovespa_ultimos_10_anos.csv'
    
    # --- 2. VERIFICAÇÃO E LISTAGEM DOS ARQUIVOS DE DADOS ---
    # Usa glob para encontrar todos os arquivos .csv dentro da pasta
    caminho_pesquisa = os.path.join(PASTA_DADOS, '*.csv')
    lista_arquivos = glob.glob(caminho_pesquisa)

    if not lista_arquivos:
        print(f"ERRO: Nenhum arquivo de dados (.csv) encontrado na pasta '{PASTA_DADOS}'.")
        print("Por favor, execute os scripts '0-Tickers.py' e '1-DataCollection.py' primeiro.")
        return

    print(f"Encontrados {len(lista_arquivos)} arquivos de dados para processar.")
    
    # --- 3. PROCESSAMENTO INDIVIDUAL E ARMAZENAMENTO ---
    lista_dfs_processados = []

    for caminho_arquivo in lista_arquivos:
        try:
            # Extrai o nome do ticker a partir do nome do arquivo
            # Ex: 'dados_historicos/PETR4.csv' -> 'PETR4'
            nome_arquivo = os.path.basename(caminho_arquivo)
            ticker = os.path.splitext(nome_arquivo)[0]
            print(f"Processando dados de {ticker}...")

            # Lê o arquivo CSV, definindo a coluna 'Date' como índice e convertendo para datetime
            df = pd.read_csv(caminho_arquivo, index_col='Date', parse_dates=True)

            # --- AJUSTE DE PREÇOS ---
            # O 'Adj Close' já está ajustado. Usamo-lo para criar um fator de ajuste
            # e aplicar esse fator às outras colunas de preço (Open, High, Low).
            # O 'Close' será substituído pelo 'Adj Close' para manter a consistência.
            fator_ajuste = df['Adj Close'] / df['Close']
            
            df_ajustado = pd.DataFrame(index=df.index) # Cria um novo DF para evitar warnings
            df_ajustado['Open'] = df['Open'] * fator_ajuste
            df_ajustado['High'] = df['High'] * fator_ajuste
            df_ajustado['Low'] = df['Low'] * fator_ajuste
            df_ajustado['Close'] = df['Adj Close']
            df_ajustado['Volume'] = df['Volume']
            
            # Renomeia as colunas para o formato 'TICKER_ATRIBUTO'
            df_ajustado.columns = [f'{ticker}_{col}' for col in df_ajustado.columns]

            lista_dfs_processados.append(df_ajustado)

        except Exception as e:
            print(f"ERRO ao processar o arquivo {caminho_arquivo}: {e}")

    # --- 4. CONSOLIDAÇÃO DOS DATAFRAMES ---
    if not lista_dfs_processados:
        print("Nenhum dado foi processado com sucesso. O arquivo final não será gerado.")
        return
        
    print("\nConsolidando todos os dados em um único DataFrame...")
    # Concatena todos os DataFrames da lista. axis=1 junta pelas colunas, alinhando pelo índice (Date).
    df_final = pd.concat(lista_dfs_processados, axis=1)

    # Garante que o índice esteja em ordem cronológica
    df_final.sort_index(inplace=True)

    # ...existing code...
    
    # --- 5. LIMPEZA FINAL (DADOS FALTANTES) ---
    print("Verificando dados faltantes (NaN)...")
    
    # Opcional: Mostrar quantidade de dados faltantes por coluna
    nan_count = df_final.isna().sum()
    print("\nQuantidade de dados faltantes por coluna:")
    print(nan_count[nan_count > 0])
    
    # Opcional: Remover linhas onde todos os dados estão ausentes
    df_final = df_final.dropna(how='all')
    
    # --- 6. SALVANDO O RESULTADO FINAL ---
    try:
        print(f"\nSalvando o DataFrame final em '{ARQUIVO_SAIDA}'...")
        price_columns = [col for col in df_final.columns if not col.endswith('_Volume')]
        df_final[price_columns] = df_final[price_columns].round(2)            
        df_final.to_csv(ARQUIVO_SAIDA)
        print("Arquivo salvo com sucesso!")
        print(f"Dimensões do DataFrame final: {df_final.shape[0]} linhas (datas) e {df_final.shape[1]} colunas (atributos).")
    except Exception as e:
        print(f"ERRO ao salvar o arquivo final: {e}")



# Bloco de execução principal
if __name__ == "__main__":
    print("=====================================================")
    print(" MÓDULO 03 - PROCESSAMENTO E CONSOLIDAÇÃO DE DADOS ")
    print("=====================================================")
    
    processar_e_consolidar_dados()
    
    print("\nProcesso finalizado.")