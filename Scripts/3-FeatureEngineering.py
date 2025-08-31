# File: 3-FeatureEngineering.py

import pandas as pd
import pandas_ta as ta
import numpy as np
import os

def calculate_technical_features(df):
    """
    Calculates technical features for each stock ticker in the DataFrame.
    
    Args:
        df (pd.DataFrame): The input DataFrame with stock data.
    
    Returns:
        pd.DataFrame: The DataFrame with new technical features added.
    """
    df_with_features = df.copy()
    
    # Dynamically identify all tickers based on column names
    # Assumes the column names follow the format 'TICKER_Attribute'
    tickers = set([col.split('_')[0] for col in df.columns if '_' in col])
    
    for ticker in tickers:
        print(f"Calculating features for ticker: {ticker}")
        
        # Check for required 'Close' and 'Volume' columns for the ticker
        close_col = f'{ticker}_Close'
        volume_col = f'{ticker}_Volume'
        
        if close_col not in df.columns:
            print(f"Skipping {ticker}: '{close_col}' not found.")
            continue
        
        # --- 1. Simple Moving Averages (MMS) ---
        # MMS de 20 períodos
        df_with_features[f'{ticker}_MMS20'] = ta.sma(df[close_col], length=20)
        
        # MMS de 50 períodos
        df_with_features[f'{ticker}_MMS50'] = ta.sma(df[close_col], length=50)

        # --- 2. Relative Strength Index (RSI) ---
        # RSI de 14 períodos
        df_with_features[f'{ticker}_RSI14'] = ta.rsi(df[close_col], length=14)

        # --- 3. Bollinger Bands ---
        # Bollinger Bands de 20 períodos
        # Returns a DataFrame with 'BBL_20_2.0', 'BBM_20_2.0', 'BBU_20_2.0'
        bbands = ta.bbands(df[close_col], length=20, append=False)
        df_with_features[f'{ticker}_BBL_20'] = bbands[f'BBL_20_2.0'] # Lower Band
        df_with_features[f'{ticker}_BBM_20'] = bbands[f'BBM_20_2.0'] # Middle Band
        df_with_features[f'{ticker}_BBU_20'] = bbands[f'BBU_20_2.0'] # Upper Band
        
        # --- 4. Volatility (Log-Return) ---
        # Daily volatility (20-period rolling standard deviation of log returns)
        log_returns = np.log(df[close_col] / df[close_col].shift(1))
        df_with_features[f'{ticker}_Vol20'] = log_returns.rolling(window=20).std()

    return df_with_features

def main():
    """
    Main function to orchestrate the process of reading data,
    calculating features, and saving the output.
    """
    input_file = 'dados_bovespa_ultimos_10_anos.csv'
    output_file = 'dados_com_features_tecnicas.csv'
    
    # Check if the input file exists
    if not os.path.exists(input_file):
        print(f"Error: The file '{input_file}' was not found.")
        return

    print(f"Reading data from '{input_file}'...")
    try:
        # Read the CSV file, assuming the first column is the Date index
        df = pd.read_csv(input_file, parse_dates=['Date'], index_col='Date')
        print("Data read successfully.")
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return

    print("Calculating technical features...")
    df_final = calculate_technical_features(df)
    
    # The first N rows will have NaN values, which is expected.
    # We will keep them. If you prefer to drop them, uncomment the next line.
    # df_final.dropna(inplace=True)

    print(f"Saving the final DataFrame to '{output_file}'...")
    # Save the DataFrame to a new CSV file without the index
    df_final.to_csv(output_file, index_label='Date')
    print("File saved successfully.")
    print(f"Final DataFrame shape: {df_final.shape}")

if __name__ == "__main__":
    main()