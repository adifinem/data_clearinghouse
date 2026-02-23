#!/usr/bin/env python3
"""
Interactive TUI demo for portfolio reconciliation system.
Uses Textual for a full-featured terminal user interface.
"""
import os
import sys
import argparse
import requests
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, OptionList, Label
from textual.widgets.option_list import Option
from textual.binding import Binding
from textual.screen import Screen
from rich.text import Text
from rich.table import Table
from rich import box

# Base URL for API
BASE_URL = "http://localhost:5000"

# Global data storage
APP_DATA = {
  "ingest_results": [],
  "accounts": ["ACC001", "ACC002", "ACC003", "ACC004"],
  "dates": ["2026-01-15"],
  "selected_account": "ACC001",
  "selected_date": "2026-01-15",
  "format": "1", # Default to format 1
}


class IngestScreen(Screen):
  """Screen showing file ingestion statistics and format comparison."""

  BINDINGS = [
    Binding("i", "app.switch_screen('ingest')", "Ingest", show=True),
    Binding("c", "app.switch_screen('compliance')", "Compliance", show=True),
    Binding("r", "app.switch_screen('reconciliation')", "Reconciliation", show=True),
    Binding("q", "app.quit", "Quit", show=True),
  ]

  def compose(self) -> ComposeResult:
    yield Header()
    yield Container(
      Static("[bold cyan]File Ingestion Summary[/bold cyan]", id="title"),
      Static(id="ingest-stats"),
      Static("\n[bold yellow]Format Equivalence Verification[/bold yellow]"),
      Static(id="format-comparison"),
      Static(id="note"),
      id="main-content",
    )
    yield Footer()

  def on_mount(self) -> None:
    """Load and display ingestion data."""
    self.update_display()

  def update_display(self) -> None:
    """Update the ingestion statistics display."""
    if not APP_DATA["ingest_results"]:
      self.query_one("#ingest-stats", Static).update(
        "[dim]No data ingested yet. Ingesting files...[/dim]"
      )
      return

    # Create ingestion summary table
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    table.add_column("File", style="cyan")
    table.add_column("Format", style="yellow")
    table.add_column("Records", justify="right", style="green")
    table.add_column("Valid", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Success Rate", justify="right", style="blue")

    for result in APP_DATA["ingest_results"]:
      table.add_row(
        result["file_name"],
        result["file_format"],
        str(result["records_processed"]),
        str(result["records_valid"]),
        str(result["records_failed"]),
        result["success_rate"],
      )

    self.query_one("#ingest-stats", Static).update(table)

    # Format comparison - find Format 1 and Format 2
    format1 = None
    format2 = None

    for result in APP_DATA["ingest_results"]:
      if result["file_format"] == "CSV_FORMAT1":
        format1 = result
      elif result["file_format"] == "PIPE_FORMAT2":
        format2 = result

    # Update note based on format selection
    if APP_DATA["format"] == "both":
      self.query_one("#note", Static).update(
        "\n[dim italic]Note: Both trade formats ingested for comparison demonstration. "
        "Reconciliation view de-duplicates on display (divides expected shares by 2).[/dim italic]"
      )
    elif APP_DATA["format"] == "1":
      self.query_one("#note", Static).update(
        "\n[dim italic]Note: CSV trade format (Format 1) ingested. "
        "Use --format 2 or --format both to compare formats.[/dim italic]"
      )
    elif APP_DATA["format"] == "2":
      self.query_one("#note", Static).update(
        "\n[dim italic]Note: Pipe-delimited trade format (Format 2) ingested. "
        "Use --format 1 or --format both to compare formats.[/dim italic]"
      )

    if format1 and format2:
      comp_table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
      comp_table.add_column("Metric", style="yellow")
      comp_table.add_column("Format 1 (CSV)", justify="right", style="green")
      comp_table.add_column("Format 2 (Pipe)", justify="right", style="blue")
      comp_table.add_column("Match", justify="center")

      match_records = format1["records_processed"] == format2["records_processed"]
      match_success = format1["success_rate"] == format2["success_rate"]

      comp_table.add_row(
        "Records Processed",
        str(format1["records_processed"]),
        str(format2["records_processed"]),
        "[green]✓[/green]" if match_records else "[red]✗[/red]",
      )
      comp_table.add_row(
        "Success Rate",
        format1["success_rate"],
        format2["success_rate"],
        "[green]✓[/green]" if match_success else "[red]✗[/red]",
      )

      self.query_one("#format-comparison", Static).update(comp_table)
    else:
      self.query_one("#format-comparison", Static).update(
        "[dim]Waiting for both trade formats to be ingested...[/dim]"
      )


class ComplianceScreen(Screen):
  """Screen showing compliance concentration violations."""

  BINDINGS = [
    Binding("i", "app.switch_screen('ingest')", "Ingest", show=True),
    Binding("c", "app.switch_screen('compliance')", "Compliance", show=True),
    Binding("r", "app.switch_screen('reconciliation')", "Reconciliation", show=True),
    Binding("q", "app.quit", "Quit", show=True),
  ]

  def compose(self) -> ComposeResult:
    yield Header()
    yield Horizontal(
      ScrollableContainer(Static(id="compliance-details"), id="main-view"),
      Vertical(
        Label("[bold]Account:[/bold]", classes="sidebar-label"),
        OptionList(
          Option("All Accounts", id="all"),
          Option("ACC001", id="ACC001"),
          Option("ACC002", id="ACC002"),
          Option("ACC003", id="ACC003"),
          Option("ACC004", id="ACC004"),
          id="account-selector",
        ),
        Label(""),
        Static(id="compliance-summary", classes="sidebar-summary"),
        id="sidebar",
      ),
    )
    yield Footer()

  def on_mount(self) -> None:
    """Load compliance data on mount."""
    # Set initial selection
    account_selector = self.query_one("#account-selector", OptionList)
    account_selector.highlighted = 0 # All Accounts
    self.refresh_data()

  def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
    """Handle account selection."""
    if event.option.id == "all":
      APP_DATA["selected_account"] = "all"
    else:
      APP_DATA["selected_account"] = event.option.id
    self.refresh_data()

  def refresh_data(self) -> None:
    """Fetch and display compliance data."""
    try:
      response = requests.get(
        f"{BASE_URL}/compliance/concentration",
        params={"date": APP_DATA["selected_date"]},
        timeout=5,
      )
      data = response.json()

      # Get violations from both sources
      from_trades = data.get("from_trades", {})
      from_bank = data.get("from_bank", {})

      trades_violations = from_trades.get("violations", [])
      bank_violations = from_bank.get("violations", [])

      # Filter by account if not 'all'
      account_filter = APP_DATA["selected_account"].strip().lower()
      if account_filter and account_filter != "all":
        trades_violations = [v for v in trades_violations if v["account_id"].lower() == account_filter]
        bank_violations = [v for v in bank_violations if v["account_id"].lower() == account_filter]

      # Update sidebar summary
      summary = (
        f"[bold]Filter:[/bold]\n{APP_DATA['selected_account']}\n\n"
        f"[bold]From Trades:[/bold]\n{len(trades_violations)}\n\n"
        f"[bold]From Bank:[/bold]\n{len(bank_violations)}\n"
      )
      self.query_one("#compliance-summary", Static).update(summary)

      # Build combined display
      output = ""

      # FROM TRADES section
      output += "[bold cyan]FROM TRADE CALCULATIONS[/bold cyan]\n"
      if len(trades_violations) > 0:
        table = Table(
          box=box.ROUNDED,
          show_header=True,
          header_style="bold cyan",
        )
        table.add_column("Account", style="cyan")
        table.add_column("Ticker", style="yellow")
        table.add_column("Shares", justify="right")
        table.add_column("Market Value", justify="right")
        table.add_column("Account Total", justify="right")
        table.add_column("Concentration %", justify="right", style="red bold")
        table.add_column("Excess %", justify="right", style="red")

        for v in trades_violations:
          table.add_row(
            v["account_id"],
            v["ticker"],
            str(v["shares"]),
            f"${v['market_value']:,.2f}",
            f"${v['account_total_value']:,.2f}",
            f"{v['concentration_pct']:.2f}%",
            f"+{v['excess_pct']:.2f}%",
          )
      else:
        table = "[dim]No violations[/dim]"

      output_trades = table

      # FROM BANK section
      if len(bank_violations) > 0:
        table2 = Table(
          box=box.ROUNDED,
          show_header=True,
          header_style="bold magenta",
        )
        table2.add_column("Account", style="cyan")
        table2.add_column("Ticker", style="yellow")
        table2.add_column("Shares", justify="right")
        table2.add_column("Market Value", justify="right")
        table2.add_column("Account Total", justify="right")
        table2.add_column("Concentration %", justify="right", style="red bold")
        table2.add_column("Excess %", justify="right", style="red")

        for v in bank_violations:
          table2.add_row(
            v["account_id"],
            v["ticker"],
            str(v["shares"]),
            f"${v['market_value']:,.2f}",
            f"${v['account_total_value']:,.2f}",
            f"{v['concentration_pct']:.2f}%",
            f"+{v['excess_pct']:.2f}%",
          )
      else:
        table2 = "[dim]No violations (or no bank data)[/dim]"

      # Combine both sections using Rich Text
      from rich.console import Console, Group
      from rich.panel import Panel

      group = Group(
        Panel(output_trades, title="[bold cyan]FROM TRADE CALCULATIONS[/bold cyan]", border_style="cyan"),
        "",
        Panel(table2, title="[bold magenta]FROM BANK POSITIONS[/bold magenta]", border_style="magenta"),
      )

      self.query_one("#compliance-details", Static).update(group)

    except Exception as e:
      self.query_one("#compliance-details", Static).update(
        f"[bold red]Error: {e}[/bold red]"
      )


class ReconciliationScreen(Screen):
  """Screen showing trade vs bank position reconciliation."""

  BINDINGS = [
    Binding("i", "app.switch_screen('ingest')", "Ingest", show=True),
    Binding("c", "app.switch_screen('compliance')", "Compliance", show=True),
    Binding("r", "app.switch_screen('reconciliation')", "Reconciliation", show=True),
    Binding("q", "app.quit", "Quit", show=True),
  ]

  def compose(self) -> ComposeResult:
    yield Header()
    yield Horizontal(
      ScrollableContainer(Static(id="recon-details"), id="main-view"),
      Vertical(
        Label("[bold]Account:[/bold]", classes="sidebar-label"),
        OptionList(
          Option("All Accounts", id="all"),
          Option("ACC001", id="ACC001"),
          Option("ACC002", id="ACC002"),
          Option("ACC003", id="ACC003"),
          Option("ACC004", id="ACC004"),
          id="account-selector",
        ),
        Label(""),
        Static(id="recon-summary", classes="sidebar-summary"),
        id="sidebar",
      ),
    )
    yield Footer()

  def on_mount(self) -> None:
    """Load reconciliation data on mount."""
    # Set initial selection
    account_selector = self.query_one("#account-selector", OptionList)
    account_selector.highlighted = 1 # ACC001
    self.refresh_data()

  def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
    """Handle account selection."""
    if event.option.id == "all":
      APP_DATA["selected_account"] = "all"
    else:
      APP_DATA["selected_account"] = event.option.id
    self.refresh_data()

  def refresh_data(self) -> None:
    """Fetch and display reconciliation data."""
    try:
      response = requests.get(
        f"{BASE_URL}/reconciliation",
        params={"date": APP_DATA["selected_date"]},
        timeout=5,
      )
      data = response.json()

      # DE-DUPLICATE: Divide expected shares by 2 if both formats were ingested
      # This keeps the server behavior correct while cleaning up the display
      if APP_DATA["format"] == "both":
        for disc in data["discrepancies"]:
          disc["expected_shares"] = disc["expected_shares"] // 2
          disc["difference"] = disc["actual_shares"] - disc["expected_shares"]

      # Filter by account if not 'all'
      account_filter = APP_DATA["selected_account"].strip().lower()
      discrepancies = data["discrepancies"]

      if account_filter and account_filter != "all":
        discrepancies = [
          d for d in discrepancies
          if d["account_id"].lower() == account_filter
        ]

      # Update sidebar summary
      summary = (
        f"[bold]Filter:[/bold]\n{APP_DATA['selected_account']}\n\n"
        f"[bold]Date:[/bold]\n{data['date']}\n\n"
        f"[bold]Discrepancies:[/bold]\n{len(discrepancies)}\n"
      )
      self.query_one("#recon-summary", Static).update(summary)

      # Discrepancies table
      if len(discrepancies) > 0:
        table = Table(
          box=box.DOUBLE,
          show_header=True,
          header_style="bold yellow",
          title=f"RECONCILIATION DISCREPANCIES ({APP_DATA['selected_account']})",
        )
        table.add_column("Account", style="cyan")
        table.add_column("Ticker", style="yellow")
        table.add_column("Expected\n(Trades)", justify="right", style="green")
        table.add_column("Actual\n(Bank)", justify="right", style="blue")
        table.add_column("Difference", justify="right")
        table.add_column("Status", style="bold")

        for disc in discrepancies:
          diff = disc["difference"]
          diff_style = "red bold" if diff != 0 else "green"
          status = disc["status"].replace("_", " ").title()
          status_style = "red" if "mismatch" in disc["status"] or "missing" in disc["status"] else "yellow"

          table.add_row(
            disc["account_id"],
            disc["ticker"],
            str(disc["expected_shares"]),
            str(disc["actual_shares"]),
            f"[{diff_style}]{diff:+d}[/{diff_style}]",
            f"[{status_style}]{status}[/{status_style}]",
          )

        self.query_one("#recon-details", Static).update(table)
      else:
        self.query_one("#recon-details", Static).update(
          f"\n\n[bold green]✓ All positions reconciled for {APP_DATA['selected_account']}[/bold green]"
        )

    except Exception as e:
      self.query_one("#recon-details", Static).update(
        f"[bold red]Error: {e}[/bold red]"
      )


class PortfolioReconApp(App):
  """Interactive TUI for Portfolio Reconciliation System."""

  CSS = """
  #main-content {
    padding: 1 2;
  }

  #title {
    text-align: center;
    padding: 1 0;
    height: 3;
  }

  #main-view {
    width: 3fr;
    height: 100%;
    border: solid $accent;
    padding: 1;
  }

  #sidebar {
    width: 1fr;
    height: 100%;
    border: solid $primary;
    padding: 1;
  }

  .sidebar-label {
    margin-bottom: 1;
    text-style: bold;
  }

  .sidebar-value {
    margin-bottom: 1;
    color: $accent;
  }

  .sidebar-summary {
    margin-top: 2;
    padding: 1;
    border: solid $secondary;
  }

  #account-selector {
    height: auto;
    max-height: 10;
    margin-bottom: 1;
  }

  #date-display {
    padding: 1;
    background: $surface;
    margin-bottom: 1;
  }

  OptionList {
    border: solid $primary;
  }

  OptionList > .option-list--option-highlighted {
    background: $accent;
  }
  """

  MODES = {
    "ingest": IngestScreen,
    "compliance": ComplianceScreen,
    "reconciliation": ReconciliationScreen,
  }

  BINDINGS = [
    Binding("i", "switch_screen('ingest')", "Ingest", show=True),
    Binding("c", "switch_screen('compliance')", "Compliance", show=True),
    Binding("r", "switch_screen('reconciliation')", "Reconciliation", show=True),
    Binding("q", "quit", "Quit", show=True),
  ]

  def on_mount(self) -> None:
    """Initialize app and ingest data."""
    self.title = "Portfolio Data Clearinghouse"
    self.sub_title = "Interactive Reconciliation Demo"

    # Check if API is running
    try:
      response = requests.get(f"{BASE_URL}/health", timeout=2)
      if response.status_code != 200:
        self.exit(message="ERROR: API is not healthy!")
        return
    except:
      self.exit(message="ERROR: API is not running! Start with: python app.py")
      return

    # Ingest files on startup
    self.ingest_files()

    # Switch to ingest screen
    self.switch_mode("ingest")

  def action_switch_screen(self, screen_name: str) -> None:
    """Switch to a different screen."""
    self.switch_mode(screen_name)

  def ingest_files(self) -> None:
    """Ingest sample data files based on format selection."""
    files = [("sample_data/bank_positions.yaml", "YAML_POSITIONS")]

    # Add trade files based on format selection
    if APP_DATA["format"] == "1":
      files.insert(0, ("sample_data/trades_format1.csv", "CSV_FORMAT1"))
    elif APP_DATA["format"] == "2":
      files.insert(0, ("sample_data/trades_format2.txt", "PIPE_FORMAT2"))
    elif APP_DATA["format"] == "both":
      files.insert(0, ("sample_data/trades_format1.csv", "CSV_FORMAT1"))
      files.append(("sample_data/trades_format2.txt", "PIPE_FORMAT2"))

    APP_DATA["ingest_results"] = []

    for file_path, file_format in files:
      try:
        with open(file_path, "rb") as f:
          files_data = {"file": (os.path.basename(file_path), f)}
          form_data = {"file_format": file_format}
          response = requests.post(
            f"{BASE_URL}/ingest",
            files=files_data,
            data=form_data,
            timeout=10,
          )

        if response.status_code in [200, 207]:
          APP_DATA["ingest_results"].append(response.json())

      except Exception as e:
        APP_DATA["ingest_results"].append({
          "file_name": os.path.basename(file_path),
          "file_format": file_format,
          "records_processed": 0,
          "records_valid": 0,
          "records_failed": 0,
          "success_rate": "0.00%",
          "error": str(e),
        })


def ingest_files_simple(format_choice: str) -> None:
  """Ingest files for simple mode."""
  files = [("sample_data/bank_positions.yaml", "YAML_POSITIONS")]

  if format_choice == "1":
    files.insert(0, ("sample_data/trades_format1.csv", "CSV_FORMAT1"))
  elif format_choice == "2":
    files.insert(0, ("sample_data/trades_format2.txt", "PIPE_FORMAT2"))
  elif format_choice == "both":
    files.insert(0, ("sample_data/trades_format1.csv", "CSV_FORMAT1"))
    files.append(("sample_data/trades_format2.txt", "PIPE_FORMAT2"))

  for file_path, file_format in files:
    try:
      with open(file_path, "rb") as f:
        files_data = {"file": (os.path.basename(file_path), f)}
        form_data = {"file_format": file_format}
        requests.post(
          f"{BASE_URL}/ingest",
          files=files_data,
          data=form_data,
          timeout=10,
        )
    except Exception as e:
      print(f"Error ingesting {file_path}: {e}", file=sys.stderr)


def simple_output(format_choice: str) -> None:
  """Generate simple ASCII output."""
  date = "2026-01-15"

  # Check API health
  try:
    response = requests.get(f"{BASE_URL}/health", timeout=2)
    if response.status_code != 200:
      print("ERROR: API is not healthy!", file=sys.stderr)
      sys.exit(1)
  except:
    print("ERROR: API is not running! Start with: python app.py", file=sys.stderr)
    sys.exit(1)

  # Ingest files
  import time
  ingest_files_simple(format_choice)
  time.sleep(1.5) # Give server time to process ingestion

  # Fetch all positions
  print("=" * 80)
  print("PORTFOLIO POSITIONS")
  print("=" * 80)
  print()

  accounts = ["ACC001", "ACC002", "ACC003", "ACC004"]
  all_positions = []

  for account in accounts:
    try:
      response = requests.get(
        f"{BASE_URL}/positions",
        params={"account": account, "date": date},
        timeout=5,
      )
      if response.status_code == 200:
        data = response.json()
        if "positions" in data and len(data["positions"]) > 0:
          for pos in data["positions"]:
            all_positions.append({
              "account": account,
              "ticker": pos["ticker"],
              "shares": pos["shares"],
              "market_value": pos["market_value"],
              "cost_basis": pos["cost_basis"],
            })
    except Exception as e:
      print(f"Error fetching positions for {account}: {e}", file=sys.stderr)

  # Sort by account then ticker
  all_positions.sort(key=lambda x: (x["account"], x["ticker"]))

  if len(all_positions) == 0:
    print("No positions found. Ensure data was ingested correctly.")
    print()

  current_account = None
  for pos in all_positions:
    if pos["account"] != current_account:
      if current_account is not None:
        print()
      current_account = pos["account"]
      print(f"Account: {pos['account']}")

    # Handle missing market value (e.g., ACC004 not in bank file)
    if pos['market_value'] is None:
      print(f" {pos['ticker']:6s} {pos['shares']:6d} shares "
         f"@ ${pos['cost_basis']:8.2f} = [missing bank data]")
    else:
      print(f" {pos['ticker']:6s} {pos['shares']:6d} shares "
         f"@ ${pos['cost_basis']:8.2f} = ${pos['market_value']:12.2f}")

  # Reconciliation
  print()
  print("=" * 80)
  print("RECONCILIATION DISCREPANCIES")
  print("=" * 80)
  print()

  try:
    response = requests.get(
      f"{BASE_URL}/reconciliation",
      params={"date": date},
      timeout=5,
    )
    data = response.json()

    # De-duplicate if both formats loaded
    if format_choice == "both":
      for disc in data["discrepancies"]:
        disc["expected_shares"] = disc["expected_shares"] // 2
        disc["difference"] = disc["actual_shares"] - disc["expected_shares"]

    if data["discrepancies_found"] == 0:
      print("No discrepancies found. All positions reconciled.")
    else:
      discrepancies = sorted(data["discrepancies"], key=lambda x: (x["account_id"], x["ticker"]))

      for disc in discrepancies:
        status_text = disc["status"].replace("_", " ").upper()
        print(f"{disc['account_id']:6s} {disc['ticker']:6s} "
           f"Expected: {disc['expected_shares']:6d} "
           f"Actual: {disc['actual_shares']:6d} "
           f"Diff: {disc['difference']:+6d} "
           f"[{status_text}]")

      # Format comparison if both
      if format_choice == "both":
        print()
        print("Format Comparison:")
        print(" Both trade formats ingested (Format 1 CSV + Format 2 Pipe)")
        print(" Expected shares shown above are de-duplicated (divided by 2)")

  except Exception as e:
    print(f"Error fetching reconciliation: {e}", file=sys.stderr)

  # Compliance
  print()
  print("=" * 80)
  print("COMPLIANCE VIOLATIONS (>20% concentration)")
  print("=" * 80)
  print()

  try:
    response = requests.get(
      f"{BASE_URL}/compliance/concentration",
      params={"date": date},
      timeout=5,
    )
    data = response.json()

    # Show violations from TRADES
    print("FROM TRADE CALCULATIONS:")
    print("-" * 80)
    from_trades = data.get("from_trades", {})
    if from_trades.get("violations_found", 0) == 0:
      print(" No violations found.")
    else:
      violations = from_trades.get("violations", [])
      for v in violations:
        print(f" {v['account_id']:6s} {v['ticker']:6s} "
           f"{v['shares']:6d} shares "
           f"${v['market_value']:12,.2f} / ${v['account_total_value']:12,.2f} "
           f"{v['concentration_pct']:5.2f}% "
           f"(excess: +{v['excess_pct']:5.2f}%)")

    print()

    # Show violations from BANK
    print("FROM BANK POSITIONS:")
    print("-" * 80)
    from_bank = data.get("from_bank", {})
    if from_bank.get("violations_found", 0) == 0:
      print(" No violations found (or no bank data).")
    else:
      violations = from_bank.get("violations", [])
      for v in violations:
        print(f" {v['account_id']:6s} {v['ticker']:6s} "
           f"{v['shares']:6d} shares "
           f"${v['market_value']:12,.2f} / ${v['account_total_value']:12,.2f} "
           f"{v['concentration_pct']:5.2f}% "
           f"(excess: +{v['excess_pct']:5.2f}%)")

  except Exception as e:
    print(f"Error fetching compliance: {e}", file=sys.stderr)

  print()


def main():
  """Run the application (TUI or simple mode)."""
  parser = argparse.ArgumentParser(description="Portfolio Reconciliation Demo")
  parser.add_argument(
    "--format",
    choices=["1", "2", "both"],
    default="1",
    help="Trade file format to ingest: 1=CSV, 2=Pipe, both=Both formats",
  )
  parser.add_argument(
    "--simple",
    action="store_true",
    help="Simple ASCII output instead of interactive TUI",
  )

  args = parser.parse_args()

  if args.simple:
    # Simple mode: just print to stdout
    simple_output(args.format)
  else:
    # TUI mode
    APP_DATA["format"] = args.format
    app = PortfolioReconApp()
    app.run()


if __name__ == "__main__":
  main()
