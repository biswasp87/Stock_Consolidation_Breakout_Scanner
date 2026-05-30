import pandas as pd
import numpy as np
from dashboard import process_data

def test_logic():
    # Create sample data for one symbol
    dates = pd.date_range(end='2023-01-10', periods=20)
    # Base price 1000. Variance 2.5% is [987.5, 1012.5]
    # We'll make it consolidate for 15 days, then breakout on day 20.
    data = []
    for i in range(19):
        data.append({
            'SYMBOL': 'TEST',
            'TIMESTAMP': dates[i],
            'EQ_HIGH_PRICE': 1005,
            'EQ_LOW_PRICE': 995,
            'EQ_OPEN_PRICE': 1000,
            'EQ_CLOSE_PRICE': 1000,
            'EQ_TTL_TRD_QNTY': 100,
            'EQ_QT': 40
        })
    # Day 20: Breakout with Volume & QT
    data.append({
        'SYMBOL': 'TEST',
        'TIMESTAMP': dates[19],
        'EQ_HIGH_PRICE': 1050,
        'EQ_LOW_PRICE': 1040,
        'EQ_OPEN_PRICE': 1040,
        'EQ_CLOSE_PRICE': 1045, # Above 1005
        'EQ_TTL_TRD_QNTY': 500,  # Above 100
        'EQ_QT': 200            # Above 40
    })

    df = pd.DataFrame(data)
    processed = process_data(df)

    print("Columns:", processed.columns.tolist())

    # Check 2.5% threshold (should have >7 days)
    assert '2.5% Days' in processed.columns
    assert processed.iloc[0]['2.5% Days'] == 19
    assert processed.iloc[0]['2.5% Status'] == 'Breakout with Volume & QT'

    # Check 5% threshold
    assert '5% Days' in processed.columns
    assert processed.iloc[0]['5% Days'] == 19

    print("Logic test passed!")

if __name__ == "__main__":
    test_logic()
