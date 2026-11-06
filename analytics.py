
import pandas as pd
from database import get_connection


def get_sales_dataframe(start_date=None, end_date=None):
    """Fetch order and product details from MySQL."""

    connection = None
    cursor = None

    query = """
        SELECT
            o.order_id,
            o.order_date,
            o.order_status,
            o.region,
            o.customer_id,
            c.full_name AS buyer,
            oi.item_id,
            oi.product_id,
            p.product_name,
            p.category,
            oi.quantity,
            oi.unit_price,
            COALESCE(oi.discount_optional, 0) AS discount,
            COALESCE(oi.return_amount_optional, 0) AS return_amount,
            p.unit_cost
        FROM orders o
        LEFT JOIN customers c
            ON o.customer_id = c.customer_id
        LEFT JOIN order_items oi
            ON o.order_id = oi.order_id
        LEFT JOIN products p
            ON oi.product_id = p.product_id
        WHERE (%s IS NULL OR o.order_date >= %s)
          AND (%s IS NULL OR o.order_date <= %s)
        ORDER BY o.order_date DESC, o.order_id DESC
    """

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            query,
            (start_date, start_date, end_date, end_date)
        )

        rows = cursor.fetchall()
        df = pd.DataFrame(rows)

        if not df.empty:
            df["quantity"] = pd.to_numeric(
                df["quantity"], errors="coerce"
            ).fillna(0)

            df["unit_price"] = pd.to_numeric(
                df["unit_price"], errors="coerce"
            ).fillna(0)

            df["discount"] = pd.to_numeric(
                df["discount"], errors="coerce"
            ).fillna(0)

            df["return_amount"] = pd.to_numeric(
                df["return_amount"], errors="coerce"
            ).fillna(0)

            df["unit_cost"] = pd.to_numeric(
                df["unit_cost"], errors="coerce"
            )

            df["gross_sales"] = (
                df["quantity"] * df["unit_price"]
            )

            df["net_sales"] = (
                df["gross_sales"]
                - df["discount"]
                - df["return_amount"]
            )

            df["profit"] = (
                df["net_sales"]
                - df["quantity"] * df["unit_cost"]
            )

        return df

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def get_sales_summary(start_date=None, end_date=None):
    """Calculate summary figures for the selected date range."""

    df = get_sales_dataframe(start_date, end_date)

    if df.empty:
        return {
            "total_orders": 0,
            "units_ordered": 0,
            "net_sales": 0.0,
            "total_profit": None
        }

    total_orders = int(df["order_id"].nunique())
    units_ordered = int(df["quantity"].sum())
    net_sales = float(df["net_sales"].sum())

    # Profit is unavailable if any purchased product lacks a cost.
    item_rows = df[df["item_id"].notna()]

    if (
        not item_rows.empty
        and item_rows["unit_cost"].notna().all()
    ):
        total_profit = float(item_rows["profit"].sum())
    else:
        total_profit = None

    return {
        "total_orders": total_orders,
        "units_ordered": units_ordered,
        "net_sales": net_sales,
        "total_profit": total_profit
    }


def get_monthly_sales(df=None):
    """Return monthly net sales for dashboard charts."""

    if df is None:
        df = get_sales_dataframe()

    if df.empty:
        return pd.DataFrame(
            columns=["month", "net_sales"]
        )

    items = df[df["item_id"].notna()].copy()

    if items.empty:
        return pd.DataFrame(
            columns=["month", "net_sales"]
        )

    items["month"] = pd.to_datetime(
        items["order_date"]
    ).dt.strftime("%Y-%m")

    result = (
        items.groupby("month", as_index=False)["net_sales"]
        .sum()
        .sort_values("month")
    )

    return result


def get_regional_sales(df=None):
    """Return net sales grouped by region."""

    if df is None:
        df = get_sales_dataframe()

    if df.empty:
        return pd.DataFrame(
            columns=["region", "net_sales"]
        )

    items = df[df["item_id"].notna()]

    return (
        items.groupby("region", as_index=False)["net_sales"]
        .sum()
        .sort_values("net_sales", ascending=False)
    )


def get_top_products(df=None):
    """Return products ranked by net sales."""

    if df is None:
        df = get_sales_dataframe()

    if df.empty:
        return pd.DataFrame(
            columns=["product_name", "net_sales"]
        )

    items = df[df["item_id"].notna()]

    return (
        items.groupby("product_name", as_index=False)["net_sales"]
        .sum()
        .sort_values("net_sales", ascending=False)
        .head(10)
    )


if __name__ == "__main__":
    try:
        sales = get_sales_dataframe()
        summary = get_sales_summary()

        print("\nE-Commerce Sales Summary")
        print("------------------------")
        print("Total orders:", summary["total_orders"])
        print("Units ordered:", summary["units_ordered"])
        print("Net sales: ₹{:.2f}".format(summary["net_sales"]))

        if summary["total_profit"] is None:
            print("Total profit: Unavailable - product costs are missing")
        else:
            print("Total profit: ₹{:.2f}".format(
                summary["total_profit"]
            ))

        print("\nMonthly Sales")
        print(get_monthly_sales(sales))

        print("\nRegional Sales")
        print(get_regional_sales(sales))

        print("\nTop Products")
        print(get_top_products(sales))

    except Exception as error:
        print("Analytics error:", error)
