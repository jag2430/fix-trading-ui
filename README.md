# FIX Trading Ticket UI

A Python Dash web application that provides a trading ticket interface to send orders via the FIX protocol.

## Features

- **Trading Ticket** - Clean UI similar to professional trading platforms
  - Buy/Sell toggle
  - Market/Limit order types
  - Symbol and quantity input
  - Real-time order submission

- **Order Management**
  - View sent orders
  - Cancel open orders
  - Click on order to auto-fill cancel form

- **Execution Reports**
  - Real-time execution updates
  - Color-coded by execution type (Fill, Partial Fill, Rejected, Cancelled)
  - Clear execution history

- **Session Monitoring**
  - FIX session connection status
  - Auto-refresh every 5 seconds

## Prerequisites

- Python 3.8+
- Running FIX Client (Spring Boot app on port 8081)
- Running FIX Exchange Simulator (on port 9876)

## Installation

```bash
cd fix-trading-ui
pip install -r requirements.txt
```

## Running

1. **Start the Exchange Simulator** (terminal 1):
   ```bash
   cd fix-exchange-simulator
   mvn spring-boot:run
   ```

2. **Start the FIX Client** (terminal 2):
   ```bash
   cd fix-client
   mvn spring-boot:run
   ```

3. **Start the Trading UI** (terminal 3):
   ```bash
   cd fix-trading-ui
   python app.py
   ```

4. Open your browser to: **http://localhost:8050**

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Trading UI     │────▶│   FIX Client    │────▶│    Exchange     │
│  (Dash:8050)    │REST │ (Spring:8081)   │ FIX │  (Spring:9876)  │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Usage

### Submitting Orders

1. Enter a symbol (e.g., AAPL)
2. Select Buy or Sell
3. Enter quantity
4. Select Market or Limit
5. If Limit, enter price
6. Click "Submit Order"

### Cancelling Orders

**Option 1:** Click on an order in the Orders table, then click "Cancel"

**Option 2:** Manually enter:
- ClOrdId of the order to cancel
- Symbol
- Side (BUY/SELL)
- Click "Cancel"

## Configuration

Edit `app.py` to change the API endpoint:

```python
API_BASE_URL = "http://localhost:8081/api"
```

## Troubleshooting

**"Cannot connect to FIX Client API"**
- Make sure the Spring Boot FIX Client is running on port 8081

**"Connection Status: Disconnected"**
- Make sure the Exchange Simulator is running on port 9876
- Check that SenderCompID/TargetCompID match in both configs

**Orders not filling**
- Send a counter-order (if you sent a BUY, send a SELL at same or lower price)
- Check the exchange order book: `curl http://localhost:8080/api/exchange/orderbook/AAPL`
