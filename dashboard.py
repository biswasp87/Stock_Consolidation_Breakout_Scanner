import pandas as pd
import numpy as np
from dash import Dash, dash_table, dcc, html, callback_context
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from google.cloud import bigquery, storage
import requests
import io
import os

# --- Configuration & Data Fetching ---

def fetch_fno_list():
    bucket_name = "bba_support_files"
    file_name = "WL_FNO.csv"
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        content = blob.download_as_text()
        df = pd.read_csv(io.StringIO(content))
        return df['SYMBOL'].tolist()
    except Exception as e:
        print(f"Error fetching FNO list via client: {e}")
        url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                df = pd.read_csv(io.StringIO(response.text))
                return df['SYMBOL'].tolist()
            else:
                return get_mock_fno_list()
        except Exception:
            return get_mock_fno_list()

def fetch_stock_data(symbols):
    project_id = "phrasal-fire-373510"
    dataset_id = "Big_Bull_Analysis"
    table_id = "Master_Data_Equity"

    query = f"""
    SELECT SYMBOL, TIMESTAMP, EQ_HIGH_PRICE, EQ_LOW_PRICE, EQ_OPEN_PRICE, EQ_CLOSE_PRICE, EQ_TTL_TRD_QNTY, EQ_QT
    FROM `{project_id}.{dataset_id}.{table_id}`
    WHERE SYMBOL IN UNNEST(@symbols)
    """

    try:
        client = bigquery.Client()
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("symbols", "STRING", symbols)
            ]
        )
        df = client.query(query, job_config=job_config).to_dataframe()
        return df
    except Exception as e:
        print(f"Error fetching BigQuery data: {e}")
        return get_mock_stock_data(symbols)

def get_mock_fno_list():
    return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC"]

def get_mock_stock_data(symbols):
    data = []
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100)
    for symbol in symbols:
        base_price = np.random.uniform(100, 2000)
        vol_base = np.random.uniform(100000, 1000000)
        for i, date in enumerate(dates):
            if i < len(dates) - 1:
                price_range = 0.01 * base_price
                high = base_price + np.random.uniform(0, price_range)
                low = base_price - np.random.uniform(0, price_range)
                close = np.random.uniform(low, high)
                open_p = np.random.uniform(low, high)
                vol = vol_base * np.random.uniform(0.8, 1.2)
                qt = vol * np.random.uniform(0.2, 0.4)
            else:
                if symbol in ["RELIANCE", "TCS"]: # Breakout
                    high, low, close, open_p = base_price*1.2, base_price*1.1, base_price*1.15, base_price*1.11
                    vol, qt = vol_base * 2.5, vol_base * 2.5 * 0.6
                elif symbol in ["INFY"]: # Breakdown
                    high, low, close, open_p = base_price*0.85, base_price*0.75, base_price*0.8, base_price*0.84
                    vol, qt = vol_base * 2.5, vol_base * 2.5 * 0.6
                else: # Still consolidating
                    price_range = 0.01 * base_price
                    high, low = base_price + np.random.uniform(0, price_range), base_price - np.random.uniform(0, price_range)
                    close, open_p = np.random.uniform(low, high), np.random.uniform(low, high)
                    vol, qt = vol_base * np.random.uniform(0.8, 1.2), vol_base * np.random.uniform(0.8, 1.2) * 0.3

            data.append({'SYMBOL': symbol, 'TIMESTAMP': date, 'EQ_HIGH_PRICE': high, 'EQ_LOW_PRICE': low,
                         'EQ_OPEN_PRICE': open_p, 'EQ_CLOSE_PRICE': close, 'EQ_TTL_TRD_QNTY': vol, 'EQ_QT': qt})
    return pd.DataFrame(data)

# --- Processing Logic ---

def process_data(df):
    thresholds = [0.025, 0.05, 0.10, 0.15, 0.20]
    df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
    df = df.sort_values(['SYMBOL', 'TIMESTAMP'])

    rows = []
    for symbol, group in df.groupby('SYMBOL'):
        if len(group) < 9: continue
        latest_day = group.iloc[-1]
        hist_days = group.iloc[:-1]

        row = {'id': symbol, 'SYMBOL': symbol}
        for t in thresholds:
            n_days, max_h, min_l = 0, -1, float('inf')
            for i in range(len(hist_days)-1, -1, -1):
                day = hist_days.iloc[i]
                new_max, new_min = max(max_h, day['EQ_HIGH_PRICE']), min(min_l, day['EQ_LOW_PRICE'])
                if (new_max - new_min) / new_min <= t:
                    max_h, min_l, n_days = new_max, new_min, n_days + 1
                else: break

            # Format as 2.5% or 5% (no .0 if integer)
            t_val = t * 100
            t_str = f"{int(t_val) if t_val == int(t_val) else t_val}%"

            if n_days > 7:
                consolidation_period = hist_days.iloc[len(hist_days)-n_days:]
                avg_vol, avg_qt = consolidation_period['EQ_TTL_TRD_QNTY'].mean(), consolidation_period['EQ_QT'].mean()
                status = "Consolidation"
                is_bo, is_bd = latest_day['EQ_CLOSE_PRICE'] > max_h, latest_day['EQ_CLOSE_PRICE'] < min_l
                c1, c2 = latest_day['EQ_TTL_TRD_QNTY'] > avg_vol, latest_day['EQ_QT'] > avg_qt
                if is_bo or is_bd:
                    prefix = "Breakout" if is_bo else "Breakdown"
                    status = f"{prefix} with Volume & QT" if c1 and c2 else (f"{prefix} with Volume" if c1 else (f"{prefix} with QT" if c2 else prefix))

                row[f"{t_str} Days"] = n_days
                row[f"{t_str} Status"] = status
                # Store hidden details for the graph
                row[f"{t_str}_max_h"] = max_h
                row[f"{t_str}_min_l"] = min_l
                row[f"{t_str}_avg_vol"] = avg_vol
                row[f"{t_str}_avg_qt"] = avg_qt
            else:
                row[f"{t_str} Days"] = n_days
                row[f"{t_str} Status"] = "None"
        rows.append(row)
    return pd.DataFrame(rows)

# --- Dash App ---

app = Dash(__name__)

fno_symbols = fetch_fno_list()
raw_data = fetch_stock_data(fno_symbols)
processed_df = process_data(raw_data)

app.layout = html.Div([
    html.H1("Stock Consolidation & Breakout Dashboard", style={'textAlign': 'center'}),

    html.Div([
        html.Label("Filter View: "),
        dcc.RadioItems(
            id='view-filter',
            options=[
                {'label': 'Only Consolidation Stocks', 'value': 'cons'},
                {'label': 'Only Breakout & Breakdown Stocks', 'value': 'bo_bd'},
                {'label': 'Both', 'value': 'both'}
            ],
            value='both',
            inline=True
        )
    ], style={'margin': '20px'}),

    html.Div([
        # Left Side: Graph in a Card
        html.Div([
            html.Div([
                html.Div([
                    html.Label("Display Days: ", style={'fontWeight': 'bold'}),
                    dcc.Slider(id='days-slider', min=30, max=250, step=10, value=90,
                               marks={i: str(i) for i in range(30, 251, 40)}),
                ], style={'marginBottom': '20px'}),

                html.Button("Close Graph", id="close-graph", n_clicks=0,
                            style={'marginBottom': '10px', 'backgroundColor': '#f0f0f0', 'border': '1px solid #ccc', 'padding': '5px 10px', 'cursor': 'pointer'}),

                dcc.Graph(id='stock-graph')
            ], style={
                'border': '1px solid #ddd',
                'borderRadius': '5px',
                'padding': '15px',
                'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)',
                'backgroundColor': 'white'
            })
        ], id='graph-container', style={'width': '0%', 'display': 'none', 'paddingRight': '10px'}),

        # Right Side: Table
        html.Div([
            dash_table.DataTable(
                id='stock-table',
                columns=[{"name": i, "id": i} for i in processed_df.columns if i != 'id' and not i.endswith(('_max_h', '_min_l', '_avg_vol', '_avg_qt'))],
                data=processed_df.to_dict('records'),
                sort_action="native",
                filter_action="native",
                page_action="native",
                page_size=15,
                style_data_conditional=[
                    {'if': {'filter_query': f'{{{int(t*100) if (t*100)==int(t*100) else t*100}% Status}} contains "Breakout"',
                            'column_id': f'{int(t*100) if (t*100)==int(t*100) else t*100}% Status'},
                     'backgroundColor': '#d4edda', 'color': '#155724'} for t in [0.025, 0.05, 0.1, 0.15, 0.2]
                ] + [
                    {'if': {'filter_query': f'{{{int(t*100) if (t*100)==int(t*100) else t*100}% Status}} contains "Breakdown"',
                            'column_id': f'{int(t*100) if (t*100)==int(t*100) else t*100}% Status'},
                     'backgroundColor': '#f8d7da', 'color': '#721c24'} for t in [0.025, 0.05, 0.1, 0.15, 0.2]
                ],
                style_cell={'textAlign': 'left', 'padding': '5px', 'fontSize': '11px'},
                style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
                active_cell=None
            )
        ], id='table-container', style={'width': '100%', 'display': 'inline-block', 'verticalAlign': 'top'})
    ], id='main-content', style={'display': 'flex', 'padding': '10px'})
])

@app.callback(
    [Output('stock-table', 'data'),
     Output('table-container', 'style'),
     Output('graph-container', 'style')],
    [Input('view-filter', 'value'),
     Input('stock-table', 'active_cell'),
     Input('close-graph', 'n_clicks')],
    [State('stock-table', 'data')]
)
def update_table_and_view(filter_val, active_cell, n_clicks, current_data):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Filtering logic
    filtered_df = processed_df
    status_cols = [c for c in processed_df.columns if 'Status' in c]
    if filter_val == 'cons':
        filtered_df = processed_df[processed_df[status_cols].apply(lambda x: x.str.contains('Consolidation').any(), axis=1)]
    elif filter_val == 'bo_bd':
        filtered_df = processed_df[processed_df[status_cols].apply(lambda x: x.str.contains('Breakout|Breakdown').any(), axis=1)]

    table_data = filtered_df.to_dict('records')

    table_style = {'width': '100%', 'display': 'inline-block'}
    graph_style = {'width': '0%', 'display': 'none'}

    if triggered_id == 'stock-table' and active_cell and (active_cell['column_id'] == 'SYMBOL' or 'Status' in active_cell['column_id']):
        table_style = {'width': '50%', 'display': 'inline-block'}
        graph_style = {'width': '50%', 'display': 'inline-block', 'paddingRight': '10px'}
    elif triggered_id == 'close-graph':
        table_style = {'width': '100%', 'display': 'inline-block'}
        graph_style = {'width': '0%', 'display': 'none'}

    return table_data, table_style, graph_style

@app.callback(
    Output('stock-graph', 'figure'),
    [Input('stock-table', 'active_cell'),
     Input('days-slider', 'value')],
    [State('stock-table', 'derived_virtual_data')]
)
def update_graph(active_cell, display_days, virtual_data):
    if not active_cell or not virtual_data:
        return go.Figure()

    col_id = active_cell['column_id']
    if col_id != 'SYMBOL' and 'Status' not in col_id:
        return go.Figure()

    # Determine variance threshold from column clicked
    variance = "2.5%" # Default
    if 'Status' in col_id:
        variance = col_id.replace(' Status', '')

    # Use row_id if available, otherwise index into virtual_data
    symbol = active_cell.get('row_id')
    if not symbol:
        symbol = virtual_data[active_cell['row']]['SYMBOL']

    stock_df = raw_data[raw_data['SYMBOL'] == symbol].sort_values('TIMESTAMP')

    # Filter by number of days
    stock_df = stock_df.tail(display_days)

    # Get details for selected variance from the virtual data
    row_data = next(item for item in virtual_data if item["SYMBOL"] == symbol)
    max_h = row_data.get(f"{variance}_max_h")
    min_l = row_data.get(f"{variance}_min_l")
    avg_vol = row_data.get(f"{variance}_avg_vol")
    avg_qt = row_data.get(f"{variance}_avg_qt")
    n_days = row_data.get(f"{variance} Days", 0)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0, row_heights=[0.6, 0.2, 0.2])

    # OHLC
    fig.add_trace(go.Candlestick(x=stock_df['TIMESTAMP'], open=stock_df['EQ_OPEN_PRICE'], high=stock_df['EQ_HIGH_PRICE'],
                                 low=stock_df['EQ_LOW_PRICE'], close=stock_df['EQ_CLOSE_PRICE'], name='OHLC'), row=1, col=1)
    # Volume
    fig.add_trace(go.Bar(x=stock_df['TIMESTAMP'], y=stock_df['EQ_TTL_TRD_QNTY'], name='Volume', marker_color='orange'), row=2, col=1)
    # QT
    fig.add_trace(go.Bar(x=stock_df['TIMESTAMP'], y=stock_df['EQ_QT'], name='QT', marker_color='teal'), row=3, col=1)

    if n_days > 7 and max_h is not None:
        # Consolidation lines on OHLC
        all_symbol_data = raw_data[raw_data['SYMBOL'] == symbol].sort_values('TIMESTAMP')
        cons_start_date = all_symbol_data.iloc[-(n_days+1)]['TIMESTAMP']
        cons_end_date = all_symbol_data.iloc[-2]['TIMESTAMP']

        # Only add shape if it's within visible range or partially visible
        fig.add_shape(type="rect", x0=cons_start_date, y0=min_l, x1=cons_end_date, y1=max_h,
                      line=dict(color="RoyalBlue", width=2), fillcolor="LightSkyBlue", opacity=0.3, row=1, col=1)

        # Avg Vol and QT lines
        fig.add_hline(y=avg_vol, line_dash="dash", line_color="red", annotation_text="Avg Vol", row=2, col=1)
        fig.add_hline(y=avg_qt, line_dash="dash", line_color="red", annotation_text="Avg QT", row=3, col=1)

    fig.update_layout(
        title=f"{symbol} Analysis ({variance})",
        xaxis_rangeslider_visible=False,
        height=700,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=40, b=10)
    )

    # Black borders for subplots
    for i in [1, 2, 3]:
        fig.update_xaxes(showline=True, linewidth=1, linecolor='black', mirror=True, row=i, col=1)
        fig.update_yaxes(showline=True, linewidth=1, linecolor='black', mirror=True, row=i, col=1)

    return fig

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8050)
