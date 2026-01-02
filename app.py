"""
FIX OEMS - Order & Execution Management System
Professional Trading Dashboard (Dash Mantine Components, compatible with dmc==0.14.7)
"""

from datetime import datetime
import requests

from dash import Dash, dcc, html, Input, Output, State, callback, dash_table, dash
from dash import _dash_renderer, ctx

_dash_renderer._set_react_version("18.2.0")

import dash_mantine_components as dmc

# =============================================================================
# Configuration
# =============================================================================

API_BASE_URL = "http://localhost:8081/api"
REFRESH_MS = 2000

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
# Helpers
# =============================================================================

def safe_get_json(url: str, timeout: int = 2):
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def search_symbols(query: str, timeout: int = 2):
    """Search for symbols using the FIX Client API"""
    if not query or len(query.strip()) < 1:
        return []
    try:
        r = requests.get(f"{API_BASE_URL}/symbols/search", params={"q": query.strip()}, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            return data.get("results", [])
    except Exception:
        pass
    return []


def validate_symbol(symbol: str, timeout: int = 2):
    """Validate a symbol using the FIX Client API"""
    if not symbol:
        return None
    try:
        r = requests.get(f"{API_BASE_URL}/symbols/{symbol.strip().upper()}/validate", timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def format_time(ts):
    if not ts:
        return ""
    if isinstance(ts, str):
        return ts[11:19] if len(ts) >= 19 else ts
    return str(ts)


def format_price(v):
    if v is None:
        return "MKT"
    try:
        fv = float(v)
        if fv <= 0:
            return "MKT"
        return f"${fv:.2f}"
    except Exception:
        return "MKT"


def normalize_orders_for_table(orders):
    # Statuses that are considered "open" and can be acted upon
    OPEN_STATUSES = {"NEW", "PENDING", "PARTIALLY_FILLED", "PENDING_REPLACE", "PENDING_NEW", "PENDING_CANCEL"}

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
    out = []
    for e in execs or []:
        row = dict(e)
        row["timestamp"] = format_time(row.get("timestamp"))

        lp = row.get("lastPrice")
        ap = row.get("avgPrice")

        try:
            row["lastPrice"] = f"${float(lp):.2f}" if lp and float(lp) > 0 else "-"
        except Exception:
            row["lastPrice"] = "-"

        try:
            row["avgPrice"] = f"${float(ap):.2f}" if ap and float(ap) > 0 else "-"
        except Exception:
            row["avgPrice"] = "-"

        out.append(row)
    return out

def mk_stat_card(title: str, value_id: str, color=None):
    # Mantine expects a string color; guard against objects/dicts accidentally passed in
    if isinstance(color, (dict, list)):
        color = None

    text_kwargs = {"size": "xl", "fw": 900, "mt": 4, "id": value_id}
    if isinstance(color, str) and color.strip():
        text_kwargs["c"] = color  # only set if it's a valid string

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
# UI Blocks (0.14.7-safe)
# =============================================================================

def main_navbar():
    """Main navigation bar with trading button"""
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

                # Center: Navigation buttons
                dmc.Group(
                    gap="sm",
                    align="center",
                    children=[
                        dmc.Button(
                            "Trading",
                            id="trading-btn",
                            leftSection=html.I(className="fa-solid fa-trade-federation"),
                            variant="light",
                            color="blue",
                        ),
                        dmc.Button(
                            "Analytics",
                            leftSection=html.I(className="fa-solid fa-chart-pie"),
                            variant="subtle",
                        ),
                        dmc.Button(
                            "Risk",
                            leftSection=html.I(className="fa-solid fa-shield-halved"),
                            variant="subtle",
                        ),
                        dmc.Button(
                            "Reports",
                            leftSection=html.I(className="fa-solid fa-file-lines"),
                            variant="subtle",
                        ),
                    ],
                ),

                # Right side: Status and time
                dmc.Group(
                    gap="md",
                    align="center",
                    children=[
                        dmc.Badge("DISCONNECTED", id="connection-badge", color="red", variant="filled", radius="sm"),
                        dmc.Text(id="header-time", size="sm", c="dimmed"),
                    ],
                ),
            ],
        ),
    )


def trading_drawer():
    """Drawer/sidebar that contains the order entry panel"""
    return dmc.Drawer(
        id="trading-drawer",
        title=dmc.Group(
            gap="xs",
            children=[
                html.I(className="fa-solid fa-trade-federation", style={"fontSize": "18px"}),
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
                        data=[],  # Will be populated dynamically
                        styles={
                            "input": {"textTransform": "uppercase", "fontWeight": 800},
                        },
                        comboboxProps={"withinPortal": False, "zIndex": 20000},
                        leftSection=html.I(className="fa-solid fa-magnifying-glass", style={"fontSize": "12px"}),
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

                    # Order Type selector (moved above price inputs)
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


def order_entry_panel():
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(gap="xs", children=[html.I(className="fa-solid fa-paper-plane"), dmc.Text("Order Entry", fw=800)]),
            dmc.Space(h=10),

            dmc.TextInput(
                id="symbol-input",
                label="Symbol",
                placeholder="e.g. AAPL",
                styles={"input": {"textTransform": "uppercase", "fontWeight": 800, "textAlign": "center"}},
            ),

            dmc.Group(
                grow=True,
                mt="sm",
                children=[
                    dmc.NumberInput(
                        id="quantity-input",
                        label="Quantity",
                        placeholder="Shares",
                        min=1,
                        step=1,
                        allowDecimal=False,
                    ),
                    # IMPORTANT: dmc 0.14.7 uses decimalScale/fixedDecimalScale (NOT precision)
                    dmc.NumberInput(
                        id="price-input",
                        label="Price",
                        placeholder="Limit Price",
                        min=0,
                        step=0.01,
                        decimalScale=2,
                        fixedDecimalScale=True,
                    ),
                ],
            ),

            dmc.Select(
                id="order-type-select",
                label="Order Type",
                data=[{"value": "LIMIT", "label": "LIMIT"}, {"value": "MARKET", "label": "MARKET"}],
                value="LIMIT",
                mt="sm",
            ),

            dmc.Group(
                grow=True,
                mt="md",
                children=[
                    dmc.Button("BUY", id="buy-btn", color="green"),
                    dmc.Button("SELL", id="sell-btn", color="red"),
                ],
            ),

            dmc.Space(h=10),
            html.Div(id="order-status-msg"),
        ],
    )


def stats_row():
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
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                children=[
                    dmc.Group(gap="xs", children=[html.I(className="fa-solid fa-list"), dmc.Text("Orders Blotter", fw=800)]),
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
                    "fontFamily": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace",
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
                        "rule": "background-color: rgba(255,255,255,0.04) !important; background: rgba(255,255,255,0.04) !important;",
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
                    # Make actions column stand out with hover-like color for cells with content
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
    """Modal popup for order actions (Amend/Cancel)"""
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
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(
                justify="space-between",
                align="center",
                children=[
                    dmc.Group(gap="xs", children=[html.I(className="fa-solid fa-right-left"), dmc.Text("Execution Reports", fw=800)]),
                    dmc.Button("Clear", id="clear-executions-btn", variant="outline", color="gray", size="sm"),
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
    return dmc.Paper(
        p="sm",
        radius=0,
        withBorder=True,
        children=dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Text("FIX OEMS v1.0 | Connected to localhost:8081", size="xs", c="dimmed"),
                dmc.Text(id="footer-session-info", size="xs", c="dimmed"),
            ],
        ),
    )


# =============================================================================
# Layout (NO AppShell to avoid 0.14.7 slot-prop issues)
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
        
        # Interval for notification timeout (checks every second)
        dcc.Interval(id="notification-interval", interval=1000, n_intervals=0),
        
        # Store for order submission timestamp (to auto-dismiss after 7s)
        dcc.Store(id="order-submission-timestamp", data=None),

        dcc.Store(id="clicked-outside-table", data=0),

        # Store to track last action cell click (for fixing the multi-click issue)
        dcc.Store(id="last-actions-click", data={"row": None, "clOrdId": None, "timestamp": 0}),
        
        # Store for validated symbol data
        dcc.Store(id="validated-symbol-data", data=None),

        # Trading Drawer (initially hidden)
        trading_drawer(),

        # Order Actions Modal (for amend/cancel from blotter)
        order_actions_modal(),

        # Main wrapper - will have "tables-deselected" class toggled
        html.Div(
            id="main-click-wrapper",
            n_clicks=0,
            className="",
            children=[
                dmc.Stack(
                    gap=0,
                    children=[
                        # Main Navigation Bar
                        main_navbar(),

                        dmc.Container(
                            fluid=True,
                            p="md",
                            children=dmc.Stack(
                                gap="md",
                                children=[
                                    stats_row(),
                                    # Full width blotters (no sidebar)
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

# Clientside callback to handle click-outside deselection via CSS
app.clientside_callback(
    """
    function(n) {
        if (!window._deselectListenerAdded) {
            window._deselectListenerAdded = true;
            window.__outsideClicks = window.__outsideClicks || 0;
            window.__outsideClicksLastSent = window.__outsideClicksLastSent || 0;


            // Inject CSS for hiding selection
            var style = document.createElement('style');
            style.id = 'custom-table-styles';
            style.textContent = `
              /* Hide *any* active/selected/focus styling when user clicked away */
              .tables-deselected .dash-spreadsheet-container td.cell--selected,
              .tables-deselected .dash-spreadsheet-container td.focused,
              .tables-deselected .dash-spreadsheet-container td[tabindex="0"],
              .tables-deselected .dash-spreadsheet-container td[aria-selected="true"],
              .tables-deselected .dash-spreadsheet-container td:focus,
              .tables-deselected .dash-spreadsheet-container td:focus-within,
              .tables-deselected .dash-spreadsheet-container td[tabindex="0"]:focus,
              .tables-deselected .dash-spreadsheet-container td[tabindex="0"]:focus-within {
                  background-color: transparent !important;
                  border: 1px solid rgba(255,255,255,0.06) !important;
                  box-shadow: none !important;
                  outline: none !important;
              }

              /* Some builds apply focus styling to an inner div */
              .tables-deselected .dash-spreadsheet-container td > div:focus,
              .tables-deselected .dash-spreadsheet-container td:focus > div,
              .tables-deselected .dash-spreadsheet-container td:focus-within > div {
                  outline: none !important;
                  box-shadow: none !important;
              }

              /* Smooth fade when clearing selection */
              .tables-deselected .dash-spreadsheet-container td {
                  transition:
                      background-color 10ms linear,
                      border-color 10ms linear,
                      box-shadow 10ms linear;
              }

              /* ============================================================
                 PREVENT HEADER HOVER - headers are th.dash-header in tbody
                 ============================================================ */

              /* Target the header cells and ALL their children */
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

              /* Keep the th itself with the dark background */
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
                var ordersWrapper = document.getElementById('orders-blotter-wrapper');
                var execsWrapper = document.getElementById('executions-blotter-wrapper');

                // Use closest() so we correctly detect clicks inside Mantine Drawer/Modal even if classnames differ.
                var clickedInsideModal = !!e.target.closest('.mantine-Modal-root, [data-mantine-modal], [role="dialog"]');
                var clickedInsideDrawer = !!e.target.closest('.mantine-Drawer-root, .mantine-Drawer-content, [data-mantine-drawer], [data-mantine-drawer-body]');

                // Mantine Select/Popover dropdowns are rendered in a portal (outside the Drawer DOM).
                // If we don't treat them as 'inside', our click-outside handler immediately blurs/closes the dropdown.
                var clickedInsideMantineDropdown = (
                  // dropdown/menu/popover/combobox containers
                  !!e.target.closest(
                    '.mantine-Select-dropdown, .mantine-Popover-dropdown, .mantine-Combobox-dropdown, .mantine-Menu-dropdown'
                  ) ||
                  // common option items / combobox internals
                  !!e.target.closest(
                    '.mantine-Select-item, .mantine-Combobox-option, .mantine-Menu-item, .mantine-Popover-target'
                  ) ||
                  // portal wrapper (mantine portals mount under body)
                  !!e.target.closest('[data-mantine-portal]') ||
                  // role-based (combobox/listbox/options)
                  !!e.target.closest('[role="listbox"], [role="option"], [role="combobox"]')
                );

                var clickedInsideOverlay = clickedInsideModal || clickedInsideDrawer || clickedInsideMantineDropdown;

                var clickedInsideAnyTable =
                  !!e.target.closest('.dash-spreadsheet-container') ||
                  !!e.target.closest('.dash-table-container');

                if (wrapper) {
                    if (clickedInsideAnyTable || clickedInsideOverlay) {
                        // Clicked inside tables - remove deselected class to show selection
                        wrapper.classList.remove('tables-deselected');
                        if (clickedInsideAnyTable) wrapper.click();

                    } else {
                        // Clicked outside tables - add deselected class to hide selection
                        wrapper.classList.add('tables-deselected');
                        window.__outsideClicks = (window.__outsideClicks || 0) + 1;

                        if (document.activeElement && document.activeElement.blur) {
                          document.activeElement.blur();
                        }
                        // ALSO clear the existing selected/focused cell classes so it truly "unhighlights"
                        document
                          .querySelectorAll('.dash-spreadsheet-container td.cell--selected')
                          .forEach((td) => td.classList.remove('cell--selected'));

                        document
                          .querySelectorAll('.dash-spreadsheet-container td.focused')
                          .forEach((td) => td.classList.remove('focused'));
                    }
                }
            });
        }
        // Only notify Dash when an outside click actually occurred
        if (window.__outsideClicks !== window.__outsideClicksLastSent) {
          window.__outsideClicksLastSent = window.__outsideClicks;
          return window.__outsideClicks;
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

@callback(Output("header-time", "children"), Input("refresh-interval", "n_intervals"))
def update_time(_n):
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@callback(
    Output("connection-badge", "children"),
    Output("connection-badge", "color"),
    Output("footer-session-info", "children"),
    Input("refresh-interval", "n_intervals"),
)
def update_connection_status(_n):
    sessions = safe_get_json(f"{API_BASE_URL}/sessions", timeout=2)
    if sessions and len(sessions) > 0 and sessions[0].get("loggedOn"):
        s = sessions[0]
        footer = f"Session: {s.get('senderCompId')} → {s.get('targetCompId')}"
        return "CONNECTED", "green", footer
    return "DISCONNECTED", "red", "No active session"


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
    orders = safe_get_json(f"{API_BASE_URL}/orders", timeout=2) or []
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
    Output("order-status-msg", "children"),
    Output("symbol-input", "value"),
    Output("quantity-input", "value"),
    Output("price-input", "value"),
    Input("buy-btn", "n_clicks"),
    Input("sell-btn", "n_clicks"),
    State("symbol-input", "value"),
    State("quantity-input", "value"),
    State("price-input", "value"),
    State("order-type-select", "value"),
    prevent_initial_call=True,
)
def submit_order(_buy, _sell, symbol, quantity, price, order_type):
    if not ctx.triggered:
        return "", dash.no_update, dash.no_update, dash.no_update

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    side = "BUY" if triggered_id == "buy-btn" else "SELL"

    if not symbol or not quantity:
        return (
            dmc.Alert("Enter symbol and quantity", color="yellow", variant="light"),
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

    order_type = (order_type or "LIMIT").upper()
    if order_type == "LIMIT" and (price is None or price == ""):
        return (
            dmc.Alert("Enter price for limit order", color="yellow", variant="light"),
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )

    payload = {
        "symbol": str(symbol).upper(),
        "side": side,
        "orderType": order_type,
        "quantity": int(quantity),
    }
    if order_type == "LIMIT":
        payload["price"] = float(price)

    try:
        r = requests.post(f"{API_BASE_URL}/orders", json=payload, timeout=5)
        if r.status_code == 200:
            cid = r.json().get("clOrdId")
            alert = dmc.Alert(
                f"✓ {side} {order_type} order sent: {cid}",
                color="green" if side == "BUY" else "red",
                variant="light",
            )
            # Clear fields after a successful submit
            return alert, "", None, None

        return (
            dmc.Alert("Order failed", color="red", variant="light"),
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )
    except Exception as e:
        return (
            dmc.Alert(f"Error: {str(e)}", color="red", variant="light"),
            dash.no_update,
            dash.no_update,
            dash.no_update,
        )


@callback(
    Output("orders-blotter", "data"),
    Input("refresh-interval", "n_intervals"),
    Input("orders-filter", "value"),
)
def refresh_orders(_n, filter_value):
    orders = safe_get_json(f"{API_BASE_URL}/orders", timeout=2) or []
    fv = (filter_value or "all").lower()

    if fv == "working":
        orders = [
            o for o in orders
            if (o.get("status") or "").upper() in ("NEW", "PENDING", "PARTIALLY_FILLED", "PENDING_REPLACE", "PENDING_NEW", "PENDING_CANCEL")
        ]
    elif fv == "filled":
        orders = [o for o in orders if (o.get("status") or "").upper() == "FILLED"]

    return normalize_orders_for_table(orders)


@callback(Output("executions-blotter", "data"), Input("refresh-interval", "n_intervals"))
def refresh_executions(_n):
    execs = safe_get_json(f"{API_BASE_URL}/executions?limit=50", timeout=2) or []
    return normalize_execs_for_table(execs)


@callback(
    Output("executions-blotter", "data", allow_duplicate=True),
    Input("clear-executions-btn", "n_clicks"),
    prevent_initial_call=True,
)
def clear_executions(_n):
    try:
        requests.delete(f"{API_BASE_URL}/executions", timeout=2)
    except Exception:
        pass
    return []


# =============================================================================
# NEW CALLBACKS FOR TRADING DRAWER
# =============================================================================

@callback(
    Output("trading-drawer", "opened"),
    Input("trading-btn", "n_clicks"),
    State("trading-drawer", "opened"),
    prevent_initial_call=True,
)
def toggle_trading_drawer(n_clicks, opened):
    """Toggle the trading drawer when trading button is clicked"""
    if n_clicks:
        return not opened
    return opened


# =============================================================================
# SYMBOL SEARCH / AUTOCOMPLETE CALLBACKS
# =============================================================================

@callback(
    Output("drawer-symbol-input", "data"),
    Output("selected-symbol-store", "data"),
    Input("drawer-symbol-input", "searchValue"),
    Input("drawer-symbol-input", "value"),
    State("selected-symbol-store", "data"),
    State("drawer-symbol-input", "data"),
    prevent_initial_call=True,
)
def update_symbol_options(search_value, selected_value, stored_symbol, current_data):
    """
    Update symbol dropdown options based on search query.
    Fetches from the FIX Client /api/symbols/search endpoint.
    Preserves the currently selected value in options.
    """
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else None
    triggered_prop = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
    
    # If a value was just selected, store it and preserve the option
    if triggered_id == "drawer-symbol-input" and "value" in triggered_prop:
        if selected_value:
            # Find the full option data for the selected value
            selected_option = None
            if current_data:
                for opt in current_data:
                    if opt.get("value") == selected_value:
                        selected_option = opt
                        break
            
            if selected_option:
                return [selected_option], {"symbol": selected_value, "option": selected_option}
            else:
                # Create a basic option if not found
                basic_option = {"value": selected_value, "label": selected_value}
                return [basic_option], {"symbol": selected_value, "option": basic_option}
        else:
            # Value was cleared
            return [], None
    
    # If searchValue triggered this but we have a stored symbol, keep showing it
    if stored_symbol and stored_symbol.get("symbol"):
        stored_option = stored_symbol.get("option", {"value": stored_symbol["symbol"], "label": stored_symbol["symbol"]})
        stored_symbol_value = stored_symbol["symbol"]
        
        # If no search or empty search, just show the stored option
        if not search_value or len(search_value.strip()) < 1:
            return [stored_option], dash.no_update
        
        # If searching, fetch results but include stored option
        results = search_symbols(search_value)
        options = []
        seen_values = set()  # Track seen values to avoid duplicates
        stored_in_results = False
        
        for r in results:
            symbol = r.get("symbol", "")
            
            # Skip if we've already seen this symbol
            if symbol in seen_values:
                continue
            seen_values.add(symbol)
            
            description = r.get("description", "")
            symbol_type = r.get("type", "")
            
            if description:
                label = f"{symbol} - {description}"
            else:
                label = symbol
            
            if symbol_type and symbol_type != "Common Stock":
                label = f"{label} ({symbol_type})"
            
            options.append({"value": symbol, "label": label})
            
            if symbol == stored_symbol_value:
                stored_in_results = True
        
        # Only add the stored option if it's not already in results
        if not stored_in_results and stored_symbol_value not in seen_values:
            options.insert(0, stored_option)
        
        return options if options else [stored_option], dash.no_update
    
    # No stored symbol - just do a fresh search
    if not search_value or len(search_value.strip()) < 1:
        return [], dash.no_update
    
    results = search_symbols(search_value)
    
    options = []
    seen_values = set()  # Track seen values to avoid duplicates
    
    for r in results:
        symbol = r.get("symbol", "")
        
        # Skip if we've already seen this symbol
        if symbol in seen_values:
            continue
        seen_values.add(symbol)
        
        description = r.get("description", "")
        symbol_type = r.get("type", "")
        
        if description:
            label = f"{symbol} - {description}"
        else:
            label = symbol
        
        if symbol_type and symbol_type != "Common Stock":
            label = f"{label} ({symbol_type})"
        
        options.append({"value": symbol, "label": label})
    
    return options if options else [], dash.no_update


@callback(
    Output("drawer-symbol-info", "children"),
    Output("validated-symbol-data", "data"),
    Input("drawer-symbol-input", "value"),
    State("validated-symbol-data", "data"),
    prevent_initial_call=True,
)
def validate_and_display_symbol(symbol, previous_validation):
    """
    Validate selected symbol and display company info.
    Shows company name, current price, and validation status.
    """
    if not symbol:
        return [], None
    
    # Validate the symbol
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
                    html.I(className="fa-solid fa-circle-xmark", style={"color": "#ff6b6b", "fontSize": "12px"}),
                    dmc.Text(
                        validation_msg or "Invalid symbol",
                        size="xs",
                        c="red",
                    ),
                ],
            )
        ], None
    
    # Build the info display for valid symbols
    info_parts = []
    
    # Valid indicator
    info_parts.append(html.I(className="fa-solid fa-circle-check", style={"color": "#00d4aa", "fontSize": "12px"}))
    
    # Company name
    if company_name:
        info_parts.append(
            dmc.Text(
                company_name,
                size="xs",
                c="dimmed",
                fw=500,
                style={"maxWidth": "200px", "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
            )
        )
    
    # Price info
    if current_price is not None:
        price_text = f"${float(current_price):.2f}"
        
        # Add change info if available
        if change is not None and change_percent is not None:
            change_val = float(change)
            change_pct = float(change_percent)
            change_color = "#00d4aa" if change_val >= 0 else "#ff6b6b"
            change_sign = "+" if change_val >= 0 else ""
            price_text = f"${float(current_price):.2f} ({change_sign}{change_val:.2f}, {change_sign}{change_pct:.2f}%)"
            
            info_parts.append(
                dmc.Text(
                    price_text,
                    size="xs",
                    c=change_color,
                    fw=600,
                )
            )
        else:
            info_parts.append(
                dmc.Text(
                    price_text,
                    size="xs",
                    c="blue",
                    fw=600,
                )
            )
    
    return [
        dmc.Group(
            gap="xs",
            align="center",
            children=info_parts,
        )
    ], validation


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
    Input("qty-100", "n_clicks"),
    Input("qty-500", "n_clicks"),
    Input("qty-1000", "n_clicks"),
    Input("qty-5000", "n_clicks"),
    State("drawer-symbol-input", "value"),
    State("drawer-quantity-input", "value"),
    State("drawer-price-input", "value"),
    State("drawer-stop-price-input", "value"),
    State("drawer-order-type-select", "value"),
    State("validated-symbol-data", "data"),
    prevent_initial_call=True,
)
def handle_drawer_orders(buy_clicks, sell_clicks, qty100, qty500, qty1000, qty5000,
                         symbol, quantity, price, stop_price, order_type, validated_data):
    """Handle order submission from the trading drawer"""
    import time

    # 8 outputs in this callback:
    # (status msg, symbol, quantity, price, stop_price, submission_timestamp, selected_symbol_store, symbol_info)
    no_update = (dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update)

    if not ctx.triggered:
        return no_update

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # Quick quantity buttons are handled by a separate callback; do nothing here.
    if triggered_id.startswith("qty-"):
        return no_update

    # Handle buy/sell orders
    side = "BUY" if triggered_id == "drawer-buy-btn" else "SELL"

    if not symbol:
        return (
            dmc.Alert("Enter a symbol", color="yellow", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )

    # Validate symbol before submission
    if validated_data is None:
        # Symbol wasn't validated yet, try to validate now
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
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )

    if not quantity:
        return (
            dmc.Alert("Enter quantity", color="yellow", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )

    order_type = (order_type or "LIMIT").upper()

    # Validate price requirements based on order type
    if order_type == "LIMIT" and (price is None or price == ""):
        return (
            dmc.Alert("Enter limit price for LIMIT order", color="yellow", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )

    # Build payload
    payload = {
        "symbol": str(symbol).upper(),
        "side": side,
        "orderType": order_type,
        "quantity": int(quantity),
    }

    if order_type == "LIMIT":
        payload["price"] = float(price)

    try:
        r = requests.post(f"{API_BASE_URL}/orders", json=payload, timeout=5)
        if r.status_code == 200:
            cid = r.json().get("clOrdId")
            current_time = time.time()

            price_info = f" @ ${float(price):.2f}" if order_type == "LIMIT" else ""
            
            # Include company name in confirmation if available
            company_name = validated_data.get("name", "")
            symbol_display = f"{symbol} ({company_name})" if company_name else symbol

            alert = dmc.Alert(
                f"✓ {side} {order_type} order sent for {symbol_display}: {cid}{price_info}",
                color="green" if side == "BUY" else "red",
                variant="light",
                title="Order Submitted",
            )

            # Clear fields immediately while drawer stays open
            # Use "" (empty string) instead of None to properly clear NumberInput fields visually
            return (alert, None, "", "", "", current_time, None, [])

        # Handle error response
        error_detail = ""
        try:
            error_json = r.json()
            error_detail = error_json.get("message", "")
        except Exception:
            pass
        
        return (
            dmc.Alert(f"Order failed{': ' + error_detail if error_detail else ''}", color="red", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )
    except Exception as e:
        return (
            dmc.Alert(f"Error: {str(e)}", color="red", variant="light"),
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
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
    """Set quantity based on quick quantity buttons"""
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
    """Auto-dismiss notification after 4 seconds"""
    import time
    
    if submission_time is None:
        return dash.no_update
    
    # Check if 4 seconds have passed
    if time.time() - submission_time >= 4:
        return ""  # Clear the notification
    
    return dash.no_update


@callback(
    Output("drawer-price-input", "style"),
    Output("drawer-price-input", "label"),
    Output("drawer-stop-price-input", "style"),
    Input("drawer-order-type-select", "value"),
)
def update_price_fields_visibility(order_type):
    """Show/hide price fields based on order type"""
    order_type = (order_type or "LIMIT").upper()
    
    # Define styles
    show_style = {"flex": 1}
    hide_style = {"flex": 1, "display": "none"}
    
    if order_type == "MARKET":
        # Hide both price fields
        return hide_style, "Limit Price", hide_style
    elif order_type == "LIMIT":
        # Show only limit price
        return show_style, "Limit Price", hide_style
    elif order_type == "STOP":
        # Show only stop price (in the limit price slot for cleaner UI)
        return hide_style, "Limit Price", show_style
    elif order_type == "STOP_LIMIT":
        # Show both
        return show_style, "Limit Price", show_style
    
    # Default - show limit price only
    return show_style, "Limit Price", hide_style


# =============================================================================
# ORDER ACTIONS MODAL CALLBACKS - FIXED VERSION 2
# =============================================================================
# Using cell click timestamp tracking via clientside callback

# Clientside callback to detect ANY cell click and record timestamp
app.clientside_callback(
    """
    function(active_cell,selected_cells, n_clicks, viewport_data) {
        if (!active_cell || !viewport_data) {
            return window.dash_clientside.no_update;
        }

        // Only care about actions column
        if (active_cell.column_id !== 'actions') {
            return window.dash_clientside.no_update;
        }

        var row_idx = active_cell.row;
        if (row_idx === null || row_idx === undefined || row_idx >= viewport_data.length) {
            return window.dash_clientside.no_update;
        }

        // IMPORTANT: use the *visible/sorted* rows
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
    """
    Open the actions modal when the last-actions-click store updates.
    This is triggered by the clientside callback that detects cell clicks.
    """
    # Default "no action" return
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

    # Only open modal for orders that have actions (open orders)
    if not row.get("actions"):
        return no_action

    # Determine colors based on side and status
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

    # Parse price for the amend input
    price_val = None
    price_str = row.get("price", "")
    if price_str and price_str != "MKT":
        try:
            price_val = float(str(price_str).replace("$", ""))
        except Exception:
            price_val = None

    return (
        True,  # Open modal
        row,   # Store order data
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
    """Handle amend and cancel actions from the modal"""
    if not ctx.triggered or not order_data:
        return "", dash.no_update

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    clordid = order_data.get("clOrdId")
    symbol = order_data.get("symbol")
    side = order_data.get("side")

    if not clordid:
        return dmc.Alert("No order selected", color="yellow", variant="light"), dash.no_update

    try:
        if triggered_id == "modal-cancel-btn":
            r = requests.delete(
                f"{API_BASE_URL}/orders/{clordid}",
                params={"symbol": symbol, "side": side},
                timeout=5,
            )
            if r.status_code == 200:
                return (
                    dmc.Alert("✓ Cancel request sent", color="blue", variant="light"),
                    False,  # Close modal
                )
            return dmc.Alert("Cancel failed", color="red", variant="light"), dash.no_update

        if triggered_id == "modal-amend-btn":
            if not new_qty and not new_price:
                return dmc.Alert("Enter new quantity or price", color="yellow", variant="light"), dash.no_update

            payload = {"symbol": symbol, "side": side}
            if new_qty:
                payload["newQuantity"] = int(new_qty)
            if new_price:
                payload["newPrice"] = float(new_price)

            r = requests.put(f"{API_BASE_URL}/orders/{clordid}", json=payload, timeout=5)
            if r.status_code == 200:
                return (
                    dmc.Alert("✓ Amend request sent", color="blue", variant="light"),
                    False,  # Close modal
                )
            return dmc.Alert("Amend failed", color="red", variant="light"), dash.no_update

        return "", dash.no_update

    except Exception as e:
        return dmc.Alert(f"Error: {str(e)}", color="red", variant="light"), dash.no_update


if __name__ == "__main__":
    print("=" * 60)
    print("  FIX OEMS - Order & Execution Management System")
    print("=" * 60)
    print(f"  API: {API_BASE_URL}")
    print("  UI:  http://localhost:8050")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=8050)