"""Mermaid rendering (ERD + LangGraph diagram) via mermaid.js in an HTML component."""
import json

import streamlit.components.v1 as components

ERD_MERMAID = """erDiagram
    CUSTOMERS ||--o{ ORDERS : "places"
    ORDERS ||--|{ ORDER_ITEMS : "contains"
    PRODUCTS ||--o{ ORDER_ITEMS : "appears in"
    ORDERS ||--|{ PAYMENTS : "is paid by"
    CUSTOMERS {
        int customer_id PK
        varchar customer_name
        varchar email UK
        varchar city
        varchar state
        date registration_date
    }
    PRODUCTS {
        int product_id PK
        varchar product_name UK
        varchar category
        numeric unit_price
        numeric cost_price
        int stock_quantity
    }
    ORDERS {
        int order_id PK
        int customer_id FK
        date order_date
        varchar order_status
        numeric total_amount
    }
    ORDER_ITEMS {
        int order_item_id PK
        int order_id FK
        int product_id FK
        int quantity
        numeric unit_price
        numeric subtotal
    }
    PAYMENTS {
        int payment_id PK
        int order_id FK
        date payment_date
        varchar payment_method
        varchar payment_status
        numeric amount
    }
"""


def mermaid(code: str, height: int = 600) -> None:
    components.html(f"""
    <div id="m" style="display:flex;justify-content:center"></div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: false, theme: 'neutral', securityLevel: 'strict' }});
      const {{ svg }} = await mermaid.render('g', {json.dumps(code)});
      document.getElementById('m').innerHTML = svg;
    </script>""", height=height, scrolling=True)
