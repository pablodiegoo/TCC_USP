Desenvolva um script em Python para baixar e tratar dados de ações da B3, com foco em ativos do índice Ibovespa.

**1. Coleta de Dados:**
- **Fonte:** Utilize a biblioteca `yfinance` para extrair os dados.
- **Ativos:** Baixe os dados de todas as ações que compuseram o índice Ibovespa nos últimos 10 anos. A lista de ativos deve ser obtida dinamicamente para garantir a atualização, mas a prioridade é a extração de dados históricos para os papéis que fazem parte do índice atualmente.
- **Período:** Os dados devem cobrir os últimos 10 anos completos, desde 01 de janeiro de 2015 até o dia anterior à execução do script.
- **Atributos:** Para cada ativo, colete os preços de Abertura (`Open`), Fechamento (`Close`), Máxima (`High`), Mínima (`Low`), Volume (`Volume`) e Fechamento Ajustado (`Adj Close`).

**2. Pré-processamento e Limpeza:**
- **Remoção de Duplicatas:** Elimine quaisquer linhas duplicadas baseadas na data e no ticker.
- **Tratamento de Dados Faltantes (`NaN`):** Preencha os valores faltantes de forma apropriada, por exemplo, utilizando a última observação válida (`forward fill`). A estratégia de tratamento deve ser documentada nos comentários do código.
- **Ajuste de Preços:** Os preços devem ser ajustados para proventos (dividendos, JCP) e desdobramentos. O atributo `Adj Close` do `yfinance` já realiza essa tarefa, mas certifique-se de que os demais preços estejam alinhados (pode ser necessário recalcular a partir do `Adj Close` para manter a coerência).

**3. Saída:**
- O resultado deve ser um único DataFrame do Pandas, onde cada linha representa uma data e cada coluna contém os preços de Abertura, Fechamento, etc. para cada ativo. As colunas devem ser nomeadas no formato `TICKER_ATRIBUTO` (ex: `PETR4_Close`).
- Salve o DataFrame final em um arquivo CSV nomeado `dados_bovespa_ultimos_10_anos.csv`.
- Adicione comentários ao código para explicar cada etapa principal (coleta, limpeza, preenchimento, salvamento).

**4. Considerações Técnicas:**
- O script deve ser modular, com funções claras para cada etapa (ex: `coletar_dados()`, `tratar_dados()`, `salvar_dados()`).
- O código deve incluir um bloco `try-except` para lidar com possíveis erros de conexão ou ativos que não estejam mais disponíveis, registrando-os sem interromper a execução.