import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import DBSCAN
import backtrader as bt
import datetime
import itertools
import os
from collections import defaultdict

# Part 1: Data Loading and Preparation
def load_data(filepath):
    """Load data from CSV file with date index"""
    print(f"Loading data from: {filepath}")
    data = pd.read_csv(filepath, parse_dates=True, index_col=0)
    return data

def extract_tickers(df):
    """Extract unique ticker symbols from column names"""
    tickers = set()
    for col in df.columns:
        ticker = col.split('_')[0]
        tickers.add(ticker)
    return list(tickers)

def prepare_price_data(df, tickers):
    """Extract price data for all tickers"""
    price_data = {}
    
    for ticker in tickers:
        if f"{ticker}_Close" in df.columns:
            # Create DataFrame with OHLCV format required by backtrader
            ticker_df = pd.DataFrame(index=df.index)
            ticker_df['open'] = df[f"{ticker}_Open"] if f"{ticker}_Open" in df.columns else df[f"{ticker}_Close"]
            ticker_df['high'] = df[f"{ticker}_High"] if f"{ticker}_High" in df.columns else df[f"{ticker}_Close"]
            ticker_df['low'] = df[f"{ticker}_Low"] if f"{ticker}_Low" in df.columns else df[f"{ticker}_Close"]
            ticker_df['close'] = df[f"{ticker}_Close"]
            ticker_df['volume'] = df[f"{ticker}_Volume"] if f"{ticker}_Volume" in df.columns else 0
            price_data[ticker] = ticker_df
    
    return price_data

# Part 2: Feature Extraction for Clustering
def extract_features_for_clustering(df, tickers):
    """Extract technical features for clustering"""
    # Define which features to use for clustering
    tech_features = ['RSI14', 'SMA20', 'SMA50', 'Volatility', 'MACD', 'ADX']
    
    feature_matrix = {}
    
    for ticker in tickers:
        feature_vector = []
        
        # For each technical feature, get the mean value over the training period
        for feature in tech_features:
            feature_col = f"{ticker}_{feature}"
            if feature_col in df.columns:
                mean_value = df[feature_col].mean()
                if not np.isnan(mean_value):
                    feature_vector.append(mean_value)
                else:
                    feature_vector.append(0)  # Replace NaN with 0
            else:
                feature_vector.append(0)  # Feature not available
        
        if len(feature_vector) == len(tech_features):
            feature_matrix[ticker] = feature_vector
    
    # Create DataFrame with tickers as index and features as columns
    feature_df = pd.DataFrame.from_dict(feature_matrix, orient='index', columns=tech_features)
    
    return feature_df

# Part 3: Clustering using DBSCAN
def perform_clustering(feature_df, eps=0.5, min_samples=2):
    """Perform DBSCAN clustering on ticker features"""
    # Normalize features
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(feature_df)
    
    # Apply DBSCAN
    dbscan = DBSCAN(eps=eps, min_samples=min_samples)
    clusters = dbscan.fit_predict(scaled_features)
    
    # Organize tickers by cluster
    clustered_tickers = defaultdict(list)
    for i, cluster_id in enumerate(clusters):
        if cluster_id != -1:  # Ignore noise points (-1)
            ticker = feature_df.index[i]
            clustered_tickers[cluster_id].append(ticker)
    
    return clustered_tickers

# Part 4: Pair Formation
def form_pairs(clustered_tickers):
    """Form pairs from clusters"""
    pairs = []
    
    for cluster_id, tickers in clustered_tickers.items():
        if len(tickers) >= 2:  # Need at least 2 tickers to form a pair
            # Form all possible pairs within the cluster
            cluster_pairs = list(itertools.combinations(tickers, 2))
            pairs.extend(cluster_pairs)
    
    return pairs

# Part 5: Pairs Trading Strategy Definition
class PairsStrategy(bt.Strategy):
    params = (
        ('window', 60),          # lookback period for z-score calculation
        ('entry_threshold', 2.0), # entry when |z| > entry_threshold
        ('exit_threshold', 0.5),  # exit when |z| < exit_threshold
    )
    
    def __init__(self):
        # Create a proper Line for the spread using a custom indicator
        self.spread_line = bt.ind.OpsSubtraction(self.data1.close, self.data0.close)
        
        # Now calculate indicators on this proper line
        self.spread_mean = bt.ind.SMA(self.spread_line, period=self.p.window)
        self.spread_std = bt.ind.StdDev(self.spread_line, period=self.p.window)
        
        # To keep track of positions
        self.in_position = False
        self.long_spread = False  # True if long spread (long data1, short data0)
        
    def next(self):
        # Skip until we have enough data for z-score calculation
        if len(self.data0) <= self.p.window or self.spread_std[0] <= 0:
            return
        
        # Calculate z-score
        zscore = (self.spread_line[0] - self.spread_mean[0]) / self.spread_std[0]
        
        # If not in a position, check for entry signals
        if not self.in_position:
            if zscore > self.p.entry_threshold:
                # Short the spread (short data1, long data0)
                self.buy(data=self.data0)
                self.sell(data=self.data1)
                self.in_position = True
                self.long_spread = False
                self.log(f'SHORT SPREAD: {zscore:.2f}')
            elif zscore < -self.p.entry_threshold:
                # Long the spread (long data1, short data0)
                self.sell(data=self.data0)
                self.buy(data=self.data1)
                self.in_position = True
                self.long_spread = True
                self.log(f'LONG SPREAD: {zscore:.2f}')
        
        # If in a position, check for exit signals
        elif self.in_position:
            if abs(zscore) < self.p.exit_threshold:
                # Close positions
                self.close(data=self.data0)
                self.close(data=self.data1)
                self.in_position = False
                self.log(f'CLOSE POSITIONS: {zscore:.2f}')
    
    def log(self, txt, dt=None):
        """Logging function"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()}, {txt}')

# Part 6: Backtesting
def run_backtest(price_data, pair, start_date, end_date, initial_cash=100000.0, commission=0.001):
    """Run backtest for a pair"""
    ticker1, ticker2 = pair
    
    if ticker1 not in price_data or ticker2 not in price_data:
        print(f"Error: Missing price data for {ticker1} or {ticker2}")
        return None, pair
    
    # Create a Cerebro instance
    cerebro = bt.Cerebro()
    
    # Add the pairs strategy
    cerebro.addstrategy(PairsStrategy)
    
    # Create data feeds for both tickers
    data1 = bt.feeds.PandasData(
        dataname=price_data[ticker1],
        fromdate=start_date,
        todate=end_date,
        timeframe=bt.TimeFrame.Days,
        name=ticker1
    )
    
    data2 = bt.feeds.PandasData(
        dataname=price_data[ticker2],
        fromdate=start_date,
        todate=end_date,
        timeframe=bt.TimeFrame.Days,
        name=ticker2
    )
    
    # Add data feeds to cerebro
    cerebro.adddata(data1)
    cerebro.adddata(data2)
    
    # Set initial cash and commission
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    
    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.03, annualize=True)
    # Fix: Replace SortinoRatio with Returns analyzer to calculate Sortino later
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
    
    # Run the backtest
    results = cerebro.run()
    
    return results[0] if results else None, pair

# Part 7: Performance Metrics Calculation
def calculate_metrics(strat, pair):
    """Calculate performance metrics from backtest results"""
    if not strat:
        return None
    
    # Extract metrics
    initial_value = strat.broker.startingcash
    final_value = strat.broker.getvalue()
    total_return = (final_value / initial_value - 1) * 100
    
    # Get metrics from analyzers
    sharpe = strat.analyzers.sharpe.get_analysis().get('sharperatio', 0)
    drawdown = strat.analyzers.drawdown.get_analysis()
    max_drawdown = drawdown.get('max', {}).get('drawdown', 0) * 100  # Convert to percentage
    
    trade_analysis = strat.analyzers.trade.get_analysis()
    total_trades = trade_analysis.get('total', {}).get('total', 0)
    
    # Calculate annualized return
    returns_analysis = strat.analyzers.returns.get_analysis()
    annualized_return = returns_analysis.get('ravg', 0) * 252 * 100  # Annualize using 252 trading days
    
    # We're not calculating Sortino since it's not available as a built-in analyzer
    metrics = {
        'Pair': f"{pair[0]}-{pair[1]}",
        'Initial Value': initial_value,
        'Final Value': final_value,
        'Total Return (%)': total_return,
        'Annualized Return (%)': annualized_return,
        'Sharpe Ratio': sharpe,
        'Max Drawdown (%)': max_drawdown,
        'Total Trades': total_trades
    }
    
    return metrics

# Part 8: Reporting and Saving Results
def save_results(metrics_list, output_file):
    """Save backtest results to a file and print summary"""
    # Create DataFrame from metrics
    results_df = pd.DataFrame(metrics_list)
    
    # Save to CSV
    results_df.to_csv(output_file, index=False)
    
    # Create a text summary
    summary_file = output_file.replace('.csv', '.txt')
    with open(summary_file, 'w') as f:
        f.write("PAIRS TRADING BACKTEST RESULTS\n")
        f.write("==============================\n\n")
        
        f.write(f"Number of Pairs Tested: {len(metrics_list)}\n\n")
        
        # Average metrics
        f.write("AVERAGE PERFORMANCE METRICS:\n")
        f.write(f"Average Total Return: {results_df['Total Return (%)'].mean():.2f}%\n")
        f.write(f"Average Annualized Return: {results_df['Annualized Return (%)'].mean():.2f}%\n")
        f.write(f"Average Sharpe Ratio: {results_df['Sharpe Ratio'].mean():.2f}\n")
        f.write(f"Average Sortino Ratio: {results_df['Sortino Ratio'].mean():.2f}\n")
        f.write(f"Average Max Drawdown: {results_df['Max Drawdown (%)'].mean():.2f}%\n")
        f.write(f"Average Trades per Pair: {results_df['Total Trades'].mean():.1f}\n\n")
        
        # Best performing pair
        best_idx = results_df['Total Return (%)'].idxmax()
        best_pair = results_df.iloc[best_idx]
        
        f.write("BEST PERFORMING PAIR:\n")
        f.write(f"Pair: {best_pair['Pair']}\n")
        f.write(f"Total Return: {best_pair['Total Return (%)']:.2f}%\n")
        f.write(f"Annualized Return: {best_pair['Annualized Return (%)']:.2f}%\n")
        f.write(f"Sharpe Ratio: {best_pair['Sharpe Ratio']:.2f}\n")
        f.write(f"Sortino Ratio: {best_pair['Sortino Ratio']:.2f}\n")
        f.write(f"Max Drawdown: {best_pair['Max Drawdown (%)']:.2f}%\n")
        f.write(f"Total Trades: {int(best_pair['Total Trades'])}\n\n")
        
        # Worst performing pair
        worst_idx = results_df['Total Return (%)'].idxmin()
        worst_pair = results_df.iloc[worst_idx]
        
        f.write("WORST PERFORMING PAIR:\n")
        f.write(f"Pair: {worst_pair['Pair']}\n")
        f.write(f"Total Return: {worst_pair['Total Return (%)']:.2f}%\n")
        
    # Print summary to console
    print(f"\nResults saved to {output_file} and {summary_file}")
    
    # Print summary statistics to console
    print("\nBacktest Results Summary:")
    print(f"Number of Pairs Tested: {len(metrics_list)}")
    print(f"Average Total Return: {results_df['Total Return (%)'].mean():.2f}%")
    print(f"Average Sharpe Ratio: {results_df['Sharpe Ratio'].mean():.2f}")
    print(f"Best Performing Pair: {best_pair['Pair']} ({best_pair['Total Return (%)']:.2f}%)")

# Main execution
if __name__ == "__main__":
    # File paths
    input_file = "dados_com_features_tecnicas.csv"
    output_file = "backtest_results.csv"
    
    # Load data
    data = load_data(input_file)
    
    # Extract tickers and prepare price data
    tickers = extract_tickers(data)
    print(f"Found {len(tickers)} tickers in the dataset")
    
    # Split data into training and testing periods
    # Use first 5 years for clustering, rest for backtesting
    all_dates = pd.to_datetime(data.index)
    split_date = all_dates.min() + pd.DateOffset(years=5)
    train_data = data[all_dates <= split_date]
    test_data = data[all_dates > split_date]
    
    # Extract features for clustering from training period
    print("Extracting features for clustering...")
    feature_df = extract_features_for_clustering(train_data, tickers)
    
    # Perform clustering
    print("Performing DBSCAN clustering...")
    clustered_tickers = perform_clustering(feature_df, eps=0.8, min_samples=2)
    
    print(f"Found {len(clustered_tickers)} clusters")
    for cluster_id, cluster_tickers in clustered_tickers.items():
        print(f"Cluster {cluster_id}: {', '.join(cluster_tickers)}")
    
    # Form pairs from clusters
    pairs = form_pairs(clustered_tickers)
    print(f"Formed {len(pairs)} pairs for backtesting")
    
    # Prepare price data for backtesting
    price_data = prepare_price_data(data, tickers)
    
    # Define backtest period
    start_date = all_dates[all_dates > split_date].min().to_pydatetime()
    end_date = all_dates.max().to_pydatetime()
    print(f"Backtesting period: {start_date.date()} to {end_date.date()}")
    
    # Run backtests for each pair
    all_metrics = []
    for i, pair in enumerate(pairs):
        print(f"Backtesting pair {i+1}/{len(pairs)}: {pair[0]}-{pair[1]}...")
        
        try:
            strat, pair = run_backtest(price_data, pair, start_date, end_date)
            metrics = calculate_metrics(strat, pair)
            
            if metrics:
                all_metrics.append(metrics)
                print(f"  Total Return: {metrics['Total Return (%)']:.2f}%, Sharpe: {metrics['Sharpe Ratio']:.2f}")
        except Exception as e:
            print(f"  Error backtesting pair {pair}: {str(e)}")
    
    # Save and report results
    if all_metrics:
        save_results(all_metrics, output_file)
    else:
        print("No valid backtest results to save")