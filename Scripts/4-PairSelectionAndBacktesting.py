"""
Script: 4-PairSelectionAndBacktesting.py

Objetivo
- Ler o arquivo 'dados_com_features_tecnicas.csv' (índice = data, colunas no formato TICKER_Atributo)
- Selecionar pares via clustering (DBSCAN) com base em features técnicas normalizadas, treinando no período inicial (ex.: 5 anos)
- Formar todos os pares dentro de cada cluster
- Rodar backtest de pairs trading (Backtrader) por par com lógica via z-score do spread (A - B)
- Agregar performance (média igualitária dos retornos diários dos pares) e calcular métricas
- Imprimir e salvar relatório com métricas

Dependências: pandas, numpy, scikit-learn, backtrader
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

try:
	import backtrader as bt
except Exception:  # pragma: no cover
	bt = None  # Permitirá mensagem amigável se não instalado

from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler


# =============================
# Utilidades e Tipos
# =============================


@dataclass
class Pair:
	a: str
	b: str

	def name(self) -> str:
		return f"{self.a}-{self.b}"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Seleção de pares por clustering e backtest com Backtrader")
	parser.add_argument(
		"--csv",
		type=str,
		default=os.path.join(os.path.dirname(__file__), "dados_com_features_tecnicas.csv"),
		help="Caminho do CSV de features técnicas (default: arquivo na mesma pasta do script)",
	)
	parser.add_argument("--train-years", type=int, default=5, help="Quantidade de anos para treinamento (DBSCAN)")
	parser.add_argument("--eps", type=float, default=1.5, help="Parâmetro eps do DBSCAN")
	parser.add_argument("--min-samples", type=int, default=2, help="Parâmetro min_samples do DBSCAN")
	parser.add_argument("--z-window", type=int, default=60, help="Janela para cálculo do z-score do spread")
	parser.add_argument("--z-entry", type=float, default=2.0, help="Limite de entrada (|z| > z-entry)")
	parser.add_argument("--z-exit", type=float, default=0.5, help="Limite de saída (|z| < z-exit)")
	parser.add_argument("--initial-cash", type=float, default=100_000.0, help="Capital inicial do backtest")
	parser.add_argument("--commission", type=float, default=0.001, help="Custo de transação (ex.: 0.001 = 0.1%)")
	parser.add_argument(
		"--max-pairs",
		type=int,
		default=25,
		help="Limite opcional de pares para backtest (evita execuções muito longas)",
	)
	parser.add_argument(
		"--results-file",
		type=str,
		default=os.path.join(os.path.dirname(__file__), "backtest_results.txt"),
		help="Arquivo de saída para salvar resultados agregados",
	)
	parser.add_argument(
		"--pairs-csv",
		type=str,
		default=os.path.join(os.path.dirname(__file__), "pairs_selected.csv"),
		help="Arquivo CSV para salvar os pares selecionados",
	)
	return parser.parse_args()


def read_features_csv(csv_path: str) -> pd.DataFrame:
	if not os.path.exists(csv_path):
		raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")
	df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
	if not isinstance(df.index, pd.DatetimeIndex):
		# Tenta converter caso a leitura não tenha feito parse
		df.index = pd.to_datetime(df.index, errors="coerce")
	df = df.sort_index().dropna(how="all")
	return df


def extract_tickers(columns: Sequence[str]) -> List[str]:
	tickers = sorted({c.split("_")[0] for c in columns if "_" in c})
	return tickers


def split_train_test_dates(index: pd.DatetimeIndex, train_years: int) -> Tuple[pd.Timestamp, pd.Timestamp]:
	start = index.min()
	if pd.isna(start):
		raise ValueError("Índice de datas vazio/ inválido no CSV")
	train_end = start + pd.DateOffset(years=train_years)
	# Garante que o train_end esteja presente no índice (ou será usado somente como corte)
	return start, train_end


def is_price_like(col: str) -> bool:
	suffix = col.split("_")[1] if "_" in col else ""
	price_suffixes = {"Close", "Open", "High", "Low", "AdjClose", "Adj_Close", "Adj Close", "Price", "Volume"}
	return suffix in price_suffixes


def extract_attributes(columns: Sequence[str]) -> List[str]:
	"""Retorna os sufixos de atributos (ex.: RSI14, Volatility), excluindo os campos de preço/volume."""
	attrs = sorted({c.split("_", 1)[1] for c in columns if "_" in c and not is_price_like(c)})
	return attrs


def build_training_matrix(df: pd.DataFrame, tickers: List[str], train_end: pd.Timestamp) -> Tuple[np.ndarray, List[str]]:
	"""
	Constrói matriz de features por ticker para o período de treinamento [início .. train_end)
	Estratégia robusta: alinhar por atributo (sufixo após o underscore). Para cada ticker e atributo, usar a mediana temporal.
	Imputar valores faltantes por mediana global do atributo (entre tickers) e, se ainda ausente, por 0.
	Retorna X (n_tickers x n_attributes) e a lista de nomes dos atributos.
	"""
	df_train = df.loc[df.index < train_end]
	if df_train.empty:
		raise ValueError("Período de treinamento vazio. Verifique as datas e o parâmetro --train-years.")

	attributes = extract_attributes(df.columns)
	if not attributes:
		raise ValueError("Nenhum atributo técnico encontrado nas colunas do CSV.")

	# Pré-calcula mediana global por atributo (entre tickers)
	attr_global_median: Dict[str, float] = {}
	for attr in attributes:
		cols_attr = [c for c in df.columns if c.endswith(f"_{attr}")]
		if not cols_attr:
			attr_global_median[attr] = 0.0
			continue
		sub = df_train[cols_attr].copy()
		sub = sub.ffill().bfill()
		# mediana temporal por ticker-coluna, depois mediana entre tickers
		med_per_col = sub.median(axis=0)
		val = float(med_per_col.median()) if not med_per_col.empty and med_per_col.notna().any() else 0.0
		attr_global_median[attr] = val

	X_rows: List[List[float]] = []
	used_tickers: List[str] = []
	for t in tickers:
		# Pelo menos 1 atributo precisa existir para o ticker
		has_any = any(f"{t}_{attr}" in df.columns for attr in attributes)
		if not has_any:
			continue
		row: List[float] = []
		for attr in attributes:
			col = f"{t}_{attr}"
			if col in df_train.columns:
				s = df_train[col].ffill().bfill()
				val = float(s.median()) if s.notna().any() else float("nan")
			else:
				val = float("nan")
			if not math.isfinite(val):
				val = attr_global_median.get(attr, 0.0)
			if not math.isfinite(val):
				val = 0.0
			row.append(val)
		X_rows.append(row)
		used_tickers.append(t)

	X = np.array(X_rows, dtype=float)
	# Garantia final contra NaNs/inf
	if np.isnan(X).any() or np.isinf(X).any():
		X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
	return X, attributes


def cluster_tickers(
	df: pd.DataFrame,
	eps: float,
	min_samples: int,
	train_years: int,
) -> Tuple[List[Pair], List[Tuple[int, List[str]]]]:
	"""
	Retorna a lista de pares formados (todas as combinações dentro de cada cluster) e
	a lista (label, tickers_do_cluster) para referência/salvamento.
	"""
	tickers = extract_tickers(df.columns)
	if not tickers:
		raise ValueError("Não foi possível identificar tickers nas colunas do CSV")

	start, train_end = split_train_test_dates(df.index, train_years)
	X, feature_names = build_training_matrix(df, tickers, train_end)
	if X.size == 0:
		raise ValueError("Matriz de treinamento vazia. Verifique se há features técnicas no CSV.")

	# Normaliza
	scaler = StandardScaler()
	X_scaled = scaler.fit_transform(X)

	# Ajusta DBSCAN
	# Garante que existem amostras suficientes
	if X_scaled.shape[0] < max(2, min_samples):
		return [], []
	db = DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean")
	labels = db.fit_predict(X_scaled)

	# Mapeia labels -> tickers (observando que a ordem de X segue a de 'tickers' filtrados por features presentes)
	# Precisamos reconstruir a lista de tickers efetivamente usados em X
	used_tickers: List[str] = []
	for t in tickers:
		cols_t = [c for c in df.columns if c.startswith(f"{t}_") and not is_price_like(c)]
		if cols_t:
			used_tickers.append(t)

	clusters: Dict[int, List[str]] = {}
	for t, lab in zip(used_tickers, labels):
		clusters.setdefault(lab, []).append(t)

	# Remove ruído (-1)
	pairs: List[Pair] = []
	cluster_list: List[Tuple[int, List[str]]] = []
	for lab, ts in clusters.items():
		if lab == -1:
			continue
		ts_sorted = sorted(set(ts))
		cluster_list.append((lab, ts_sorted))
		# Todas as combinações (pares) dentro do cluster
		for a, b in itertools.combinations(ts_sorted, 2):
			pairs.append(Pair(a=a, b=b))

	return pairs, cluster_list


# =============================
# Backtrader - Estratégia
# =============================


class PairTradingZScore(bt.Strategy):  # type: ignore[misc]
	params = dict(
		window=60,
		entry=2.0,
		exit=0.5,
		stake_perc=0.2,  # fração do valor atual a alocar por lado do par
	)

	def __init__(self):
		if len(self.datas) != 2:
			raise ValueError("A estratégia requer exatamente 2 datas (2 ativos)")

		d0, d1 = self.datas[0], self.datas[1]
		self.spread = d0.close - d1.close
		self.sma = bt.ind.SMA(self.spread, period=self.p.window)
		self.std = bt.ind.StdDev(self.spread, period=self.p.window)
		# Evita divisão por zero: adiciona um epsilon mínimo
		self.eps = 1e-9
		self.zscore = (self.spread - self.sma) / (self.std + self.eps)

		# Guarda referências de ordens (tipagem livre para evitar problemas quando bt não está disponível)
		self.order_refs: List[object] = []
		self.trade_count = 0

	def log(self, txt):  # opcional para debug
		pass

	def has_position(self) -> bool:
		return any(self.getposition(d).size != 0 for d in self.datas)

	def notify_trade(self, trade):
		if trade.isclosed:
			self.trade_count += 1

	def next(self):
		# Garante janela suficiente
		if len(self) < self.p.window:
			return

		z = float(self.zscore[0])
		if not math.isfinite(z):
			return

		d0, d1 = self.datas[0], self.datas[1]
		pos0 = self.getposition(d0).size
		pos1 = self.getposition(d1).size

		value = self.broker.getvalue()
		target_value_each_side = value * self.p.stake_perc
		# Calcula tamanho por preço atual, usando o menor para manter simetria
		size0 = int(max(0, target_value_each_side / max(1e-9, d0.close[0])))
		size1 = int(max(0, target_value_each_side / max(1e-9, d1.close[0])))
		size = int(max(0, min(size0, size1)))

		# Sinais
		if not self.has_position():
			if z > self.p.entry and size > 0:
				# z alto: spread A-B acima da média => A caro vs B
				# Vende A (d0), compra B (d1)
				self.sell(data=d0, size=size)
				self.buy(data=d1, size=size)
			elif z < -self.p.entry and size > 0:
				# z baixo: A barato vs B
				# Compra A (d0), vende B (d1)
				self.buy(data=d0, size=size)
				self.sell(data=d1, size=size)
		else:
			# Saída quando z volta para a média
			if abs(z) < self.p.exit:
				if pos0 != 0:
					self.close(data=d0)
				if pos1 != 0:
					self.close(data=d1)


def make_pandasdata_from_series(series: pd.Series) -> bt.feeds.PandasData:  # type: ignore[misc]
	"""Cria um feed Backtrader a partir de uma série de preços de fechamento."""
	df = pd.DataFrame({"close": series})
	data = bt.feeds.PandasData(dataname=df, open=None, high=None, low=None, close="close", volume=None, openinterest=None)
	return data


def run_backtest_for_pair(
	pair: Pair,
	test_df: pd.DataFrame,
	initial_cash: float,
	commission: float,
	z_window: int,
	z_entry: float,
	z_exit: float,
) -> Tuple[pd.Series, Dict[str, float]]:
	"""
	Executa um backtest para um par e retorna:
	- Série de retornos diários (indexada por data)
	- Dicionário com métricas básicas do par
	"""
	if bt is None:
		raise RuntimeError("Backtrader não está instalado. Instale com: pip install backtrader")

	close_a_col = f"{pair.a}_Close"
	close_b_col = f"{pair.b}_Close"
	if close_a_col not in test_df.columns or close_b_col not in test_df.columns:
		# Sem dados de preço para o par
		return pd.Series(dtype=float), {"trades": 0, "final_value": initial_cash}

	# Monta dataframe do par e remove quaisquer linhas com NaN (limpar linhas em branco)
	pair_df = pd.DataFrame({
		pair.a: test_df[close_a_col],
		pair.b: test_df[close_b_col],
	}).dropna()

	if len(pair_df) < max(100, z_window + 5):
		return pd.Series(dtype=float), {"trades": 0, "final_value": initial_cash}

	sA = pair_df[pair.a]
	sB = pair_df[pair.b]

	cerebro = bt.Cerebro()
	cerebro.broker.setcash(initial_cash)
	cerebro.broker.setcommission(commission=commission)

	data_a = make_pandasdata_from_series(sA)
	data_b = make_pandasdata_from_series(sB)

	cerebro.adddata(data_a, name=pair.a)
	cerebro.adddata(data_b, name=pair.b)

	cerebro.addstrategy(
		PairTradingZScore,
		window=z_window,
		entry=z_entry,
		exit=z_exit,
		stake_perc=0.2,
	)

	# Analyzers: retornos diários e trades
	cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="timereturn", timeframe=bt.TimeFrame.Days)
	cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

	results = cerebro.run()
	strat = results[0]

	# Retornos diários em dict {datetime: return}
	returns_dict = strat.analyzers.timereturn.get_analysis()
	# Converte para Series ordenada por data
	sr = pd.Series(returns_dict)
	if not sr.empty:
		sr.index = pd.to_datetime(sr.index)
		sr = sr.sort_index()

	trade_an = strat.analyzers.trades.get_analysis()
	total_trades = 0
	try:
		total_trades = int(trade_an.get("total", {}).get("closed", 0))
	except Exception:
		total_trades = 0

	final_value = cerebro.broker.getvalue()
	metrics = {"trades": total_trades, "final_value": float(final_value)}
	return sr, metrics


# =============================
# Métricas
# =============================


def compute_metrics_from_returns(daily_ret: pd.Series, initial_cash: float) -> Dict[str, float]:
	if daily_ret.empty:
		return {
			"total_return": 0.0,
			"annual_return": 0.0,
			"sharpe": 0.0,
			"sortino": 0.0,
			"max_drawdown": 0.0,
			"num_days": 0,
		}

	daily_ret = daily_ret.dropna()
	if daily_ret.empty:
		return {
			"total_return": 0.0,
			"annual_return": 0.0,
			"sharpe": 0.0,
			"sortino": 0.0,
			"max_drawdown": 0.0,
			"num_days": 0,
		}

	# Equity curve assumindo initial_cash
	equity = (1.0 + daily_ret).cumprod() * initial_cash
	total_ret = equity.iloc[-1] / initial_cash - 1.0
	n = len(daily_ret)
	ann_ret = (1.0 + total_ret) ** (252.0 / max(1, n)) - 1.0

	mean = daily_ret.mean()
	std = daily_ret.std(ddof=0)
	neg = daily_ret[daily_ret < 0]
	ddown = equity / equity.cummax() - 1.0
	max_dd = float(ddown.min()) if len(ddown) else 0.0

	sharpe = float(mean / std * math.sqrt(252)) if std > 0 else 0.0
	downside = neg.std(ddof=0)
	sortino = float(mean / downside * math.sqrt(252)) if downside > 0 else 0.0

	return {
		"total_return": float(total_ret),
		"annual_return": float(ann_ret),
		"sharpe": sharpe,
		"sortino": sortino,
		"max_drawdown": float(max_dd),
		"num_days": int(n),
	}


def main():
	args = parse_args()

	# 1) Carrega dados
	df = read_features_csv(args.csv)

	# 2) Clustering -> pares
	pairs, cluster_list = cluster_tickers(df, eps=args.eps, min_samples=args.min_samples, train_years=args.train_years)
	if not pairs:
		print("Nenhum par encontrado pelos clusters.")
		return

	# Salva pares e clusters
	try:
		pairs_df = pd.DataFrame({"pair": [p.name() for p in pairs], "a": [p.a for p in pairs], "b": [p.b for p in pairs]})
		pairs_df.to_csv(args.pairs_csv, index=False)
	except Exception:
		pass

	# 3) Split treino/teste
	start, train_end = split_train_test_dates(df.index, args.train_years)
	test_df = df.loc[df.index >= train_end].copy()
	if test_df.empty:
		print("Período de teste vazio após o corte de treinamento.")
		return

	# 4) Backtest por par (limitado por --max-pairs para acelerar)
	to_run = pairs[: args.max_pairs] if args.max_pairs and args.max_pairs > 0 else pairs

	per_pair_returns: Dict[str, pd.Series] = {}
	per_pair_metrics: Dict[str, Dict[str, float]] = {}

	for i, pair in enumerate(to_run, 1):
		print(f"Backtesting ({i}/{len(to_run)}): {pair.name()}")
		try:
			sr, metrics = run_backtest_for_pair(
				pair,
				test_df=test_df,
				initial_cash=args.initial_cash,
				commission=args.commission,
				z_window=args.z_window,
				z_entry=args.z_entry,
				z_exit=args.z_exit,
			)
		except Exception as e:
			print(f"Falha no par {pair.name()}: {e}")
			continue

		if not sr.empty:
			per_pair_returns[pair.name()] = sr
		per_pair_metrics[pair.name()] = metrics

	if not per_pair_returns:
		print("Nenhum retorno gerado pelos pares (dados insuficientes ou sem sinais).")
		return

	# 5) Agregação: média igualitária dos retornos diários entre pares
	all_ret = pd.DataFrame(per_pair_returns)
	# Alinha por data e substitui NaN por 0 para pares sem dado naquele dia
	all_ret = all_ret.sort_index().fillna(0.0)
	portfolio_ret = all_ret.mean(axis=1)

	# 6) Métricas agregadas
	metrics = compute_metrics_from_returns(portfolio_ret, initial_cash=args.initial_cash)

	total_trades = int(sum(m.get("trades", 0) for m in per_pair_metrics.values()))

	# 7) Relatórios
	print("\n===== Resumo do Backtest (Portfolio Equal-Weighted) =====")
	print(f"Retorno Total: {metrics['total_return']:.2%}")
	print(f"Retorno Anualizado: {metrics['annual_return']:.2%}")
	print(f"Sharpe Ratio: {metrics['sharpe']:.2f}")
	print(f"Sortino Ratio: {metrics['sortino']:.2f}")
	print(f"Drawdown Máximo: {metrics['max_drawdown']:.2%}")
	print(f"Número Total de Trades (soma dos pares): {total_trades}")

	# 8) Salvar em arquivo
	try:
		lines = []
		lines.append("Resumo do Backtest (Portfolio Equal-Weighted)\n")
		lines.append(f"Data/Hora geração: {datetime.now()}\n\n")
		lines.append("Parâmetros:\n")
		lines.append(f"- CSV: {args.csv}\n")
		lines.append(f"- Train Years: {args.train_years}\n")
		lines.append(f"- DBSCAN: eps={args.eps}, min_samples={args.min_samples}\n")
		lines.append(f"- Z-Score: window={args.z_window}, entry={args.z_entry}, exit={args.z_exit}\n")
		lines.append(f"- Inicial: {args.initial_cash:,.2f}, Comissão: {args.commission:.4f}\n")
		lines.append("\nMétricas do Portfólio:\n")
		lines.append(f"- Retorno Total: {metrics['total_return']:.6f}\n")
		lines.append(f"- Retorno Anualizado: {metrics['annual_return']:.6f}\n")
		lines.append(f"- Sharpe: {metrics['sharpe']:.4f}\n")
		lines.append(f"- Sortino: {metrics['sortino']:.4f}\n")
		lines.append(f"- Max Drawdown: {metrics['max_drawdown']:.6f}\n")
		lines.append(f"- Dias no Teste: {metrics['num_days']}\n")
		lines.append(f"- Total Trades (pares): {total_trades}\n")
		lines.append("\nPares Selecionados (limitados por --max-pairs):\n")
		for p in per_pair_metrics.keys():
			m = per_pair_metrics[p]
			lines.append(f"  {p}: trades={m.get('trades', 0)}, final_value={m.get('final_value', args.initial_cash):,.2f}\n")

		with open(args.results_file, "w", encoding="utf-8") as f:
			f.writelines(lines)

		# Também salva a série de retornos do portfólio para análises posteriores
		portfolio_csv = os.path.splitext(args.results_file)[0] + "_portfolio_returns.csv"
		portfolio_ret.to_csv(portfolio_csv, header=["retorno_diario"])
	except Exception as e:
		print(f"Falha ao salvar resultados: {e}")


if __name__ == "__main__":
	main()

