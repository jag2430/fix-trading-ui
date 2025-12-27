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
                    
                    # Symbol input with autocomplete suggestions
                    dmc.TextInput(
                        id="drawer-symbol-input",
                        label="Symbol",
                        placeholder="e.g. AAPL, TSLA, MSFT",
                        styles={"input": {"textTransform": "uppercase", "fontWeight": 800}},
                        rightSection=dmc.ActionIcon(
                            html.I(className="fa-solid fa-magnifying-glass"),
                            variant="subtle",
                            size="sm",
                        ),
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
                    
                    # Quantity and Price inputs
                    dmc.Group(
                        grow=True,
                        mt="md",
                        children=[
                            dmc.NumberInput(
                                id="drawer-quantity-input",
                                label="Quantity",
                                placeholder="Shares",
                                min=1,
                                step=1,
                                value=100,
                                allowDecimal=False,
                                style={"flex": 1},
                            ),
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
                        ],
                    ),
                    
                    # Order Type selector
                    dmc.Select(
                        id="drawer-order-type-select",
                        label="Order Type",
                        data=[
                            {"value": "MARKET", "label": "MARKET"},
                            {"value": "LIMIT", "label": "LIMIT"},
                            {"value": "STOP", "label": "STOP"},
                        ],
                        value="LIMIT",
                        mt="sm",
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
                    
                    # Market data snippet
                    dmc.Paper(
                        p="sm",
                        mt="md",
                        radius="sm",
                        withBorder=True,
                        style={"backgroundColor": "rgba(0,0,0,0.1)"},
                        children=[
                            dmc.Group(
                                justify="apart",
                                children=[
                                    dmc.Text("AAPL", fw=700),
                                    dmc.Group(
                                        gap="xs",
                                        children=[
                                            dmc.Text("$172.35", fw=700, c="green"),
                                            dmc.Text("+1.24%", size="xs", c="green"),
                                        ],
                                    ),
                                ],
                            ),
                            dmc.Text("NASDAQ • Last: $172.35 • Volume: 45.2M", size="xs", c="dimmed"),
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
        
        dcc.Store(id="clicked-outside-table", data=0),

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
                var modal = document.querySelector('.mantine-Modal-root');
                var drawer = document.querySelector('.mantine-Drawer-root');
                
                var clickedInsideOrders = ordersWrapper && ordersWrapper.contains(e.target);
                var clickedInsideExecs = execsWrapper && execsWrapper.contains(e.target);
                var clickedInsideModal = modal && modal.contains(e.target);
                var clickedInsideDrawer = drawer && drawer.contains(e.target);

                var clickedInsideAnyTable =
                  !!e.target.closest('.dash-spreadsheet-container') ||
                  !!e.target.closest('.dash-table-container');
                
                if (wrapper) {
                    if (clickedInsideAnyTable || clickedInsideModal || clickedInsideDrawer) {
                        // Clicked inside tables - remove deselected class to show selection
                        wrapper.classList.remove('tables-deselected');
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
        return ""

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    side = "BUY" if triggered_id == "buy-btn" else "SELL"

    if not symbol or not quantity:
        return dmc.Alert("Enter symbol and quantity", color="yellow", variant="light")

    order_type = (order_type or "LIMIT").upper()
    if order_type == "LIMIT" and (price is None or price == ""):
        return dmc.Alert("Enter price for limit order", color="yellow", variant="light")

    payload = {"symbol": str(symbol).upper(), "side": side, "orderType": order_type, "quantity": int(quantity)}
    if order_type == "LIMIT":
        payload["price"] = float(price)

    try:
        r = requests.post(f"{API_BASE_URL}/orders", json=payload, timeout=5)
        if r.status_code == 200:
            cid = r.json().get("clOrdId")
            return dmc.Alert(f"✓ {side} order sent: {cid}", color="green" if side == "BUY" else "red", variant="light")
        return dmc.Alert("Order failed", color="red", variant="light")
    except Exception as e:
        return dmc.Alert(f"Error: {str(e)}", color="red", variant="light")


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


@callback(
    Output("drawer-order-status-msg", "children"),
    Input("drawer-buy-btn", "n_clicks"),
    Input("drawer-sell-btn", "n_clicks"),
    Input("qty-100", "n_clicks"),
    Input("qty-500", "n_clicks"),
    Input("qty-1000", "n_clicks"),
    Input("qty-5000", "n_clicks"),
    State("drawer-symbol-input", "value"),
    State("drawer-quantity-input", "value"),
    State("drawer-price-input", "value"),
    State("drawer-order-type-select", "value"),
    prevent_initial_call=True,
)
def handle_drawer_orders(buy_clicks, sell_clicks, qty100, qty500, qty1000, qty5000,
                         symbol, quantity, price, order_type):
    """Handle order submission from the trading drawer"""
    if not ctx.triggered:
        return ""
    
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Handle quick quantity buttons
    if triggered_id.startswith("qty-"):
        qty_map = {
            "qty-100": 100,
            "qty-500": 500,
            "qty-1000": 1000,
            "qty-5000": 5000,
        }
        return dash.no_update  # Quantity updates handled by separate callback
    
    # Handle buy/sell orders
    side = "BUY" if triggered_id == "drawer-buy-btn" else "SELL"
    
    if not symbol:
        return dmc.Alert("Enter a symbol", color="yellow", variant="light")
    
    if not quantity:
        return dmc.Alert("Enter quantity", color="yellow", variant="light")
    
    order_type = (order_type or "LIMIT").upper()
    if order_type == "LIMIT" and (price is None or price == ""):
        return dmc.Alert("Enter price for limit order", color="yellow", variant="light")
    
    payload = {
        "symbol": str(symbol).upper(),
        "side": side,
        "orderType": order_type,
        "quantity": int(quantity)
    }
    
    if order_type == "LIMIT" and price:
        payload["price"] = float(price)
    
    try:
        r = requests.post(f"{API_BASE_URL}/orders", json=payload, timeout=5)
        if r.status_code == 200:
            cid = r.json().get("clOrdId")
            # Close drawer after successful order
            return dmc.Alert(
                f"✓ {side} order sent: {cid}",
                color="green" if side == "BUY" else "red",
                variant="light",
                title="Order Submitted",
            )
        return dmc.Alert("Order failed", color="red", variant="light")
    except Exception as e:
        return dmc.Alert(f"Error: {str(e)}", color="red", variant="light")


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


# =============================================================================
# ORDER ACTIONS MODAL CALLBACKS
# =============================================================================

@callback(
    Output("order-actions-modal", "opened"),
    Output("modal-order-data", "data"),
    Output("modal-clordid-display", "children"),
    Output("modal-symbol-display", "children"),
    Output("modal-side-display", "children"),
    Output("modal-side-display", "c"),
    Output("modal-status-display", "children"),
    Output("modal-status-display", "color"),
    Output("modal-amend-qty", "value"),
    Output("modal-amend-price", "value"),
    Output("orders-blotter", "active_cell", allow_duplicate=True),
    Input("orders-blotter", "active_cell"),
    State("orders-blotter", "data"),
    prevent_initial_call=True,
)
def open_actions_modal(active_cell, data):
    """Open the actions modal when clicking on the actions column (three dots)"""
    no_action = (dash.no_update, dash.no_update, dash.no_update, dash.no_update, 
                 dash.no_update, dash.no_update, dash.no_update, dash.no_update, 
                 dash.no_update, dash.no_update, dash.no_update)
    
    if not active_cell or not data:
        return no_action
    
    # Only trigger for clicks on the "actions" column
    if active_cell.get("column_id") != "actions":
        return no_action
    
    row_idx = active_cell.get("row")
    if row_idx is None or row_idx >= len(data):
        return no_action
    
    row = data[row_idx]
    
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
        None,  # Clear active_cell so clicking same cell again works
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
