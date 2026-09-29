"""The Seller Central datasets and the columns a row of each carries, named as SP-API names them in snake_case.

A file parser maps its headers to these names; SP-API documents flatten to them. A column left out of a row is
stored as null: the export did not bring it, which is not the same as 0.
"""

SALES_TRAFFIC_DAILY = "sales_traffic_daily"
SALES_TRAFFIC_BY_ASIN = "sales_traffic_by_asin"
SQP_BRAND_VIEW = "sqp_brand_view"
SQP_ASIN_VIEW = "sqp_asin_view"

BRAND_VIEW = "brand"
ASIN_VIEW = "asin"

SALES_TRAFFIC_DAILY_COLUMNS = (
    "day",
    "currency_code",
    "ordered_product_sales",
    "ordered_product_sales_b2b",
    "units_ordered",
    "units_ordered_b2b",
    "total_order_items",
    "total_order_items_b2b",
    "units_refunded",
    "claims_granted",
    "claims_amount",
    "shipped_product_sales",
    "units_shipped",
    "orders_shipped",
    "page_views",
    "page_views_b2b",
    "browser_page_views",
    "browser_page_views_b2b",
    "mobile_app_page_views",
    "mobile_app_page_views_b2b",
    "sessions",
    "sessions_b2b",
    "browser_sessions",
    "browser_sessions_b2b",
    "mobile_app_sessions",
    "mobile_app_sessions_b2b",
    "buy_box_percentage",
    "buy_box_percentage_b2b",
    "average_offer_count",
    "average_parent_items",
    "feedback_received",
    "negative_feedback_received",
)

SALES_TRAFFIC_BY_ASIN_COLUMNS = (
    "child_asin",
    "parent_asin",
    "title",
    "currency_code",
    "units_ordered",
    "units_ordered_b2b",
    "ordered_product_sales",
    "ordered_product_sales_b2b",
    "total_order_items",
    "total_order_items_b2b",
    "sessions",
    "sessions_b2b",
    "browser_sessions",
    "browser_sessions_b2b",
    "mobile_app_sessions",
    "mobile_app_sessions_b2b",
    "session_percentage",
    "session_percentage_b2b",
    "browser_session_percentage",
    "browser_session_percentage_b2b",
    "mobile_app_session_percentage",
    "mobile_app_session_percentage_b2b",
    "page_views",
    "page_views_b2b",
    "browser_page_views",
    "browser_page_views_b2b",
    "mobile_app_page_views",
    "mobile_app_page_views_b2b",
    "page_views_percentage",
    "page_views_percentage_b2b",
    "browser_page_views_percentage",
    "browser_page_views_percentage_b2b",
    "mobile_app_page_views_percentage",
    "mobile_app_page_views_percentage_b2b",
    "buy_box_percentage",
    "buy_box_percentage_b2b",
)

# own_* is the brand in Brand View and the ASIN in ASIN View; total_* is every product shown for the query.
SEARCH_QUERY_PERFORMANCE_COLUMNS = (
    "search_query",
    "search_query_score",
    "search_query_volume",
    "total_impression_count",
    "own_impression_count",
    "total_click_count",
    "own_click_count",
    "total_median_click_price",
    "own_median_click_price",
    "total_same_day_shipping_click_count",
    "total_one_day_shipping_click_count",
    "total_two_day_shipping_click_count",
    "total_cart_add_count",
    "own_cart_add_count",
    "total_median_cart_add_price",
    "own_median_cart_add_price",
    "total_same_day_shipping_cart_add_count",
    "total_one_day_shipping_cart_add_count",
    "total_two_day_shipping_cart_add_count",
    "total_purchase_count",
    "own_purchase_count",
    "total_median_purchase_price",
    "own_median_purchase_price",
    "total_same_day_shipping_purchase_count",
    "total_one_day_shipping_purchase_count",
    "total_two_day_shipping_purchase_count",
    "currency_code",
)
