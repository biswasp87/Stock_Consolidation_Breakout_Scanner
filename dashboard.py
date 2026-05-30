import pandas as pd
import numpy as np
from dash import Dash, dash_table, dcc, html
from dash.dependencies import Input, Output
import plotly.express as px
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
        # Fallback to direct URL if client fails
        url = f"https://storage.googleapis.com/{bucket_name}/{file_name}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                df = pd.read_csv(io.StringIO(response.text))
                return df['SYMBOL'].tolist()
            else:
                print(f"Failed to fetch FNO list via URL: {response.status_code}")
                return get_mock_fno_list()
        except Exception as e2:
            print(f"Error fetching FNO list via URL: {e2}")
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
    dates = pd.date_range(end=pd.Timestamp.now(), periods=30)
    for symbol in symbols:
        base_price = np.random.uniform(100, 2000)
        vol_base = np.random.uniform(100000, 1000000)
        for i, date in enumerate(dates):
            # Create some consolidation and a breakout at the very end
            if i < len(dates) - 1:
                # Consolidation phase
                price_range = 0.01 * base_price
                high = base_price + np.random.uniform(0, price_range)
                low = base_price - np.random.uniform(0, price_range)
                close = np.random.uniform(low, high)
                open_p = np.random.uniform(low, high)
                vol = vol_base * np.random.uniform(0.8, 1.2)
                qt = vol * np.random.uniform(0.2, 0.4)
            else:
                # Potential breakout/breakdown phase on the latest day
                if symbol in ["RELIANCE", "TCS"]: # Breakout
                    high = base_price * 1.2
                    low = base_price * 1.1
                    close = base_price * 1.15
                    open_p = base_price * 1.11
                    vol = vol_base * 2.5
                    qt = vol * 0.6
                elif symbol in ["INFY"]: # Breakdown
                    high = base_price * 0.85
                    low = base_price * 0.75
                    close = base_price * 0.8
                    open_p = base_price * 0.84
                    vol = vol_base * 2.5
                    qt = vol * 0.6
                else: # Still consolidating
                    price_range = 0.02 * base_price
                    high = base_price + np.random.uniform(0, price_range)
                    low = base_price - np.random.uniform(0, price_range)
                    close = np.random.uniform(low, high)
                    open_p = np.random.uniform(low, high)
                    vol = vol_base * np.random.uniform(0.8, 1.2)
                    qt = vol * np.random.uniform(0.2, 0.4)

            data.append({
                'SYMBOL': symbol,
                'TIMESTAMP': date,
                'EQ_HIGH_PRICE': high,
                'EQ_LOW_PRICE': low,
                'EQ_OPEN_PRICE': open_p,
                'EQ_CLOSE_PRICE': close,
                'EQ_TTL_TRD_QNTY': vol,
                'EQ_QT': qt
            })
    return pd.DataFrame(data)

# --- Processing Logic ---

def process_data(df):
    thresholds = [0.025, 0.05, 0.10, 0.15, 0.20]
    results = []

    df['TIMESTAMP'] = pd.to_datetime(df['TIMESTAMP'])
    df = df.sort_values(['SYMBOL', 'TIMESTAMP'])

    for symbol, group in df.groupby('SYMBOL'):
        if len(group) < 2:
            continue

        latest_day = group.iloc[-1]
        hist_days = group.iloc[:-1]

        for t in thresholds:
            n_days = 0
            max_h = -1
            min_l = float('inf')

            # Look back from the last historical day
            for i in range(len(hist_days)-1, -1, -1):
                day = hist_days.iloc[i]
                new_max = max(max_h, day['EQ_HIGH_PRICE'])
                new_min = min(min_l, day['EQ_LOW_PRICE'])

                if (new_max - new_min) / new_min <= t:
                    max_h = new_max
                    min_l = new_min
                    n_days += 1
                else:
                    break

            if n_days > 7:
                consolidation_period = hist_days.iloc[len(hist_days)-n_days:]
                avg_vol = consolidation_period['EQ_TTL_TRD_QNTY'].mean()
                avg_qt = consolidation_period['EQ_QT'].mean()

                latest_close = latest_day['EQ_CLOSE_PRICE']
                latest_vol = latest_day['EQ_TTL_TRD_QNTY']
                latest_qt = latest_day['EQ_QT']

                status = "Consolidation"
                is_breakout = latest_close > max_h
                is_breakdown = latest_close < min_l

                case1 = latest_vol > avg_vol
                case2 = latest_qt > avg_qt

                if is_breakout or is_breakdown:
                    prefix = "Breakout" if is_breakout else "Breakdown"
                    if case1 and case2:
                        status = f"{prefix} with Volume & QT"
                    elif case1:
                        status = f"{prefix} with Volume"
                    elif case2:
                        status = f"{prefix} with QT"
                    else:
                        status = prefix

                results.append({
                    'SYMBOL': symbol,
                    'Threshold': f"{t*100}%",
                    'Consolidation Days': n_days,
                    'Status': status,
                    'Latest Close': round(latest_close, 2),
                    'Max High': round(max_h, 2),
                    'Min Low': round(min_l, 2),
                    'Avg Vol': round(avg_vol, 2),
                    'Avg QT': round(avg_qt, 2)
                })

    return pd.DataFrame(results)

# --- Dash App ---

app = Dash(__name__)

# Initial Data Load
fno_symbols = fetch_fno_list()
raw_data = fetch_stock_data(fno_symbols)
processed_df = process_data(raw_data)

app.layout = html.Div([
    html.H1("Stock Consolidation & Breakout Dashboard", style={'textAlign': 'center'}),

    html.Div([
        dash_table.DataTable(
            id='stock-table',
            columns=[{"name": i, "id": i} for i in processed_df.columns],
            data=processed_df.to_dict('records'),
            sort_action="native",
            filter_action="native",
            page_action="native",
            page_size=20,
            style_data_conditional=[
                {
                    'if': {
                        'filter_query': '{Status} contains "Breakout"',
                    },
                    'backgroundColor': '#d4edda',
                    'color': '#155724'
                },
                {
                    'if': {
                        'filter_query': '{Status} contains "Breakdown"',
                    },
                    'backgroundColor': '#f8d7da',
                    'color': '#721c24'
                }
            ],
            style_cell={'textAlign': 'left', 'padding': '10px'},
            style_header={
                'backgroundColor': 'rgb(230, 230, 230)',
                'fontWeight': 'bold'
            },
        )
    ], style={'margin': '20px'})
])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)
