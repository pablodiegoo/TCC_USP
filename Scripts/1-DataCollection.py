# ==============================================================================
# SCRIPT: 1-DataCollection.py
# DESCRIÇÃO: Lê um CSV com tickers, baixa os dados históricos de 10 anos
#            para cada um e salva em arquivos CSV individuais.
# AUTOR: Gemini
# DATA: 2024-05-21
# ==============================================================================

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os

def coletar_dados_historicos():
    """
    Função principal que orquestra a leitura dos tickers e o download
    dos dados históricos.
    """
    # --- 1. CONFIGURAÇÃO INICIAL ---
    ARQUIVO_TICKERS = 'Tickers.csv'
    PASTA_SAIDA = 'dados_historicos'
    
    # Período de 10 anos até a data atual
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * 10)

    # --- 2. VERIFICAÇÃO E LEITURA DO ARQUIVO DE TICKERS ---
    if not os.path.exists(ARQUIVO_TICKERS):
        print(f"ERRO: Arquivo '{ARQUIVO_TICKERS}' não encontrado.")
        print("Por favor, execute o script '0-Tickers.py' primeiro.")
        return

    print(f"Lendo tickers do arquivo '{ARQUIVO_TICKERS}'...")
    df_tickers = pd.read_csv(ARQUIVO_TICKERS)
    tickers = df_tickers['Ticker'].tolist()
    print(f"{len(tickers)} tickers carregados.")

    # --- 3. CRIAÇÃO DA PASTA DE SAÍDA ---
    if not os.path.exists(PASTA_SAIDA):
        print(f"Criando pasta de saída: '{PASTA_SAIDA}'")
        os.makedirs(PASTA_SAIDA)

    # --- 4. LOOP DE DOWNLOAD DOS DADOS ---
    print("\nIniciando o download dos dados históricos (10 anos)...")
    tickers_sucesso = []
    tickers_falha = []

    for ticker in tickers:
        try:
            # Caminho completo para o arquivo de saída do ticker atual
            caminho_arquivo = os.path.join(PASTA_SAIDA, f'{ticker}.csv')
            
            # Otimização: Se o arquivo já existe, pula o download
            if os.path.exists(caminho_arquivo):
                print(f"Arquivo para {ticker} já existe. Pulando...")
                tickers_sucesso.append(ticker)
                continue

            # yfinance requer o sufixo '.SA' para ações da B3
            ticker_sa = f"{ticker.upper()}.SA"
            print(f"Baixando dados para {ticker_sa}...")
            
            # Baixa os dados usando a biblioteca yfinance
            dados = yf.download(
                ticker_sa,
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                progress=False,  # Mantém o log mais limpo
                auto_adjust=False
            )

            if dados.empty:
                print(f"AVISO: Nenhum dado retornado para {ticker_sa}. O ativo pode ser novo ou o ticker inválido.")
                tickers_falha.append(ticker)
                continue
            
             # Reset index para manter a data como coluna
            dados = dados.reset_index()
            dados.columns = dados.columns.get_level_values(0)  # Remove o segundo nível do índice
            
            
            # Salva os dados em um arquivo CSV sem o index
            dados[['Open', 'High', 'Low', 'Close', 'Adj Close']] = dados[['Open', 'High', 'Low', 'Close', 'Adj Close']].round(2)
            dados.to_csv(caminho_arquivo, index=False)
            tickers_sucesso.append(ticker)
            print(f"-> Dados para {ticker} salvos em '{caminho_arquivo}'")

        except Exception as e:
            print(f"ERRO ao baixar dados para {ticker}: {e}")
            tickers_falha.append(ticker)
    
    # --- 5. RELATÓRIO FINAL ---
    print("\n==============================================")
    print("      RELATÓRIO DA COLETA DE DADOS      ")
    print("==============================================")
    print(f"Processo finalizado.")
    print(f"Total de tickers processados: {len(tickers)}")
    print(f"Downloads com sucesso: {len(tickers_sucesso)}")
    print(f"Falhas: {len(tickers_falha)}")
    if tickers_falha:
        print(f"\nTickers com falha: {', '.join(tickers_falha)}")
    print("==============================================")


# Bloco de execução principal
if __name__ == "__main__":
    print("==============================================")
    print(" MÓDULO 02 - COLETA DOS DADOS HISTÓRICOS  ")
    print("==============================================")
    
    coletar_dados_historicos()