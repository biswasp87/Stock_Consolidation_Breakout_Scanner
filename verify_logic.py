import pandas as pd
import numpy as np
from dashboard import process_data

def test_consolidation_logic():
    # Create test data for a single symbol
    dates = pd.date_range(end='2024-01-30', periods=20)
    # Days 0-18: Consolidation around 100 within 2.5% range
    # Range: [99, 101] -> (101-99)/99 = 0.0202... < 0.025
    data = []
    for i in range(19):
        data.append({
            'SYMBOL': 'TEST',
            'TIMESTAMP': dates[i],
            'EQ_HIGH_PRICE': 101,
            'EQ_LOW_PRICE': 99,
            'EQ_OPEN_PRICE': 100,
            'EQ_CLOSE_PRICE': 100,
            'EQ_TTL_TRD_QNTY': 1000,
            'EQ_QT': 400
        })

    # Day 19: Latest day, Breakout with Volume & QT
    data.append({
        'SYMBOL': 'TEST',
        'TIMESTAMP': dates[19],
        'EQ_HIGH_PRICE': 110,
        'EQ_LOW_PRICE': 105,
        'EQ_OPEN_PRICE': 106,
        'EQ_CLOSE_PRICE': 108, # Above 101
        'EQ_TTL_TRD_QNTY': 2000, # Above 1000
        'EQ_QT': 1000 # Above 400
    })

    df = pd.DataFrame(data)
    results = process_data(df)

    print("Test Results:")
    print(results)

    # Check if we have results for 2.5% threshold
    res_25 = results[results['Threshold'] == '2.5%']
    assert len(res_25) == 1
    assert res_25.iloc[0]['Consolidation Days'] == 19
    assert res_25.iloc[0]['Status'] == 'Breakout with Volume & QT'

    print("Consolidation and Breakout logic verified!")

if __name__ == "__main__":
    test_consolidation_logic()
