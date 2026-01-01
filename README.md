# FIX Trading UI

A modern, real-time order entry and management interface for electronic trading, built with Python Dash and Dash Mantine Components.

## Overview

The FIX Trading UI provides a professional trading interface for submitting, monitoring, and managing orders through a FIX protocol-based trading system. It communicates with the FIX Client middleware via REST API and displays real-time order status and execution information.

## Features

### Order Entry
- **Order Types**: Support for Market and Limit orders
- **Quick Quantity Buttons**: One-click buttons for common sizes (100, 500, 1000, 5000 shares)
- **Dynamic Price Field**: Automatically shows/hides based on order type selection (hidden for Market orders)
- **Side Selection**: Clear BUY (green) and SELL (red) buttons
- **Symbol Input**: Free-form symbol entry
- **Slide-out Drawer**: Clean order entry panel that doesn't clutter the main view

### Order Management
- **Amend Orders**: Modify quantity or price of working orders
- **Cancel Orders**: Cancel any non-filled order
- **Order Actions Menu**: Click the ⋮ (vertical ellipsis) button on any order row to access amendment and cancellation options
- **Order Actions Modal**: Pop-up dialog for confirming amendments or cancellations

### Real-Time Monitoring

#### Orders Blotter
Live view of all orders with the following columns:

| Column | Description |
|--------|-------------|
| Timestamp | Order submission time |
| ClOrdId | Client order identifier (unique) |
| Symbol | Stock ticker |
| Side | BUY or SELL |
| Type | MARKET or LIMIT |
| Quantity | Order size |
| Price | Limit price (if applicable) |
| Filled | Number of shares filled |
| Status | Current order status |
| Actions | Menu button (⋮) for amend/cancel |

#### Executions Blotter
View all execution reports (fills) with:

| Column | Description |
|--------|-------------|
| ExecId | Execution identifier |
| ClOrdId | Related order ID |
| Symbol | Stock ticker |
| Side | BUY or SELL |
| ExecType | NEW, FILL, PARTIAL_FILL, CANCELLED, REJECTED |
| LastQty | Shares in this execution |
| LastPx | Price of this execution |
| CumQty | Cumulative filled quantity |
| AvgPx | Average fill price |

#### Statistics Dashboard
At-a-glance metrics displayed in cards at the top of the interface:

| Metric | Description |
|--------|-------------|
| Total Orders | All orders submitted in session |
| Filled | Completely filled orders |
| Partial | Partially filled orders |
| Working | Active orders in the market |
| Cancelled | Cancelled orders |
| Rejected | Rejected orders |

### Visual Indicators
Color-coded rows for quick status recognition:

| Color | Meaning |
|-------|---------|
| Green | BUY side or FILLED status |
| Red | SELL side or REJECTED status |
| Yellow | PARTIAL_FILL status |
| Default | Other statuses |

### Auto-Refresh
- Orders and executions automatically refresh every 2 seconds
- Configurable via `REFRESH_MS` constant in `app.py`
- No manual refresh needed

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      FIX Trading UI                             │
│                    http://localhost:8050                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Order Entry Drawer                    │   │
│  │  ┌─────────┐ ┌─────────────────┐ ┌─────────────────────┐ │   │
│  │  │ Symbol  │ │ Quantity Buttons│ │ Order Type Selector │ │   │
│  │  │  Input  │ │ 100|500|1K|5K   │ │   MARKET | LIMIT    │ │   │
│  │  └─────────┘ └─────────────────┘ └─────────────────────┘ │   │
│  │  ┌─────────────────┐  ┌──────────┐  ┌──────────┐         │   │
│  │  │   Price Input   │  │   BUY    │  │   SELL   │         │   │
│  │  │ (Limit orders)  │  │  Button  │  │  Button  │         │   │
│  │  └─────────────────┘  └──────────┘  └──────────┘         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Statistics Cards Row                        │   │
│  │  [Total] [Filled] [Partial] [Working] [Cancelled] [Rej]  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Orders Blotter                         │   │
│  │  Timestamp | ClOrdId | Symbol | Side | ... | Actions (⋮) 
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 Executions Blotter                       │   │
│  │  ExecId | ClOrdId | Symbol | Side | ExecType | LastQty...│   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ REST API (HTTP)
                              ▼
                    ┌─────────────────┐
                    │   FIX Client    │
                    │  (Spring Boot)  │
                    │  localhost:8081 │
                    └─────────────────┘
```

## Prerequisites

- Python 3.8+
- Running FIX Client (Spring Boot app on port 8081)
- Running FIX Exchange Simulator (on port 9876)

## Installation

```bash
cd fix-trading-ui
pip install -r requirements.txt
```

### Dependencies

Key Python packages used:
- `dash` - Web framework
- `dash-mantine-components` - UI component library
- `dash-iconify` - Icons
- `requests` - HTTP client for REST API calls
- `pandas` - Data manipulation

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

## API Endpoints Used

The Trading UI communicates with the FIX Client via these REST endpoints:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/orders` | Fetch all orders |
| `POST` | `/api/orders` | Submit new order |
| `PUT` | `/api/orders/{clOrdId}` | Amend order (quantity/price) |
| `DELETE` | `/api/orders/{clOrdId}?symbol=X&side=Y` | Cancel order |
| `GET` | `/api/executions` | Fetch all executions |
| `GET` | `/api/sessions` | Check FIX session status |

### Request/Response Examples

**Submit Order:**
```bash
curl -X POST http://localhost:8081/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "BUY",
    "orderType": "LIMIT",
    "quantity": 100,
    "price": 150.00
  }'
```

**Amend Order:**
```bash
curl -X PUT http://localhost:8081/api/orders/ABC123 \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "side": "BUY",
    "newQuantity": 150,
    "newPrice": 148.00
  }'
```

**Cancel Order:**
```bash
curl -X DELETE "http://localhost:8081/api/orders/ABC123?symbol=AAPL&side=BUY"
```

## Usage

### Submitting Orders

1. Click the order entry button to open the drawer
2. Enter a symbol (e.g., AAPL)
3. Select quantity using quick buttons or enter manually
4. Select order type (Market or Limit)
5. If Limit, enter price
6. Click **BUY** (green) or **SELL** (red)

### Amending Orders

1. Find the order in the Orders Blotter
2. Click the ⋮ (actions) button on that row
3. Select "Amend" from the menu
4. In the modal dialog, enter new quantity and/or price
5. Click "Confirm Amendment"

### Cancelling Orders

**Option 1 - Via Actions Menu:**
1. Find the order in the Orders Blotter
2. Click the ⋮ (actions) button
3. Select "Cancel"
4. Confirm the cancellation

**Option 2 - Click to Select:**
1. Click on an order row to select it
2. Click the "Cancel Selected" button
3. Confirm the cancellation

## Configuration

Edit `app.py` to customize:

```python
# API endpoint
API_BASE_URL = "http://localhost:8081/api"

# Refresh interval (milliseconds)
REFRESH_MS = 2000  # 2 seconds

# Dashboard port
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIX_CLIENT_URL` | FIX Client API base URL | `http://localhost:8081` |

## Order Statuses

| Status | Description |
|--------|-------------|
| `PENDING` | Order sent, awaiting acknowledgment |
| `NEW` | Order accepted by exchange |
| `PARTIALLY_FILLED` | Order partially executed |
| `FILLED` | Order completely executed |
| `CANCELLED` | Order cancelled |
| `REJECTED` | Order rejected by exchange |

## Troubleshooting

### "Cannot connect to FIX Client API"
- Make sure the Spring Boot FIX Client is running on port 8081
- Check: `curl http://localhost:8081/api/health`

### "Connection Status: Disconnected"
- Make sure the Exchange Simulator is running on port 9876
- Check that SenderCompID/TargetCompID match in both configs
- Verify FIX session: `curl http://localhost:8081/api/sessions`

### Orders Not Filling
- Check exchange has liquidity: `curl http://localhost:8080/api/exchange/orderbook/AAPL`
- Ensure liquidity provider is enabled on exchange
- For limit orders, verify price crosses the spread

### Orders Blotter Not Updating
- Check browser console for JavaScript errors
- Verify API is responding: `curl http://localhost:8081/api/orders`
- Try refreshing the page

### Amendment/Cancel Not Working
- Ensure order is in a modifiable state (NEW or PARTIALLY_FILLED)
- Check that symbol and side match the original order
- View FIX Client logs for rejection reasons

## Technology Stack

| Technology | Purpose |
|------------|---------|
| Python Dash | Web application framework |
| Dash Mantine Components | Modern UI components |
| Dash DataTable | Interactive data tables |
| Dash Iconify | Icon library |
| Requests | HTTP client |
| Pandas | Data manipulation |
