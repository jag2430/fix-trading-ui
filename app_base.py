"""
FIX OEMS - Order & Execution Management System
Professional Trading Dashboard (Dash Mantine Components, compatible with dmc==0.14.7)
"""

from datetime import datetime
import requests

from dash import Dash, dcc, html, Input, Output, State, callback, dash_table, ctx
from dash import _dash_renderer

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
    out = []
    for o in orders or []:
        row = dict(o)
        row["timestamp"] = format_time(row.get("timestamp"))
        row["price"] = format_price(row.get("price"))
        row["filledQuantity"] = row.get("filledQuantity") or 0
        row["leavesQuantity"] = row.get("leavesQuantity")
        if row["leavesQuantity"] is None:
            row["leavesQuantity"] = row.get("quantity", 0)
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

def top_bar():
    return dmc.Paper(
        p="md",
        radius=0,
        withBorder=True,
        children=dmc.Group(
            justify="space-between",
            align="center",
            children=[
                dmc.Group(
                    gap="sm",
                    align="center",
                    children=[
                        html.I(className="fa-solid fa-chart-line", style={"fontSize": "18px"}),
                        dmc.Text("FIX OEMS", fw=900, size="lg"),
                        dmc.Text("Trading Dashboard", c="dimmed", size="sm"),
                    ],
                ),
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


def order_actions_panel():
    return dmc.Paper(
        p="md",
        radius="md",
        withBorder=True,
        children=[
            dmc.Group(gap="xs", children=[html.I(className="fa-solid fa-pen-to-square"), dmc.Text("Order Actions", fw=800)]),
            dmc.Space(h=10),

            dmc.Group(
                grow=True,
                children=[
                    dmc.TextInput(id="action-clordid", label="Selected Order", placeholder="ClOrdId", disabled=True),
                    dmc.TextInput(id="action-symbol", label="Symbol", placeholder="Symbol", disabled=True),
                ],
            ),

            dmc.Group(
                grow=True,
                mt="sm",
                children=[
                    dmc.TextInput(id="action-side", label="Side", placeholder="Side", disabled=True),
                    dmc.NumberInput(
                        id="amend-qty",
                        label="New Qty",
                        placeholder="New Qty",
                        min=1,
                        step=1,
                        allowDecimal=False,
                    ),
                    dmc.NumberInput(
                        id="amend-price",
                        label="New Price",
                        placeholder="New Price",
                        min=0,
                        step=0.01,
                        decimalScale=2,
                        fixedDecimalScale=True,
                    ),
                ],
            ),

            dmc.Group(
                grow=True,
                mt="md",
                children=[
                    dmc.Button("Amend", id="amend-btn", color="yellow"),
                    dmc.Button("Cancel", id="cancel-btn", color="red"),
                ],
            ),

            dmc.Space(h=10),
            html.Div(id="action-status-msg"),
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
                ],
                data=[],
                row_selectable="single",
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
                style_data_conditional=[
                    {"if": {"filter_query": "{side} = BUY"}, "color": "#00d4aa", "fontWeight": "700"},
                    {"if": {"filter_query": "{side} = SELL"}, "color": "#ff6b6b", "fontWeight": "700"},
                    {"if": {"filter_query": "{status} = FILLED"}, "backgroundColor": "rgba(0, 212, 170, 0.10)"},
                    {"if": {"filter_query": "{status} = PARTIALLY_FILLED"}, "backgroundColor": "rgba(255, 217, 61, 0.10)"},
                    {"if": {"filter_query": "{status} = CANCELLED"}, "backgroundColor": "rgba(180, 180, 180, 0.08)"},
                    {"if": {"filter_query": "{status} = REPLACED"}, "backgroundColor": "rgba(77, 171, 247, 0.10)"},
                    {"if": {"filter_query": "{status} = REJECTED"}, "backgroundColor": "rgba(255, 107, 107, 0.12)"},
                    {"if": {"state": "selected"}, "backgroundColor": "rgba(77, 171, 247, 0.25)", "border": "1px solid rgba(77,171,247,0.7)"},
                ],
            ),
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

        dmc.Stack(
            gap=0,
            children=[
                top_bar(),

                dmc.Container(
                    fluid=True,
                    p="md",
                    children=dmc.Stack(
                        gap="md",
                        children=[
                            stats_row(),

                            dmc.Grid(
                                gutter="md",
                                children=[
                                    dmc.GridCol(
                                        span=3,
                                        children=dmc.Stack(
                                            gap="md",
                                            children=[
                                                order_entry_panel(),
                                                order_actions_panel(),
                                            ],
                                        ),
                                    ),
                                    dmc.GridCol(
                                        span=9,
                                        children=dmc.Stack(
                                            gap="md",
                                            children=[
                                                orders_blotter(),
                                                executions_blotter(),
                                            ],
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),

                footer_bar(),
            ],
        ),
    ],
)

# =============================================================================
# Callbacks
# =============================================================================

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
    Output("action-clordid", "value"),
    Output("action-symbol", "value"),
    Output("action-side", "value"),
    Output("amend-qty", "value"),
    Output("amend-price", "value"),
    Input("orders-blotter", "selected_rows"),
    State("orders-blotter", "data"),
    prevent_initial_call=True,
)
def select_order(selected_rows, data):
    if selected_rows and data:
        row = data[selected_rows[0]]
        price = None
        if row.get("price") and row["price"] != "MKT":
            try:
                price = float(str(row["price"]).replace("$", ""))
            except Exception:
                price = None
        return row.get("clOrdId", ""), row.get("symbol", ""), row.get("side", ""), row.get("quantity", ""), price
    return "", "", "", "", ""


@callback(
    Output("action-status-msg", "children"),
    Input("cancel-btn", "n_clicks"),
    Input("amend-btn", "n_clicks"),
    State("action-clordid", "value"),
    State("action-symbol", "value"),
    State("action-side", "value"),
    State("amend-qty", "value"),
    State("amend-price", "value"),
    prevent_initial_call=True,
)
def handle_order_action(_cancel, _amend, clordid, symbol, side, new_qty, new_price):
    if not ctx.triggered or not clordid:
        return dmc.Alert("Select an order first", color="yellow", variant="light")

    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]

    try:
        if triggered_id == "cancel-btn":
            r = requests.delete(
                f"{API_BASE_URL}/orders/{clordid}",
                params={"symbol": symbol, "side": side},
                timeout=5,
            )
            if r.status_code == 200:
                return dmc.Alert("✓ Cancel sent", color="blue", variant="light")
            return dmc.Alert("Cancel failed", color="red", variant="light")

        if triggered_id == "amend-btn":
            if not new_qty and not new_price:
                return dmc.Alert("Enter new qty or price", color="yellow", variant="light")

            payload = {"symbol": symbol, "side": side}
            if new_qty:
                payload["newQuantity"] = int(new_qty)
            if new_price:
                payload["newPrice"] = float(new_price)

            r = requests.put(f"{API_BASE_URL}/orders/{clordid}", json=payload, timeout=5)
            if r.status_code == 200:
                return dmc.Alert("✓ Amend sent", color="blue", variant="light")
            return dmc.Alert("Amend failed", color="red", variant="light")

        return dmc.Alert("Request failed", color="red", variant="light")
    except Exception as e:
        return dmc.Alert(f"Error: {str(e)}", color="red", variant="light")


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


if __name__ == "__main__":
    print("=" * 60)
    print("  FIX OEMS - Order & Execution Management System")
    print("=" * 60)
    print(f"  API: {API_BASE_URL}")
    print("  UI:  http://localhost:8050")
    print("=" * 60)
    app.run(debug=True, host="0.0.0.0", port=8050)

