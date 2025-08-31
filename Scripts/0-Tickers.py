# ==============================================================================
# SCRIPT: 0-Tickers.py
# DESCRIÇÃO: Coleta os tickers das ações do índice Ibovespa a partir do site
#            Status Invest e os salva em um arquivo CSV.
# AUTOR: Gemini
# DATA: 2024-05-21
# ==============================================================================

import pandas as pd
import requests
from bs4 import BeautifulSoup

def obter_e_salvar_tickers_ibovespa(nome_arquivo="Tickers.csv"):
    """
    Realiza o web scraping da página do Ibovespa no Status Invest para obter
    a lista de tickers de ações e a salva em um arquivo CSV.

    Args:
        nome_arquivo (str): O nome do arquivo CSV de saída.

    Returns:
        bool: True se a operação foi bem-sucedida, False caso contrário.
    """
    print("Iniciando a busca pelos tickers do Ibovespa...")
    
    try:
        # 1. DEFINIÇÃO DO ALVO E CABEÇALHOS
        # O User-Agent simula o acesso de um navegador para evitar bloqueios.
        url = 'https://statusinvest.com.br/indices/ibovespa'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

        # 2. REQUISIÇÃO HTTP
        print(f"Acessando a URL: {url}")
        response = requests.get(url, headers=headers)
        # Lança uma exceção se a requisição falhou (ex: erro 404, 500)
        response.raise_for_status()
        print("Página acessada com sucesso.")

        # 3. PARSEAMENTO DO HTML
        # Utiliza o BeautifulSoup para analisar o conteúdo HTML da página.
        soup = BeautifulSoup(response.text, 'html.parser')

        # 4. EXTRAÇÃO DOS DADOS
        # Encontra todos os elementos <span> com a classe 'ticker'.
        # Esta é a parte mais sensível do script, pois depende da estrutura do site.
        ticker_tags = soup.find_all('span', class_='ticker')
        
        # Extrai o texto de cada tag encontrada.
        tickers = [tag.text for tag in ticker_tags]

        # 5. VALIDAÇÃO E PROCESSAMENTO
        if not tickers:
            print("\nERRO: Nenhum ticker foi encontrado.")
            print("Possível causa: O site Status Invest mudou sua estrutura HTML.")
            print("Verifique a classe 'ticker' no HTML da página ou tente uma abordagem diferente.")
            return False
        
        print(f"\n{len(tickers)} tickers foram encontrados com sucesso.")

        # 6. CRIAÇÃO DO DATAFRAME E SALVAMENTO EM CSV
        # Converte a lista de tickers em um DataFrame do Pandas.
        df_tickers = pd.DataFrame(tickers, columns=['Ticker'])
        
        # Salva o DataFrame em um arquivo CSV sem a coluna de índice do pandas.
        df_tickers.to_csv(nome_arquivo, index=False)
        
        print(f"Arquivo '{nome_arquivo}' foi criado com sucesso na pasta do script.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"\nERRO DE CONEXÃO: Não foi possível acessar a página.")
        print(f"Detalhes: {e}")
        return False
    except Exception as e:
        print(f"\nERRO INESPERADO: Ocorreu um problema durante a execução.")
        print(f"Detalhes: {e}")
        return False

# Bloco de execução principal
if __name__ == "__main__":
    print("==============================================")
    print(" MÓDULO 01 - OBTENÇÃO DOS TICKERS DO IBOVESPA ")
    print("==============================================")
    
    sucesso = obter_e_salvar_tickers_ibovespa()
    
    if sucesso:
        print("\nProcesso finalizado com sucesso.")
    else:
        print("\nO processo falhou. Verifique as mensagens de erro acima.")