import yfinance as yf
df = yf.download('VALE3.SA',
                 start='2025-08-25',
                    end='2025-08-29',
                    actions=True,
                    group_by='ticker',
                    auto_adjust=True,
                    back_adjust=True
                )

print(df)