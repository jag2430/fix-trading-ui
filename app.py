"""
FIX OEMS - Order & Execution Management System
Professional Trading Dashboard (Dash Mantine Components, compatible with dmc==0.14.7)
"""

import json
import os
import threading
import time
from datetime import datetime

import redis
import requests
from dash import Dash, dcc, html, Input, Output, State, callback, dash_table, ctx
from dash import _dash_renderer

_dash_renderer._set_react_version("18.2.0")

import dash_mantine_components as dmc

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = os.getenv("FIX_CLIENT_URL", "http://localhost:8081") + "/api"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REFRESH_MS = int(os.getenv("REFRESH_MS", "500"))
NOTIFICATION_TIMEOUT_SECONDS = 4
NOTIFICATION_CHECK_INTERVAL_MS = 1000

# Redis channels (must match what FIX Client publishes to)
REDIS_CHANNELS = {
    "orders": "orders:updates",
    "executions": "executions:updates",
}

external_stylesheets = [
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"
]

app = Dash(
    __name__,
    external_stylesheets=external_stylesheets,
    title="FIX OEMS - Trading Dashboard",
    suppress_callback_exceptions=True,
)


# =============================================================================
# Shared State (in-memory, updated by Redis subscriber)
# =============================================================================

class SharedState:
    """Thread-safe shared state updated by Redis subscriber."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.orders = {}  # keyed by clOrdId for easy updates
        self.executions = []
        self.redis_connected = False
    
    def update_orders(self, orders_list):
        """Replace all orders (used for initial load)."""
        with self._lock:
            self.orders = {o.get("clOrdId"): o for o in orders_list if o.get("clOrdId")}
    
    def update_order(self, order_data):
        """Update a single order by clOrdId (used for Redis updates)."""
        with self._lock:
            cl_ord_id = order_data.get("clOrdId")
            if cl_ord_id:
                self.orders[cl_ord_id] = order_data
                print(f"[Redis] Order updated: {cl_ord_id} -> {order_data.get('status')}")
    
    def add_execution(self, exec_data):
        """Add an execution to the front of the list."""
        with self._lock:
            exec_id = exec_data.get("execId")
            if exec_id:
                self.executions = [e for e in self.executions if e.get("execId") != exec_id]
            self.executions.insert(0, exec_data)
            self.executions = self.executions[:100]
            print(f"[Redis] Execution added: {exec_data.get('execType')} {exec_data.get('symbol')}")
    
    def set_executions(self, execs_list):
        """Replace all executions (used for initial load)."""
        with self._lock:
            self.executions = list(execs_list)
    
    def set_redis_connected(self, connected: bool):
        """Track Redis connection status."""
        with self._lock:
            self.redis_connected = connected
    
    def get_orders(self):
        """Get all orders as a list."""
        with self._lock:
            return list(self.orders.values())
    
    def get_executions(self):
        """Get all executions."""
        with self._lock:
            return list(self.executions)
    
    def is_redis_connected(self):
        """Check if Redis is connected."""
        with self._lock:
            return self.redis_connected


# Global shared state
state = SharedState()


# =============================================================================
# Redis Subscriber (background thread)
# =============================================================================

class RedisSubscriber(threading.Thread):
    """Background thread that subscribes to Redis and updates shared state."""
    
    def __init__(self, shared_state: SharedState):
        super().__init__(daemon=True)
        self.state = shared_state
        self.running = True
        self.pubsub = None
    
    def run(self):
        retry_delay = 1
        max_retry_delay = 30
        
        while self.running:
            try:
                redis_client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                redis_client.ping()
                self.state.set_redis_connected(True)
                print(f"[Redis] Connected to {REDIS_HOST}:{REDIS_PORT}")
                retry_delay = 1
                
                self.pubsub = redis_client.pubsub()
                self.pubsub.subscribe(
                    REDIS_CHANNELS["orders"],
                    REDIS_CHANNELS["executions"],
                )
                print(f"[Redis] Subscribed to: {list(REDIS_CHANNELS.values())}")
                
                # Use get_message with timeout instead of listen() 
                # This is more reliable and matches portfolio-blotter's approach
                while self.running:
                    message = self.pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        self._handle_message(message)
                        
            except redis.ConnectionError as e:
                self.state.set_redis_connected(False)
                print(f"[Redis] Connection error: {e}, retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
            except Exception as e:
                self.state.set_redis_connected(False)
                print(f"[Redis] Error: {e}, retrying in {retry_delay}s...")
                import traceback
                traceback.print_exc()
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
    
    def _handle_message(self, message):
        try:
            channel = message["channel"]
            data = message["data"]
            
            # Debug: log raw message
            print(f"[Redis] Received on {channel}: {data[:200] if len(str(data)) > 200 else data}")
            
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            payload = json.loads(data)
            
            # Handle double-encoded JSON (FIX Client encodes twice)
            if isinstance(payload, str):
                print(f"[Redis] Detected double-encoded JSON, parsing again...")
                payload = json.loads(payload)
            
            # Debug: log parsed payload
            print(f"[Redis] Parsed payload type: {type(payload)}, keys: {payload.keys() if isinstance(payload, dict) else 'N/A'}")
            
            # Handle different payload formats
            if isinstance(payload, dict):
                if "type" in payload and "data" in payload:
                    msg_type = payload.get("type")
                    msg_data = payload.get("data", {})
                    print(f"[Redis] Message type: {msg_type}")
                else:
                    msg_type = "DIRECT"
                    msg_data = payload
                    print(f"[Redis] Direct payload (no type/data wrapper)")
            else:
                print(f"[Redis] Unexpected payload format: {type(payload)}")
                return
            
            if channel == REDIS_CHANNELS["orders"]:
                if isinstance(msg_data, dict) and msg_data:
                    print(f"[Redis] Updating order: {msg_data.get('clOrdId')} -> {msg_data.get('status')}")
                    self.state.update_order(msg_data)
            elif channel == REDIS_CHANNELS["executions"]:
                if isinstance(msg_data, dict) and msg_data:
                    print(f"[Redis] Adding execution: {msg_data.get('execId')} {msg_data.get('execType')}")
                    self.state.add_execution(msg_data)
                
        except json.JSONDecodeError as e:
            print(f"[Redis] Failed to parse message: {e}")
            print(f"[Redis] Raw data was: {data[:500] if data else 'None'}")
        except Exception as e:
            print(f"[Redis] Error handling message: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        self.running = False

# =============================================================================
# Helpers
# =============================================================================

def safe_get_json(url: str, timeout: int = 2):
    """Safely fetch JSON from a URL with proper error logging."""
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[WARN] API returned status {r.status_code} for {url}")
    except requests.exceptions.Timeout:
        print(f"[WARN] Timeout fetching {url}")
    except requests.exceptions.ConnectionError:
        print(f"[WARN] Connection error fetching {url}")
    except json.JSONDecodeError as e:
        print(f"[WARN] JSON decode error for {url}: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected error fetching {url}: {e}")
    return None


def search_symbols(query: str, timeout: int = 2):
    """Search for symbols using the FIX Client API."""
    if not query or len(query.strip()) < 1:
        return []
    try:
        r = requests.get(
            f"{API_BASE_URL}/symbols/search",
            params={"q": query.strip()},
            timeout=timeout
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("results", [])
        else:
            print(f"[WARN] Symbol search returned status {r.status_code} for query '{query}'")
    except requests.exceptions.Timeout:
        print(f"[WARN] Symbol search timeout for query '{query}'")
    except requests.exceptions.ConnectionError:
        print(f"[WARN] Symbol search connection error for query '{query}'")
    except Exception as e:
        print(f"[ERROR] Symbol search error for query '{query}': {e}")
    return None


def validate_symbol(symbol: str, timeout: int = 2):
    """Validate a symbol using the FIX Client API."""
    if not symbol:
        return None
    try:
        r = requests.get(
            f"{API_BASE_URL}/symbols/{symbol.strip().upper()}/validate",
            timeout=timeout
        )
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[WARN] Symbol validation returned status {r.status_code} for '{symbol}'")
    except requests.exceptions.Timeout:
        print(f"[WARN] Symbol validation timeout for '{symbol}'")
    except requests.exceptions.ConnectionError:
        print(f"[WARN] Symbol validation connection error for '{symbol}'")
    except Exception as e:
        print(f"[ERROR] Symbol validation error for '{symbol}': {e}")
    return None


def send_order_to_api(symbol: str, side: str, order_type: str, quantity: int, price: float = None):
    """
    Send order to FIX Client API.
    
    Returns:
        tuple: (success: bool, result: dict if success else error_message: str)
    """
    payload = {
        "symbol": symbol.upper(),
        "side": side,
        "orderType": order_type,
        "quantity": quantity,
    }
    if order_type == "LIMIT" and price is not None:
        payload["price"] = price

    try:
        r = requests.post(f"{API_BASE_URL}/orders", json=payload, timeout=5)
        if r.status_code == 200:
            return True, r.json()
        else:
            error_detail = ""
            try:
                error_json = r.json()
                error_detail = error_json.get("message") or error_json.get("error", "")
            except (json.JSONDecodeError, ValueError):
                error_detail = r.text[:100] if r.text else f"HTTP {r.status_code}"
            return False, error_detail or f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "Request timed out - check connection"
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to FIX Client - is it running?"
    except Exception as e:
        return False, str(e)


def send_cancel_to_api(cl_ord_id: str, symbol: str, side: str):
    """
    Send cancel request to FIX Client API.
    
    Returns:
        tuple: (success: bool, result: dict if success else error_message: str)
    """
    try:
        r = requests.delete(
            f"{API_BASE_URL}/orders/{cl_ord_id}",
            params={"symbol": symbol, "side": side},
            timeout=5,
        )
        if r.status_code == 200:
            return True, r.json()
        else:
            error_detail = ""
            try:
                error_json = r.json()
                error_detail = error_json.get("message") or error_json.get("error", "")
            except (json.JSONDecodeError, ValueError):
                error_detail = r.text[:100] if r.text else f"HTTP {r.status_code}"
            return False, error_detail or f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "Cancel request timed out"
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to FIX Client"
    except Exception as e:
        return False, str(e)


def send_amend_to_api(cl_ord_id: str, symbol: str, side: str, new_qty: int = None, new_price: float = None):
    """
    Send amend request to FIX Client API.
    
    Returns:
        tuple: (success: bool, result: dict if success else error_message: str)
    """
    payload = {"symbol": symbol, "side": side}
    if new_qty is not None:
        payload["newQuantity"] = int(new_qty)
    if new_price is not None:
        payload["newPrice"] = float(new_price)

    try:
        r = requests.put(f"{API_BASE_URL}/orders/{cl_ord_id}", json=payload, timeout=5)
        if r.status_code == 200:
            return True, r.json()
        else:
            error_detail = ""
            try:
                error_json = r.json()
                error_detail = error_json.get("message") or error_json.get("error", "")
            except (json.JSONDecodeError, ValueError):
                error_detail = r.text[:100] if r.text else f"HTTP {r.status_code}"
            return False, error_detail or f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "Amend request timed out"
    except requests.exceptions.ConnectionError:
        return False, "Cannot connect to FIX Client"
    except Exception as e:
        return False, str(e)


def format_time(ts):
    """Format timestamp for display."""
    if not ts:
        return ""
    if isinstance(ts, str):
        return ts[11:19] if len(ts) >= 19 else ts
    return str(ts)


def format_price(v):
    """Format price for display. Returns 'MKT' for market orders."""
    if v is None:
        return "MKT"
    try:
        fv = float(v)
        if fv <= 0:
            return "MKT"
        return f"${fv:.2f}"
    except (TypeError, ValueError):
        return "MKT"


def normalize_orders_for_table(orders):
    """Normalize order data for display in the orders blotter."""
    # Statuses that are considered "open" and can be acted upon
    OPEN_STATUSES = {
        "NEW", "PENDING", "PARTIALLY_FILLED", "PENDING_REPLACE",
        "PENDING_NEW", "PENDING_CANCEL"
    }

    out = []
    for o in orders or []:
        row = dict(o)
        row["timestamp"] = format_time(row.get("timestamp"))
        row["price"] = format_price(row.get("price"))
        row["filledQuantity"] = row.get("filledQuantity") or 0
        row["leavesQuantity"] = row.get("leavesQuantity")
        if row["leavesQuantity"] is None:
            row["leavesQuantity"] = row.get("quantity", 0)

        # Add actions column - show clickable dots for open orders only
        status = (row.get("status") or "").upper()
        if status in OPEN_STATUSES:
            row["actions"] = "⋮"  # Vertical ellipsis (three dots)
        else:
            row["actions"] = ""  # No actions for closed orders

        out.append(row)
    return out


def normalize_execs_for_table(execs):
    """Normalize execution data for display in the executions blotter."""
    out = []
    for e in execs or []:
        row = dict(e)
        row["timestamp"] = format_time(row.get("timestamp"))

        lp = row.get("lastPrice")
        ap = row.get("avgPrice")

        try:
            row["lastPrice"] = f"${float(lp):.2f}" if lp and float(lp) > 0 else "-"
        except (TypeError, ValueError):
            row["lastPrice"] = "-"

        try:
            row["avgPrice"] = f"${float(ap):.2f}" if ap and float(ap) > 0 else "-"
        except (TypeError, ValueError):
            row["avgPrice"] = "-"

        out.append(row)
    return out


def mk_stat_card(title: str, value_id: str, color=None):
    """Create a statistics card for the dashboard header."""
    # Mantine expects a string color; guard against objects/dicts accidentally passed in
    if isinstance(color, (dict, list)):
        color = None

    text_kwargs = {"size": "xl", "fw": 900, "mt": 4, "id": value_id}
    if isinstance(color, str) and color.strip():
        text_kwargs["c"] = color

    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Text(title, size="xs", c="dimmed", tt="uppercase", fw=700),
            dmc.Text("0", **text_kwargs),
        ],
    )


# =============================================================================
# UI Blocks
# =============================================================================

def main_navbar():
    """Main navigation bar with trading button."""
    return dmc.Paper(
        p="md",
        radius=0,
        withBorder=True,
        style={"borderTop": "none", "borderLeft": "none", "borderRight": "none"},
        children=dmc.Group(
            justify="space-between",
            align="center",
            children=[
                # Left side: Logo
                dmc.Group(
                    gap="sm",
                    align="center",
                    children=[
                        html.I(className="fa-solid fa-chart-line", style={"fontSize": "18px"}),
                        dmc.Text("FIX OEMS", fw=900, size="lg"),
                        dmc.Text("Trading Dashboard", c="dimmed", size="sm"),
                    ],
                ),

                # Center: Trade Button
                dmc.Group(
                    gap="sm",
                    align="center",
                    children=[
                        dmc.Button(
                            "Trade",
                            id="trading-btn",
                            leftSection=html.I(className="fa-solid fa-arrow-right-arrow-left"),
                            variant="light",
                            color="blue",
                            style={"marginLeft": "45px"},
                        ),
                    ],
                ),

                # Right side: Status and time
                dmc.Group(
                    gap="md",
                    align="center",
                    children=[
                        dmc.Tooltip(
                            label="Redis Pub/Sub Status",
                            children=dmc.Badge(
                                "REDIS",
                                id="redis-badge",
                                color="gray",
                                variant="outline",
                                radius="sm",
                                size="sm",
                            ),
                        ),
                        dmc.Badge(
                            "DISCONNECTED",
                            id="connection-badge",
                            color="red",
                            variant="filled",
                            radius="sm"
                        ),
                        dmc.Text(id="header-time", size="sm", c="dimmed"),
                    ],
                ),
            ],
        ),
    )


def trading_drawer():
    """Drawer/sidebar that contains the order entry panel."""
    return dmc.Drawer(
        id="trading-drawer",
        title=dmc.Group(
            gap="xs",
            children=[
                html.I(className="fa-solid fa-arrow-right-arrow-left", style={"fontSize": "18px"}),
                dmc.Text("Quick Trade", fw=700, size="lg"),
            ],
        ),
        padding="md",
        zIndex=10000,
        size="400px",
        children=[
            dmc.Paper(
                p="md",
                radius="md",
                withBorder=True,
                children=[
                    dmc.Group(
                        gap="xs",
                        align="center",
                        children=[
                            html.I(className="fa-solid fa-bolt"),
                            dmc.Text("Quick Order", fw=700),
                        ],
                    ),
                    dmc.Space(h=15),

                    # Symbol input with autocomplete
                    dmc.Select(
                        id="drawer-symbol-input",
                        label="Symbol",
                        placeholder="Search symbol (e.g. AAPL, TSLA)",
                        searchable=True,
                        clearable=True,
                        allowDeselect=False,
                        nothingFoundMessage="No symbols found - type to search",
                        data=[],
                        value=None,
                        styles={
                            "input": {"textTransform": "uppercase", "fontWeight": 800},
                        },
                        comboboxProps={"withinPortal": False, "zIndex": 20000},
                        leftSection=html.I(
                            className="fa-solid fa-magnifying-glass",
                            style={"fontSize": "12px"}
                        ),
                    ),
                    # Hidden store to track the selected symbol separately
                    dcc.Store(id="selected-symbol-store", data=None),

                    # Company name and validation display
                    html.Div(
                        id="drawer-symbol-info",
                        children=[],
                        style={"minHeight": "24px", "marginTop": "4px"},
                    ),

                    # Quick quantity buttons
                    dmc.Group(
                        justify="center",
                        mt="sm",
                        children=[
                            dmc.Text("Quick Qty:", size="sm", c="dimmed"),
                            dmc.Group(
                                gap="xs",
                                children=[
                                    dmc.Button("100", id="qty-100", size="xs", variant="light"),
                                    dmc.Button("500", id="qty-500", size="xs", variant="light"),
                                    dmc.Button("1000", id="qty-1000", size="xs", variant="light"),
                                    dmc.Button("5000", id="qty-5000", size="xs", variant="light"),
                                ],
                            ),
                        ],
                    ),

                    # Order Type selector
                    dmc.Select(
                        id="drawer-order-type-select",
                        label="Order Type",
                        data=[
                            {"value": "MARKET", "label": "MARKET"},
                            {"value": "LIMIT", "label": "LIMIT"},
                        ],
                        comboboxProps={"withinPortal": False, "zIndex": 20000},
                        value="LIMIT",
                        mt="sm",
                    ),

                    # Quantity input
                    dmc.NumberInput(
                        id="drawer-quantity-input",
                        label="Quantity",
                        placeholder="Shares",
                        min=1,
                        step=1,
                        value=None,
                        allowDecimal=False,
                        mt="sm",
                    ),

                    # Price inputs - shown/hidden based on order type
                    html.Div(
                        id="drawer-price-section",
                        children=[
                            dmc.Group(
                                grow=True,
                                mt="sm",
                                children=[
                                    dmc.NumberInput(
                                        id="drawer-price-input",
                                        label="Limit Price",
                                        placeholder="0.00",
                                        min=0,
                                        step=0.01,
                                        decimalScale=2,
                                        fixedDecimalScale=True,
                                        style={"flex": 1},
                                    ),
                                    dmc.NumberInput(
                                        id="drawer-stop-price-input",
                                        label="Stop Price",
                                        placeholder="0.00",
                                        min=0,
                                        step=0.01,
                                        decimalScale=2,
                                        fixedDecimalScale=True,
                                        style={"flex": 1, "display": "none"},
                                    ),
                                ],
                            ),
                        ],
                    ),

                    # Buy/Sell buttons
                    dmc.Group(
                        grow=True,
                        mt="xl",
                        children=[
                            dmc.Button(
                                "BUY",
                                id="drawer-buy-btn",
                                color="green",
                                variant="filled",
                                leftSection=html.I(className="fa-solid fa-arrow-up"),
                                style={"height": "50px", "fontSize": "16px"},
                            ),
                            dmc.Button(
                                "SELL",
                                id="drawer-sell-btn",
                                color="red",
                                variant="filled",
                                leftSection=html.I(className="fa-solid fa-arrow-down"),
                                style={"height": "50px", "fontSize": "16px"},
                            ),
                        ],
                    ),

                    dmc.Space(h=10),
                    html.Div(id="drawer-order-status-msg"),
                ],
            ),
        ],
    )


def stats_row():
    """Create the statistics cards row."""
    return dmc.SimpleGrid(
        cols=6,
        spacing="md",
        children=[
            mk_stat_card("Total Orders", "stat-orders"),
            mk_stat_card("Filled", "stat-filled", color="green"),
            mk_stat_card("Partial", "stat-partial", color="yellow"),
            mk_stat_card("Working", "stat-open", color="blue"),
            mk_stat_card("Cancelled", "stat-cancelled", color="gray"),
            mk_stat_card("Rejected", "stat-rejected", color="red"),
        ],
    )


def orders_blotter():
    """Create the orders blotter table."""
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                children=[
                    dmc.Group(
                        gap="xs",
                        children=[
                            html.I(className="fa-solid fa-list"),
                            dmc.Text("Orders Blotter", fw=800)
                        ]
                    ),
                    dmc.SegmentedControl(
                        id="orders-filter",
                        value="all",
                        data=[
                            {"value": "all", "label": "All"},
                            {"value": "working", "label": "Working"},
                            {"value": "filled", "label": "Filled"},
                        ],
                    ),
                ],
            ),
            dmc.Space(h=10),
            dash_table.DataTable(
                id="orders-blotter",
                columns=[
                    {"name": "Time", "id": "timestamp"},
                    {"name": "ClOrdId", "id": "clOrdId"},
                    {"name": "Symbol", "id": "symbol"},
                    {"name": "Side", "id": "side"},
                    {"name": "Type", "id": "orderType"},
                    {"name": "Qty", "id": "quantity"},
                    {"name": "Price", "id": "price"},
                    {"name": "Filled", "id": "filledQuantity"},
                    {"name": "Remaining", "id": "leavesQuantity"},
                    {"name": "Status", "id": "status"},
                    {"name": "⚙", "id": "actions"},
                ],
                data=[],
                page_size=10,
                sort_action="native",
                sort_by=[{"column_id": "timestamp", "direction": "desc"}],
                style_table={"overflowX": "auto"},
                style_cell={
                    "padding": "10px 12px",
                    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                    "fontSize": "12px",
                    "border": "1px solid rgba(255,255,255,0.06)",
                    "backgroundColor": "transparent",
                    "color": "white",
                    "textAlign": "left",
                },
                style_header={
                    "fontWeight": "800",
                    "textTransform": "uppercase",
                    "fontSize": "10px",
                    "letterSpacing": "0.6px",
                    "border": "1px solid rgba(255,255,255,0.08)",
                    "backgroundColor": "rgba(255,255,255,0.04)",
                    "color": "rgba(255,255,255,0.75)",
                },
                css=[
                    {
                        "selector": "thead",
                        "rule": "background-color: rgba(255,255,255,0.04) !important;",
                    },
                    {
                        "selector": "thead tr, thead th, thead td",
                        "rule": "background-color: rgba(255,255,255,0.04) !important; background: rgba(255,255,255,0.04) !important;",
                    },
                    {
                        "selector": "thead tr:hover, thead tr:hover th, thead tr:hover td, thead th:hover, th.dash-header:hover",
                        "rule": "background-color: rgba(255,255,255,0.04) !important; background: rgba(255,255,255,0.04) !important; color: rgba(255,255,255,0.75) !important;",
                    },
                    {
                        "selector": ".dash-header, .dash-header--sort",
                        "rule": "background-color: rgba(255,255,255,0.04) !important;",
                    },
                    {
                        "selector": ".dash-header:hover, .dash-header--sort:hover",
                        "rule": "background-color: rgba(255,255,255,0.04) !important;; background: rgba(255,255,255,0.04) !important;",
                    },
                ],
                style_cell_conditional=[
                    {
                        "if": {"column_id": "actions"},
                        "textAlign": "center",
                        "width": "50px",
                        "minWidth": "50px",
                        "maxWidth": "50px",
                        "cursor": "pointer",
                        "fontSize": "18px",
                        "fontWeight": "bold",
                        "color": "#4dabf7",
                    },
                ],
                style_data_conditional=[
                    {"if": {"filter_query": "{side} = BUY"}, "color": "#00d4aa", "fontWeight": "700"},
                    {"if": {"filter_query": "{side} = SELL"}, "color": "#ff6b6b", "fontWeight": "700"},
                    {"if": {"filter_query": "{status} = FILLED"}, "backgroundColor": "rgba(0, 212, 170, 0.10)"},
                    {"if": {"filter_query": "{status} = PARTIALLY_FILLED"}, "backgroundColor": "rgba(255, 217, 61, 0.10)"},
                    {"if": {"filter_query": "{status} = CANCELLED"}, "backgroundColor": "rgba(180, 180, 180, 0.08)"},
                    {"if": {"filter_query": "{status} = REPLACED"}, "backgroundColor": "rgba(77, 171, 247, 0.10)"},
                    {"if": {"filter_query": "{status} = REJECTED"}, "backgroundColor": "rgba(255, 107, 107, 0.12)"},
                    {"if": {"state": "selected"}, "backgroundColor": "rgba(77, 171, 247, 0.25)", "border": "1px solid rgba(77,171,247,0.7)"},
                    {
                        "if": {
                            "column_id": "actions",
                            "filter_query": "{actions} != ''"
                        },
                        "color": "#4dabf7",
                        "fontSize": "20px",
                    },
                ],
            ),
        ],
    )


def order_actions_modal():
    """Modal popup for order actions (Amend/Cancel)."""
    return dmc.Modal(
        id="order-actions-modal",
        title=dmc.Group(
            gap="xs",
            children=[
                html.I(className="fa-solid fa-sliders", style={"fontSize": "16px"}),
                dmc.Text("Order Actions", fw=700),
            ],
        ),
        size="md",
        zIndex=10001,
        children=[
            # Order info display
            dmc.Paper(
                p="sm",
                radius="sm",
                withBorder=True,
                style={"backgroundColor": "rgba(255,255,255,0.03)"},
                children=[
                    dmc.Group(
                        justify="space-between",
                        children=[
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Text("Order ID", size="xs", c="dimmed"),
                                    dmc.Text(id="modal-clordid-display", fw=700, size="sm"),
                                ],
                            ),
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Text("Symbol", size="xs", c="dimmed"),
                                    dmc.Text(id="modal-symbol-display", fw=700, size="sm"),
                                ],
                            ),
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Text("Side", size="xs", c="dimmed"),
                                    dmc.Text(id="modal-side-display", fw=700, size="sm"),
                                ],
                            ),
                            dmc.Stack(
                                gap=2,
                                children=[
                                    dmc.Text("Status", size="xs", c="dimmed"),
                                    dmc.Badge(id="modal-status-display", size="sm"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),

            dmc.Space(h=15),
            dmc.Divider(label="Amend Order", labelPosition="center"),
            dmc.Space(h=10),

            # Amend inputs
            dmc.Group(
                grow=True,
                children=[
                    dmc.NumberInput(
                        id="modal-amend-qty",
                        label="New Quantity",
                        placeholder="Enter new qty",
                        min=1,
                        step=1,
                        allowDecimal=False,
                        leftSection=html.I(className="fa-solid fa-hashtag"),
                    ),
                    dmc.NumberInput(
                        id="modal-amend-price",
                        label="New Price",
                        placeholder="Enter new price",
                        min=0,
                        step=0.01,
                        decimalScale=2,
                        fixedDecimalScale=True,
                        leftSection=html.I(className="fa-solid fa-dollar-sign"),
                    ),
                ],
            ),

            dmc.Space(h=15),

            # Action buttons
            dmc.Group(
                grow=True,
                children=[
                    dmc.Button(
                        "Amend Order",
                        id="modal-amend-btn",
                        color="yellow",
                        variant="filled",
                        leftSection=html.I(className="fa-solid fa-pen"),
                        fullWidth=True,
                    ),
                    dmc.Button(
                        "Cancel Order",
                        id="modal-cancel-btn",
                        color="red",
                        variant="filled",
                        leftSection=html.I(className="fa-solid fa-xmark"),
                        fullWidth=True,
                    ),
                ],
            ),

            dmc.Space(h=10),
            html.Div(id="modal-action-status"),

            # Hidden stores for order data
            dcc.Store(id="modal-order-data"),
        ],
    )


def executions_blotter():
    """Create the executions blotter table."""
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                children=[
                    dmc.Group(
                        gap="xs",
                        children=[
                            html.I(className="fa-solid fa-right-left"),
                            dmc.Text("Execution Reports", fw=800)
                        ]
                    ),
                    dmc.Button(
                        "Clear",
                        id="clear-executions-btn",
                        variant="outline",
                        color="gray",
                        size="sm"
                    ),
                ],
            ),
            dmc.Space(h=10),
            dash_table.DataTable(
                id="executions-blotter",
                columns=[
                    {"name": "Time", "id": "timestamp"},
                    {"name": "ExecId", "id": "execId"},
                    {"name": "ClOrdId", "id": "clOrdId"},
                    {"name": "OrigClOrdId", "id": "origClOrdId"},
                    {"name": "Symbol", "id": "symbol"},
                    {"name": "Side", "id": "side"},
                    {"name": "ExecType", "id": "execType"},
                    {"name": "LastQty", "id": "lastQuantity"},
                    {"name": "LastPx", "id": "lastPrice"},
                    {"name": "CumQty", "id": "cumQuantity"},
                    {"name": "AvgPx", "id": "avgPrice"},
                    {"name": "Status", "id": "orderStatus"},
                ],
                data=[],
                page_size=8,
                sort_action="native",
                sort_by=[{"column_id": "timestamp", "direction": "desc"}],
                style_table={"overflowX": "auto"},
                style_cell={
                    "padding": "8px 10px",
                    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
                    "fontSize": "11px",
                    "border": "1px solid rgba(255,255,255,0.06)",
                    "backgroundColor": "transparent",
                    "color": "white",
                    "textAlign": "left",
                },
                style_header={
                    "fontWeight": "800",
                    "textTransform": "uppercase",
                    "fontSize": "10px",
                    "letterSpacing": "0.6px",
                    "border": "1px solid rgba(255,255,255,0.08)",
                    "backgroundColor": "rgba(255,255,255,0.04)",
                    "color": "rgba(255,255,255,0.75)",
                },
                css=[
                    {
                        "selector": "thead",
                        "rule": "background-color: rgba(255,255,255,0.04) !important;",
                    },
                    {
                        "selector": "thead tr, thead th, thead td",
                        "rule": "background-color: rgba(255,255,255,0.04) !important; background: rgba(255,255,255,0.04) !important;",
                    },
                    {
                        "selector": "thead tr:hover, thead tr:hover th, thead tr:hover td, thead th:hover, th.dash-header:hover",
                        "rule": "background-color: rgba(255,255,255,0.04) !important; background: rgba(255,255,255,0.04) !important; color: rgba(255,255,255,0.75) !important;",
                    },
                    {
                        "selector": ".dash-header, .dash-header--sort",
                        "rule": "background-color: rgba(255,255,255,0.04) !important;",
                    },
                    {
                        "selector": ".dash-header:hover, .dash-header--sort:hover",
                        "rule": "background-color: rgba(255,255,255,0.04) !important; background: rgba(255,255,255,0.04) !important;",
                    },
                ],
                style_data_conditional=[
                    {"if": {"filter_query": "{side} = BUY"}, "color": "#00d4aa", "fontWeight": "700"},
                    {"if": {"filter_query": "{side} = SELL"}, "color": "#ff6b6b", "fontWeight": "700"},
                    {"if": {"filter_query": "{execType} = FILL"}, "backgroundColor": "rgba(0, 212, 170, 0.12)"},
                    {"if": {"filter_query": "{execType} = PARTIAL_FILL"}, "backgroundColor": "rgba(255, 217, 61, 0.12)"},
                    {"if": {"filter_query": "{execType} = CANCELLED"}, "backgroundColor": "rgba(180, 180, 180, 0.10)"},
                    {"if": {"filter_query": "{execType} = REPLACED"}, "backgroundColor": "rgba(77, 171, 247, 0.12)"},
                    {"if": {"filter_query": "{execType} = REJECTED"}, "backgroundColor": "rgba(255, 107, 107, 0.14)"},
                ],
            ),
        ],
    )


def footer_bar():
    """Create the footer bar with session info."""
    return dmc.Paper(
        p="sm",
        radius=0,
        withBorder=True,
        children=dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Text(
                    f"FIX OEMS v1.0 | Redis: {REDIS_HOST}:{REDIS_PORT} | API: {API_BASE_URL.replace('/api', '')}",
                    size="xs",
                    c="dimmed"
                ),
                dmc.Text(id="footer-session-info", size="xs", c="dimmed"),
            ],
        ),
    )


# =============================================================================
# Layout
# =============================================================================

app.layout = dmc.MantineProvider(
    forceColorScheme="dark",
    theme={
        "primaryColor": "blue",
        "defaultRadius": "md",
        "fontFamily": "Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
    },
    children=[
        dcc.Interval(id="refresh-interval", interval=REFRESH_MS, n_intervals=0),

        # Interval for notification timeout
        dcc.Interval(
            id="notification-interval",
            interval=NOTIFICATION_CHECK_INTERVAL_MS,
            n_intervals=0
        ),

        # Store for order submission timestamp (to auto-dismiss after timeout)
        dcc.Store(id="order-submission-timestamp", data=None),

        dcc.Store(id="symbol-search-prev", data=""),

        dcc.Store(id="clicked-outside-table", data=0),

        # Store to track last action cell click
        dcc.Store(id="last-actions-click", data={"row": None, "clOrdId": None, "timestamp": 0}),

        # Store for validated symbol data
        dcc.Store(id="validated-symbol-data", data=None),

        # Trading Drawer (initially hidden)
        trading_drawer(),

        # Order Actions Modal (for amend/cancel from blotter)
        order_actions_modal(),

        # Main wrapper
        html.Div(
            id="main-click-wrapper",
            n_clicks=0,
            className="",
            children=[
                dmc.Stack(
                    gap=0,
                    children=[
                        main_navbar(),
                        dmc.Container(
                            fluid=True,
                            p="md",
                            children=dmc.Stack(
                                gap="md",
                                children=[
                                    stats_row(),
                                    html.Div(id="orders-blotter-wrapper", children=[orders_blotter()]),
                                    html.Div(id="executions-blotter-wrapper", children=[executions_blotter()]),
                                ],
                            ),
                        ),
                        footer_bar(),
                    ],
                ),
            ],
            style={"minHeight": "100vh"},
        ),
    ],
)


# =============================================================================
# Clientside Callback for Click-Outside Deselection
# =============================================================================

app.clientside_callback(
    """
    function(n) {
        // Namespace our globals to avoid polluting window
        window._fixTradingUI = window._fixTradingUI || {
            outsideClicks: 0,
            outsideClicksLastSent: 0,
            listenerAdded: false
        };
        
        var state = window._fixTradingUI;
        
        if (!state.listenerAdded) {
            state.listenerAdded = true;

            // Inject CSS for hiding selection
            var style = document.createElement('style');
            style.id = 'fix-trading-ui-table-styles';
            style.textContent = `
              .tables-deselected .dash-spreadsheet-container td.cell--selected,
              .tables-deselected .dash-spreadsheet-container td.focused,
              .tables-deselected .dash-spreadsheet-container td[tabindex="0"],
              .tables-deselected .dash-spreadsheet-container td[aria-selected="true"],
              .tables-deselected .dash-spreadsheet-container td:focus,
              .tables-deselected .dash-spreadsheet-container td:focus-within {
                  background-color: transparent !important;
                  border: 1px solid rgba(255,255,255,0.06) !important;
                  box-shadow: none !important;
                  outline: none !important;
              }

              .tables-deselected .dash-spreadsheet-container td > div:focus,
              .tables-deselected .dash-spreadsheet-container td:focus > div,
              .tables-deselected .dash-spreadsheet-container td:focus-within > div {
                  outline: none !important;
                  box-shadow: none !important;
              }

              .tables-deselected .dash-spreadsheet-container td {
                  transition:
                    background-color 10ms linear,
                    border-color 10ms linear,
                    box-shadow 10ms linear;
              }

              th.dash-header,
              th.dash-header:hover,
              th.dash-header *,
              th.dash-header:hover *,
              th.dash-header > div,
              th.dash-header > div:hover,
              th.dash-header > div > div,
              th.dash-header > div > div:hover,
              th.dash-header .column-actions,
              th.dash-header .column-actions:hover,
              th.dash-header .column-header--sort,
              th.dash-header .column-header--sort:hover,
              th.dash-header .column-header-name,
              th.dash-header .column-header-name:hover {
                  background: transparent !important;
                  background-color: transparent !important;
              }

              th.dash-header,
              th.dash-header:hover {
                  background: rgba(255,255,255,0.04) !important;
                  background-color: rgba(255,255,255,0.04) !important;
              }

              /* Target the row containing headers */
              tbody tr:has(th.dash-header),
              tbody tr:has(th.dash-header):hover {
                  background: rgba(255,255,255,0.04) !important;
                  background-color: rgba(255,255,255,0.04) !important;
              }
            `;
            document.head.appendChild(style);

            var wrapper = document.getElementById('main-click-wrapper');

            document.addEventListener('mousedown', function(e) {
                var clickedInsideModal = !!e.target.closest('.mantine-Modal-root, [role="dialog"]');
                var clickedInsideDrawer = !!e.target.closest('.mantine-Drawer-root, .mantine-Drawer-content');
                var clickedInsideMantineDropdown = !!(
                    e.target.closest('.mantine-Select-dropdown, .mantine-Popover-dropdown, .mantine-Combobox-dropdown') ||
                    e.target.closest('.mantine-Select-item, .mantine-Combobox-option') ||
                    e.target.closest('[data-mantine-portal]') ||
                    e.target.closest('[role="listbox"], [role="option"]')
                );

                var clickedInsideOverlay = clickedInsideModal || clickedInsideDrawer || clickedInsideMantineDropdown;
                var clickedInsideAnyTable = !!(
                    e.target.closest('.dash-spreadsheet-container') ||
                    e.target.closest('.dash-table-container')
                );

                if (wrapper) {
                    if (clickedInsideAnyTable || clickedInsideOverlay) {
                        wrapper.classList.remove('tables-deselected');
                        if (clickedInsideAnyTable) wrapper.click();
                    } else {
                        wrapper.classList.add('tables-deselected');
                        state.outsideClicks++;

                        if (document.activeElement && document.activeElement.blur) {
                            document.activeElement.blur();
                        }
                        
                        document.querySelectorAll('.dash-spreadsheet-container td.cell--selected')
                            .forEach(function(td) { td.classList.remove('cell--selected'); });
                        document.querySelectorAll('.dash-spreadsheet-container td.focused')
                            .forEach(function(td) { td.classList.remove('focused'); });
                    }
                }
            });
        }
        
        if (state.outsideClicks !== state.outsideClicksLastSent) {
            state.outsideClicksLastSent = state.outsideClicks;
            return state.outsideClicks;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("clicked-outside-table", "data"),
    Input("main-click-wrapper", "n_clicks"),
)


# =============================================================================
# Callbacks
# =============================================================================

@callback(
    Output("orders-blotter", "active_cell", allow_duplicate=True),
    Input("clicked-outside-table", "data"),
    prevent_initial_call=True,
)
def clear_orders_active_cell(_):
    return None


@callback(
    Output("executions-blotter", "active_cell", allow_duplicate=True),
    Input("clicked-outside-table", "data"),
    prevent_initial_call=True,
)
def clear_execs_active_cell(_):
    return None


@callback(
    Output("orders-blotter", "selected_cells", allow_duplicate=True),
    Input("clicked-outside-table", "data"),
    prevent_initial_call=True,
)
def clear_orders_selected_cells(_):
    return []


@callback(
    Output("executions-blotter", "selected_cells", allow_duplicate=True),
    Input("clicked-outside-table", "data"),
    prevent_initial_call=True,
)
def clear_execs_selected_cells(_):
    return []


@callback(
    Output("header-time", "children"),
    Input("refresh-interval", "n_intervals")
)
def update_time(_n):
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@callback(
    Output("connection-badge", "children"),
    Output("connection-badge", "color"),
    Output("redis-badge", "color"),
    Output("footer-session-info", "children"),
    Input("refresh-interval", "n_intervals"),
)
def update_connection_status(_n):
    # Redis status from SharedState
    redis_color = "green" if state.is_redis_connected() else "red"
    
    # Session status still uses HTTP (lightweight call)
    sessions = safe_get_json(f"{API_BASE_URL}/sessions", timeout=2)
    if sessions and len(sessions) > 0 and sessions[0].get("loggedOn"):
        s = sessions[0]
        footer = f"Session: {s.get('senderCompId')} → {s.get('targetCompId')}"
        return "CONNECTED", "green", redis_color, footer
    return "DISCONNECTED", "red", redis_color, "No active session"


@callback(
    Output("stat-orders", "children"),
    Output("stat-filled", "children"),
    Output("stat-partial", "children"),
    Output("stat-open", "children"),
    Output("stat-cancelled", "children"),
    Output("stat-rejected", "children"),
    Input("refresh-interval", "n_intervals"),
)
def update_stats(_n):
    # Read from SharedState (instant, no HTTP call)
    orders = state.get_orders()
    total = len(orders)
    filled = sum(1 for o in orders if (o.get("status") or "").upper() == "FILLED")
    partial = sum(1 for o in orders if (o.get("status") or "").upper() == "PARTIALLY_FILLED")
    working = sum(
        1 for o in orders
        if (o.get("status") or "").upper() in (
            "NEW", "PENDING", "PENDING_REPLACE", "PENDING_NEW", "PENDING_CANCEL", "PARTIALLY_FILLED"
        )
    )
    cancelled = sum(1 for o in orders if (o.get("status") or "").upper() in ("CANCELLED", "REPLACED"))
    rejected = sum(1 for o in orders if (o.get("status") or "").upper() == "REJECTED")
    return str(total), str(filled), str(partial), str(working), str(cancelled), str(rejected)


@callback(
    Output("orders-blotter", "data"),
    Input("refresh-interval", "n_intervals"),
    Input("orders-filter", "value"),
)
def refresh_orders(_n, filter_value):
    # Read from SharedState (instant, no HTTP call)
    orders = state.get_orders()
    fv = (filter_value or "all").lower()

    if fv == "working":
        orders = [
            o for o in orders
            if (o.get("status") or "").upper() in (
                "NEW", "PENDING", "PARTIALLY_FILLED", "PENDING_REPLACE", "PENDING_NEW", "PENDING_CANCEL"
            )
        ]
    elif fv == "filled":
        orders = [o for o in orders if (o.get("status") or "").upper() == "FILLED"]

    return normalize_orders_for_table(orders)


@callback(
    Output("executions-blotter", "data"),
    Input("refresh-interval", "n_intervals")
)
def refresh_executions(_n):
    # Read from SharedState (instant, no HTTP call)
    execs = state.get_executions()
    return normalize_execs_for_table(execs)


@callback(
    Output("executions-blotter", "data", allow_duplicate=True),
    Input("clear-executions-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_executions(_n):
    try:
        requests.delete(f"{API_BASE_URL}/executions", timeout=2)
        state.set_executions([])  # Also clear local state
    except Exception as e:
        print(f"[WARN] Failed to clear executions: {e}")
    return []


# =============================================================================
# Trading Drawer Callbacks
# =============================================================================

@callback(
    Output("trading-drawer", "opened"),
    Input("trading-btn", "n_clicks"),
    State("trading-drawer", "opened"),
    prevent_initial_call=True,
)
def toggle_trading_drawer(n_clicks, opened):
    """Toggle the trading drawer when trading button is clicked."""
    if n_clicks:
        return not opened
    return opened

@callback(
    Output("drawer-symbol-input", "data"),
    Output("selected-symbol-store", "data"),
    Output("symbol-search-prev", "data"),
    Input("drawer-symbol-input", "searchValue"),
    Input("drawer-symbol-input", "value"),
    State("selected-symbol-store", "data"),
    State("drawer-symbol-input", "data"),
    State("symbol-search-prev", "data"),
    prevent_initial_call=True,
)
def update_symbol_options(search_value, selected_value, stored_symbol, current_data, prev_search):
    """
    Update symbol dropdown options based on search query.
    Fetches from the FIX Client /api/symbols/search endpoint.
    """
    import dash
    
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update
    
    # Get the exact property that triggered this callback
    triggered_prop_id = ctx.triggered[0]["prop_id"]
    
    # Use exact match instead of substring to avoid "value" matching "searchValue"
    is_value_trigger = triggered_prop_id == "drawer-symbol-input.value"
    is_search_trigger = triggered_prop_id == "drawer-symbol-input.searchValue"

    # If a value was just selected, store it and preserve the option
    if is_value_trigger:
        if selected_value:
            selected_option = None
            if current_data:
                for opt in current_data:
                    if opt.get("value") == selected_value:
                        selected_option = opt
                        break

            if selected_option:
                return [selected_option], {"symbol": selected_value, "option": selected_option}, prev_search
            else:
                basic_option = {"value": selected_value, "label": selected_value}
                return [basic_option], {"symbol": selected_value, "option": basic_option}, prev_search
        else:
            # Only clear if we previously had a stored symbol
            if stored_symbol:
                return [], None, ""
            else:
                return dash.no_update, dash.no_update, prev_search

    # Handle search trigger
    if is_search_trigger:
        # If search is empty
        sv = (search_value or "").strip()
        prev = (prev_search or "").strip()

        if sv == "":
            # startup / focus bounce: keep whatever is there
            if prev == "":
                return dash.no_update, dash.no_update, prev_search

            # user cleared: force empty options so nothingFoundMessage appears
            return [], None, ""
        
        # We have a search value - perform the search
        results = search_symbols(sv)
        if results is None:
            return dash.no_update, dash.no_update, prev_search  # Don't clear on error
        
        options = []
        seen_values = set()

        for r in results:
            symbol = r.get("symbol", "")
            if symbol in seen_values:
                continue
            seen_values.add(symbol)

            description = r.get("description", "")
            symbol_type = r.get("type", "")

            label = f"{symbol} - {description}" if description else symbol
            if symbol_type and symbol_type != "Common Stock":
                label = f"{label} ({symbol_type})"

            options.append({"value": symbol, "label": label})

        # If we have a stored symbol, make sure it's in the options
        if stored_symbol and stored_symbol.get("symbol"):
            stored_symbol_value = stored_symbol["symbol"]
            if stored_symbol_value not in seen_values:
                stored_option = stored_symbol.get(
                    "option",
                    {"value": stored_symbol_value, "label": stored_symbol_value}
                )
                options.insert(0, stored_option)

        return (options if options else []), dash.no_update, sv

    # Unknown trigger
    return dash.no_update, dash.no_update, prev_search


@callback(
    Output("drawer-symbol-info", "children"),
    Output("validated-symbol-data", "data"),
    Input("drawer-symbol-input", "value"),
    State("validated-symbol-data", "data"),
    prevent_initial_call=True,
)
def validate_and_display_symbol(symbol, previous_validation):
    """Validate selected symbol and display company info."""
    if not symbol:
        return [], None

    validation = validate_symbol(symbol)

    if not validation:
        return [
            dmc.Text(
                "Unable to validate symbol",
                size="xs",
                c="yellow",
                style={"fontStyle": "italic"},
            )
        ], None

    is_valid = validation.get("valid", False)
    company_name = validation.get("name", "")
    current_price = validation.get("currentPrice")
    change = validation.get("change")
    change_percent = validation.get("changePercent")
    validation_msg = validation.get("validationMessage", "")

    if not is_valid:
        return [
            dmc.Group(
                gap="xs",
                children=[
                    html.I(
                        className="fa-solid fa-circle-xmark",
                        style={"color": "#ff6b6b", "fontSize": "12px"}
                    ),
                    dmc.Text(validation_msg or "Invalid symbol", size="xs", c="red"),
                ],
            )
        ], None

    # Build the info display for valid symbols
    info_parts = [
        html.I(
            className="fa-solid fa-circle-check",
            style={"color": "#00d4aa", "fontSize": "12px"}
        )
    ]

    if company_name:
        info_parts.append(
            dmc.Text(
                company_name,
                size="xs",
                c="dimmed",
                fw=500,
                style={
                    "maxWidth": "200px",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                    "whiteSpace": "nowrap"
                },
            )
        )

    if current_price is not None:
        if change is not None and change_percent is not None:
            change_val = float(change)
            change_pct = float(change_percent)
            change_color = "#00d4aa" if change_val >= 0 else "#ff6b6b"
            change_sign = "+" if change_val >= 0 else ""
            price_text = f"${float(current_price):.2f} ({change_sign}{change_val:.2f}, {change_sign}{change_pct:.2f}%)"

            info_parts.append(dmc.Text(price_text, size="xs", c=change_color, fw=600))
        else:
            info_parts.append(
                dmc.Text(f"${float(current_price):.2f}", size="xs", c="blue", fw=600)
            )

    return [dmc.Group(gap="xs", align="center", children=info_parts)], validation


@callback(
    Output("drawer-order-status-msg", "children"),
    Output("drawer-symbol-input", "value"),
    Output("drawer-quantity-input", "value", allow_duplicate=True),
    Output("drawer-price-input", "value"),
    Output("drawer-stop-price-input", "value"),
    Output("order-submission-timestamp", "data"),
    Output("selected-symbol-store", "data", allow_duplicate=True),
    Output("drawer-symbol-info", "children", allow_duplicate=True),
    Input("drawer-buy-btn", "n_clicks"),
    Input("drawer-sell-btn", "n_clicks"),
    State("drawer-symbol-input", "value"),
    State("drawer-quantity-input", "value"),
    State("drawer-price-input", "value"),
    State("drawer-stop-price-input", "value"),
    State("drawer-order-type-select", "value"),
    State("validated-symbol-data", "data"),
    prevent_initial_call=True,
)
def handle_drawer_orders(
    buy_clicks, sell_clicks,
    symbol, quantity, price, stop_price, order_type, validated_data
):
    """Handle order submission from the trading drawer."""
    import dash

    # Helper for returning no-update tuple
    def no_update_all():
        return (
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )

    if not ctx.triggered:
        return no_update_all()

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # Determine side from which button was clicked
    if triggered_id == "drawer-buy-btn":
        side = "BUY"
    elif triggered_id == "drawer-sell-btn":
        side = "SELL"
    else:
        return no_update_all()

    # Validation
    if not symbol:
        return (
            dmc.Alert("Enter a symbol", color="yellow", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )

    # Validate symbol before submission
    if validated_data is None:
        validated_data = validate_symbol(symbol)

    if validated_data is None or not validated_data.get("valid", False):
        error_msg = "Invalid symbol"
        if validated_data and validated_data.get("validationMessage"):
            error_msg = validated_data.get("validationMessage")
        return (
            dmc.Alert(
                f"Cannot submit order: {error_msg}",
                color="red",
                variant="light",
                title="Symbol Validation Failed",
            ),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )

    if not quantity:
        return (
            dmc.Alert("Enter quantity", color="yellow", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )

    order_type = (order_type or "LIMIT").upper()

    if order_type == "LIMIT" and (price is None or price == ""):
        return (
            dmc.Alert("Enter limit price for LIMIT order", color="yellow", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )

    # Send order
    success, result = send_order_to_api(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=int(quantity),
        price=float(price) if order_type == "LIMIT" and price else None
    )

    if success:
        cid = result.get("clOrdId", "")
        current_time = time.time()
        price_info = f" @ ${float(price):.2f}" if order_type == "LIMIT" else ""
        company_name = validated_data.get("name", "")
        symbol_display = f"{symbol} ({company_name})" if company_name else symbol

        alert = dmc.Alert(
            f"✓ {side} {order_type} order sent for {symbol_display}: {cid}{price_info}",
            color="green" if side == "BUY" else "red",
            variant="light",
            title="Order Submitted",
        )

        # Clear fields after successful submit
        return (alert, None, "", "", "", current_time, None, [])
    else:
        return (
            dmc.Alert(f"Order failed: {result}", color="red", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )


@callback(
    Output("drawer-quantity-input", "value"),
    Input("qty-100", "n_clicks"),
    Input("qty-500", "n_clicks"),
    Input("qty-1000", "n_clicks"),
    Input("qty-5000", "n_clicks"),
    State("drawer-quantity-input", "value"),
    prevent_initial_call=True,
)
def set_quick_quantity(qty100, qty500, qty1000, qty5000, current_qty):
    """Set quantity based on quick quantity buttons."""
    import dash

    if not ctx.triggered:
        return dash.no_update

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    qty_map = {
        "qty-100": 100,
        "qty-500": 500,
        "qty-1000": 1000,
        "qty-5000": 5000,
    }

    return qty_map.get(triggered_id, current_qty)


@callback(
    Output("drawer-order-status-msg", "children", allow_duplicate=True),
    Input("notification-interval", "n_intervals"),
    State("order-submission-timestamp", "data"),
    State("drawer-order-status-msg", "children"),
    prevent_initial_call=True,
)
def auto_dismiss_notification(n_intervals, submission_time, current_msg):
    """Auto-dismiss notification after configured timeout."""
    import dash

    if submission_time is None:
        return dash.no_update

    if time.time() - submission_time >= NOTIFICATION_TIMEOUT_SECONDS:
        return ""

    return dash.no_update


@callback(
    Output("drawer-price-input", "style"),
    Output("drawer-price-input", "label"),
    Output("drawer-stop-price-input", "style"),
    Input("drawer-order-type-select", "value"),
)
def update_price_fields_visibility(order_type):
    """Show/hide price fields based on order type."""
    order_type = (order_type or "LIMIT").upper()

    show_style = {"flex": 1}
    hide_style = {"flex": 1, "display": "none"}

    if order_type == "MARKET":
        return hide_style, "Limit Price", hide_style
    elif order_type == "LIMIT":
        return show_style, "Limit Price", hide_style
    elif order_type == "STOP":
        return hide_style, "Limit Price", show_style
    elif order_type == "STOP_LIMIT":
        return show_style, "Limit Price", show_style

    return show_style, "Limit Price", hide_style


# =============================================================================
# Order Actions Modal Callbacks
# =============================================================================

# Clientside callback to detect actions cell click
app.clientside_callback(
    """
    function(active_cell, selected_cells, n_clicks, viewport_data) {
        if (!active_cell || !viewport_data) {
            return window.dash_clientside.no_update;
        }

        if (active_cell.column_id !== 'actions') {
            return window.dash_clientside.no_update;
        }

        var row_idx = active_cell.row;
        if (row_idx === null || row_idx === undefined || row_idx >= viewport_data.length) {
            return window.dash_clientside.no_update;
        }

        var row = viewport_data[row_idx];
        if (!row || !row.actions) {
            return window.dash_clientside.no_update;
        }

        return {
            row: row_idx,
            clOrdId: row.clOrdId,
            timestamp: Date.now(),
            rowData: row
        };
    }
    """,
    Output("last-actions-click", "data"),
    Input("orders-blotter", "active_cell"),
    Input("orders-blotter", "selected_cells"),
    Input("main-click-wrapper", "n_clicks"),
    State("orders-blotter", "derived_viewport_data"),
)


@callback(
    Output("order-actions-modal", "opened"),
    Output("modal-order-data", "data"),
    Output("modal-clordid-display", "children"),
    Output("modal-symbol-display", "children"),
    Output("modal-side-display", "children"),
    Output("modal-side-display", "color"),
    Output("modal-status-display", "children"),
    Output("modal-status-display", "color"),
    Output("modal-amend-qty", "value"),
    Output("modal-amend-price", "value"),
    Input("last-actions-click", "data"),
    prevent_initial_call=True,
)
def open_actions_modal(click_data):
    """Open the actions modal when the last-actions-click store updates."""
    import dash

    no_action = (
        dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        dash.no_update, dash.no_update, dash.no_update, dash.no_update,
        dash.no_update, dash.no_update
    )

    if not click_data:
        return no_action

    row = click_data.get("rowData")
    if not row:
        return no_action

    if not row.get("actions"):
        return no_action

    side = row.get("side", "")
    side_color = "#00d4aa" if side == "BUY" else "#ff6b6b"

    status = row.get("status", "")
    status_color_map = {
        "NEW": "blue",
        "PENDING": "blue",
        "PENDING_NEW": "blue",
        "PARTIALLY_FILLED": "yellow",
        "PENDING_REPLACE": "cyan",
        "PENDING_CANCEL": "orange",
    }
    status_color = status_color_map.get(status, "gray")

    price_val = None
    price_str = row.get("price", "")
    if price_str and price_str != "MKT":
        try:
            price_val = float(str(price_str).replace("$", ""))
        except (TypeError, ValueError):
            price_val = None

    return (
        True,
        row,
        row.get("clOrdId", ""),
        row.get("symbol", ""),
        side,
        side_color,
        status,
        status_color,
        row.get("quantity"),
        price_val,
    )


@callback(
    Output("modal-action-status", "children"),
    Output("order-actions-modal", "opened", allow_duplicate=True),
    Input("modal-amend-btn", "n_clicks"),
    Input("modal-cancel-btn", "n_clicks"),
    State("modal-order-data", "data"),
    State("modal-amend-qty", "value"),
    State("modal-amend-price", "value"),
    prevent_initial_call=True,
)
def handle_modal_actions(amend_clicks, cancel_clicks, order_data, new_qty, new_price):
    """Handle amend and cancel actions from the modal."""
    import dash

    if not ctx.triggered or not order_data:
        return "", dash.no_update

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    clordid = order_data.get("clOrdId")
    symbol = order_data.get("symbol")
    side = order_data.get("side")

    if not clordid:
        return dmc.Alert("No order selected", color="yellow", variant="light"), dash.no_update

    if triggered_id == "modal-cancel-btn":
        success, result = send_cancel_to_api(clordid, symbol, side)
        if success:
            return (
                dmc.Alert("✓ Cancel request sent", color="blue", variant="light"),
                False,
            )
        return dmc.Alert(f"Cancel failed: {result}", color="red", variant="light"), dash.no_update

    if triggered_id == "modal-amend-btn":
        if not new_qty and not new_price:
            return (
                dmc.Alert("Enter new quantity or price", color="yellow", variant="light"),
                dash.no_update
            )

        success, result = send_amend_to_api(
            clordid, symbol, side,
            new_qty=int(new_qty) if new_qty else None,
            new_price=float(new_price) if new_price else None
        )
        if success:
            return (
                dmc.Alert("✓ Amend request sent", color="blue", variant="light"),
                False,
            )
        return dmc.Alert(f"Amend failed: {result}", color="red", variant="light"), dash.no_update

    return "", dash.no_update


# =============================================================================
# Startup: Load initial data and start Redis subscriber
# =============================================================================

def _fetch_initial_data():
    """Load current state from REST API on startup."""
    print("[Startup] Fetching initial data from FIX Client...")
    try:
        orders = safe_get_json(f"{API_BASE_URL}/orders", timeout=5) or []
        state.update_orders(orders)
        print(f"[Startup] Loaded {len(orders)} orders")
        
        execs = safe_get_json(f"{API_BASE_URL}/executions?limit=100", timeout=5) or []
        state.set_executions(execs)
        print(f"[Startup] Loaded {len(execs)} executions")
    except Exception as e:
        print(f"[Startup] Failed to fetch initial data: {e}")


# Initialize on module load
_fetch_initial_data()

# Only start Redis subscriber in the main process (not the reloader)
# When debug=True, Dash spawns a reloader process. We check for WERKZEUG_RUN_MAIN
# to ensure we only start one subscriber in the actual running process.
import os as _os
if _os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.server.debug:
    _redis_subscriber = RedisSubscriber(state)
    _redis_subscriber.start()
else:
    print("[Startup] Skipping Redis subscriber in reloader parent process")


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  FIX OEMS - Order & Execution Management System")
    print("  (Redis Pub/Sub Edition)")
    print("=" * 60)
    print(f"  API:   {API_BASE_URL}")
    print(f"  Redis: {REDIS_HOST}:{REDIS_PORT}")
    print("  UI:    http://localhost:8050")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=8050)