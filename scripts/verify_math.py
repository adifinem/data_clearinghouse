#!/usr/bin/env python3
"""
Simple script to verify portfolio math from CSV trade file.
Reads trades, aggregates by account/symbol, calculates values and percentages.
"""
import csv
from decimal import Decimal
from pprint import pprint
from collections import defaultdict

# Read CSV file
positions = defaultdict(lambda: defaultdict(lambda: {'quantity': 0, 'total_cost': Decimal('0')}))

with open('sample_data/trades_format1.csv', 'r') as f:
  reader = csv.DictReader(f)
  for row in reader:
    account = row['AccountID']
    ticker = row['Ticker']
    quantity = int(row['Quantity'])
    price = Decimal(row['Price'])
    trade_type = row['TradeType']

    # BUY adds shares, SELL subtracts
    if trade_type == 'BUY':
      positions[account][ticker]['quantity'] += quantity
      positions[account][ticker]['total_cost'] += quantity * price
    elif trade_type == 'SELL':
      positions[account][ticker]['quantity'] -= quantity
      positions[account][ticker]['total_cost'] -= quantity * price

# Build final structure
result = {}

for account, tickers in sorted(positions.items()):
  result[account] = {
    'positions': {},
    'account_total_value': Decimal('0')
  }

  # Calculate position values
  for ticker, data in sorted(tickers.items()):
    quantity = data['quantity']
    total_cost = data['total_cost']

    if quantity > 0:
      avg_price = total_cost / quantity
    else:
      avg_price = Decimal('0')

    position_value = total_cost

    result[account]['positions'][ticker] = {
      'quantity': quantity,
      'avg_price': float(avg_price),
      'position_value': float(position_value)
    }

    result[account]['account_total_value'] += position_value

  # Calculate percentages
  acct_total = result[account]['account_total_value']
  for ticker in result[account]['positions']:
    pos_value = Decimal(str(result[account]['positions'][ticker]['position_value']))
    if acct_total > 0:
      pct = (pos_value / acct_total) * 100
      result[account]['positions'][ticker]['pct_of_account'] = float(pct)
    else:
      result[account]['positions'][ticker]['pct_of_account'] = 0.0

  # Convert account total to float for display
  result[account]['account_total_value'] = float(acct_total)

print("PORTFOLIO ANALYSIS FROM TRADES CSV")
print("=" * 80)
pprint(result, width=100)
