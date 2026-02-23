#!/usr/bin/env python3
"""
Simple script to verify portfolio math from YAML bank positions file.
Reads positions, aggregates by account, calculates percentages.
"""
import yaml
from decimal import Decimal
from pprint import pprint
from collections import defaultdict

# Read YAML file
with open('sample_data/bank_positions.yaml', 'r') as f:
  data = yaml.safe_load(f)

positions_by_account = defaultdict(lambda: {'positions': {}, 'account_total_value': Decimal('0')})

for position in data['positions']:
  account = position['account_id']
  ticker = position['ticker']
  shares = position['shares']
  market_value = Decimal(str(position['market_value']))

  positions_by_account[account]['positions'][ticker] = {
    'shares': shares,
    'market_value': float(market_value)
  }

  positions_by_account[account]['account_total_value'] += market_value

# Calculate percentages
result = {}
for account, data in sorted(positions_by_account.items()):
  result[account] = {
    'positions': data['positions'],
    'account_total_value': float(data['account_total_value'])
  }

  acct_total = data['account_total_value']
  for ticker, pos_data in result[account]['positions'].items():
    pos_value = Decimal(str(pos_data['market_value']))
    if acct_total > 0:
      pct = (pos_value / acct_total) * 100
      pos_data['pct_of_account'] = float(pct)
    else:
      pos_data['pct_of_account'] = 0.0

print("PORTFOLIO ANALYSIS FROM BANK POSITIONS YAML")
print("=" * 80)
pprint(result, width=100)

print("\n\nCOMPLIANCE CHECK (>20% threshold)")
print("=" * 80)
for account, data in sorted(result.items()):
  violations = []
  for ticker, pos_data in sorted(data['positions'].items()):
    pct = pos_data['pct_of_account']
    if pct > 20.0:
      violations.append({
        'ticker': ticker,
        'market_value': pos_data['market_value'],
        'pct': pct,
        'excess': pct - 20.0
      })

  if violations:
    print(f"\n{account}: {len(violations)} violation(s)")
    print(f" Total account value: ${data['account_total_value']:,.2f}")
    for v in violations:
      print(f" - {v['ticker']:6s}: ${v['market_value']:>10,.2f} = {v['pct']:5.1f}% (excess: +{v['excess']:.1f}%)")
  else:
    print(f"\n{account}: No violations")
