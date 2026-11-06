
from datetime import date, datetime

import pandas as pd
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    Response,
    flash,
)

from database import get_connection
from analytics import (
    get_sales_dataframe,
    get_sales_summary,
    get_monthly_sales,
    get_regional_sales,
    get_top_products,
)

app = Flask(__name__)
app.secret_key = "ecommerce-bi-local-key"


# ==================================================
# DATABASE HELPERS
# ==================================================

def fetch_all(query, params=None):
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchall()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def fetch_one(query, params=None):
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchone()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def execute_query(query, params=None):
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute(query, params or ())
        connection.commit()
        return cursor.lastrowid
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def get_customer_count():
    result = fetch_one(
        "SELECT COUNT(*) AS total FROM customers"
    )
    return result["total"] if result else 0


def get_product_count():
    result = fetch_one(
        "SELECT COUNT(*) AS total FROM products"
    )
    return result["total"] if result else 0


# ==================================================
# MAIN DASHBOARD
# ==================================================

@app.route("/")
@app.route("/dashboard")
def index():
    try:
        df = get_sales_dataframe()
        summary = get_sales_summary()

        monthly = get_monthly_sales(df)
        regional = get_regional_sales(df)
        top_products = get_top_products(df)

        total_revenue = summary["net_sales"]
        total_orders = summary["total_orders"]

        average_order_value = (
            total_revenue / total_orders
            if total_orders else 0
        )

        return render_template(
            "index.html",
            summary=summary,
            total_orders=total_orders,
            units_ordered=summary["units_ordered"],
            total_revenue=total_revenue,
            total_profit=summary["total_profit"],
            average_order_value=average_order_value,
            total_customers=get_customer_count(),
            total_products=get_product_count(),
            months=monthly["month"].tolist(),
            monthly_revenue=monthly["net_sales"].tolist(),
            regions=regional["region"].fillna("Unknown").tolist(),
            regional_revenue=regional["net_sales"].tolist(),
            products=top_products["product_name"].fillna(
                "Unknown"
            ).tolist(),
            product_revenue=top_products["net_sales"].tolist(),
            sales_data=df.to_dict("records"),
        )

    except Exception as error:
        app.logger.exception("Dashboard error")
        return f"Dashboard error: {error}", 500


# ==================================================
# SALES ANALYTICS
# ==================================================

@app.route("/analytics")
def analytics_dashboard():
    today = date.today().isoformat()

    start_date = request.args.get(
        "start_date", "2026-10-01"
    )
    end_date = request.args.get("end_date", today)

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if start > end:
            return "Start date must be on or before end date.", 400

    except ValueError:
        return "Please enter valid dates in YYYY-MM-DD format.", 400

    try:
        summary = get_sales_summary(start_date, end_date)
        df = get_sales_dataframe(start_date, end_date)

        purchases = (
            df[df["item_id"].notna()].to_dict("records")
            if not df.empty else []
        )

        return render_template(
            "order_analytics.html",
            summary=summary,
            purchases=purchases,
            start_date=start_date,
            end_date=end_date,
        )

    except Exception as error:
        app.logger.exception("Analytics page error")
        return f"Analytics page error: {error}", 500


# ==================================================
# CUSTOMERS
# ==================================================

@app.route("/customers")
def customers():
    try:
        rows = fetch_all("""
            SELECT customer_id, full_name, email, phone,
                   city, created_at
            FROM customers
            ORDER BY customer_id DESC
        """)

        return render_template(
            "customers.html",
            customers=rows,
        )

    except Exception as error:
        app.logger.exception("Customers page error")
        return f"Customers page error: {error}", 500


@app.route("/customers/add", methods=["GET", "POST"])
def add_customer():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()

        if not full_name or not email:
            flash("Name and email are required.")
            return redirect(url_for("add_customer"))

        try:
            execute_query("""
                INSERT INTO customers
                    (full_name, email, phone, city)
                VALUES (%s, %s, %s, %s)
            """, (
                full_name,
                email,
                phone or None,
                city or None,
            ))

            flash("Customer added successfully.")
            return redirect(url_for("customers"))

        except Exception as error:
            app.logger.exception("Add customer error")
            return f"Could not add customer: {error}", 500

    return render_template("add_customer.html")


@app.route(
    "/customers/edit/<int:customer_id>",
    methods=["GET", "POST"],
)
def edit_customer(customer_id):
    customer = fetch_one(
        "SELECT * FROM customers WHERE customer_id = %s",
        (customer_id,),
    )

    if customer is None:
        return "Customer not found.", 404

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()

        if not full_name or not email:
            flash("Name and email are required.")
            return redirect(
                url_for("edit_customer", customer_id=customer_id)
            )

        try:
            execute_query("""
                UPDATE customers
                SET full_name = %s,
                    email = %s,
                    phone = %s,
                    city = %s
                WHERE customer_id = %s
            """, (
                full_name,
                email,
                phone or None,
                city or None,
                customer_id,
            ))

            flash("Customer updated successfully.")
            return redirect(url_for("customers"))

        except Exception as error:
            app.logger.exception("Edit customer error")
            return f"Could not update customer: {error}", 500

    return render_template(
        "edit_customer.html",
        customer=customer,
    )


@app.route(
    "/customers/delete/<int:customer_id>",
    methods=["POST"],
)
def delete_customer(customer_id):
    try:
        linked_order = fetch_one(
            """
            SELECT order_id
            FROM orders
            WHERE customer_id = %s
            LIMIT 1
            """,
            (customer_id,),
        )

        if linked_order:
            flash(
                "This customer is linked to an order "
                "and cannot be deleted."
            )
        else:
            execute_query(
                "DELETE FROM customers WHERE customer_id = %s",
                (customer_id,),
            )
            flash("Customer deleted.")

        return redirect(url_for("customers"))

    except Exception as error:
        app.logger.exception("Delete customer error")
        return f"Could not delete customer: {error}", 500


@app.route("/customers/export")
def export_customers():
    try:
        rows = fetch_all("""
            SELECT customer_id, full_name, email, phone,
                   city, created_at
            FROM customers
            ORDER BY customer_id
        """)

        csv_data = pd.DataFrame(rows).to_csv(index=False)

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    "attachment; filename=customers.csv"
            },
        )

    except Exception as error:
        app.logger.exception("Customer export error")
        return f"Customer export error: {error}", 500


# ==================================================
# ALL ORDERS
# ==================================================

@app.route("/all-orders")
def all_orders():
    try:
        rows = fetch_all("""
            SELECT
                o.order_id,
                o.order_date,
                o.order_status,
                o.region,
                o.customer_id,
                c.full_name AS buyer
            FROM orders o
            LEFT JOIN customers c
                ON o.customer_id = c.customer_id
            ORDER BY o.order_date DESC, o.order_id DESC
        """)

        return render_template(
            "all_orders.html",
            orders=rows,
        )

    except Exception as error:
        app.logger.exception("Orders page error")
        return f"Orders page error: {error}", 500


# ==================================================
# ALL PRODUCTS
# ==================================================

@app.route("/all-products")
def all_products():
    try:
        rows = fetch_all("""
            SELECT product_id, product_name, category,
                   image, unit_cost
            FROM products
            ORDER BY product_id
        """)

        return render_template(
            "all_products.html",
            products=rows,
        )

    except Exception as error:
        app.logger.exception("Products page error")
        return f"Products page error: {error}", 500


# ==================================================
# EARNINGS
# ==================================================

@app.route("/earnings")
def earnings():
    try:
        summary = get_sales_summary()
        monthly = get_monthly_sales()

        total_revenue = summary["net_sales"]
        total_orders = summary["total_orders"]

        average_order_value = (
            total_revenue / total_orders
            if total_orders else 0
        )

        return render_template(
            "earnings.html",
            summary=summary,
            total_revenue=total_revenue,
            total_orders=total_orders,
            units_ordered=summary["units_ordered"],
            total_profit=summary["total_profit"],
            average_order_value=average_order_value,
            months=monthly["month"].tolist(),
            monthly_revenue=monthly["net_sales"].tolist(),
        )

    except Exception as error:
        app.logger.exception("Earnings page error")
        return f"Earnings page error: {error}", 500


# ==================================================
# SALES REPORT
# ==================================================

@app.route("/report")
def report():
    try:
        df = get_sales_dataframe()
        summary = get_sales_summary()

        total_revenue = summary["net_sales"]
        total_orders = summary["total_orders"]

        average_order_value = (
            total_revenue / total_orders
            if total_orders else 0
        )

        customer_count = get_customer_count()

        # Regional revenue
        regional_sales = get_regional_sales(df)

        regions = (
            regional_sales["region"]
            .fillna("Unknown")
            .tolist()
            if not regional_sales.empty else []
        )

        regional_revenue = (
            regional_sales["net_sales"].tolist()
            if not regional_sales.empty else []
        )

        # Top products
        top_products = get_top_products(df)

        products = (
            top_products["product_name"]
            .fillna("Unknown")
            .tolist()
            if not top_products.empty else []
        )

        product_revenue = (
            top_products["net_sales"].tolist()
            if not top_products.empty else []
        )

        # Business insights
        insights = []

        if not top_products.empty:
            best_product = top_products.iloc[0]

            insights.append({
                "title": "Top-Selling Product",
                "detail": (
                    f'{best_product["product_name"]} generated '
                    f'₹{best_product["net_sales"]:,.2f} in revenue.'
                ),
            })

        if not regional_sales.empty:
            best_region = regional_sales.iloc[0]

            insights.append({
                "title": "Leading Region",
                "detail": (
                    f'{best_region["region"]} generated '
                    f'₹{best_region["net_sales"]:,.2f} in revenue.'
                ),
            })

        if summary["total_profit"] is None:
            insights.append({
                "title": "Profit Information",
                "detail": (
                    "Profit is unavailable because product unit costs "
                    "are missing. Add the actual costs in MySQL."
                ),
            })

        return render_template(
            "report.html",
            now=datetime.now().strftime("%d-%m-%Y %H:%M"),
            selected_region="All regions",
            total_revenue=total_revenue,
            total_orders=total_orders,
            average_order_value=average_order_value,
            customer_count=customer_count,
            regions=regions,
            regional_revenue=regional_revenue,
            products=products,
            product_revenue=product_revenue,
            insights=insights,
        )

    except Exception as error:
        app.logger.exception("Report page error")
        return f"Report page error: {error}", 500


# ==================================================
# EXPORT SALES DATA AS CSV
# ==================================================

@app.route("/export/csv")
def export_csv():
    try:
        csv_data = get_sales_dataframe().to_csv(index=False)

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    "attachment; filename=ecommerce_sales.csv"
            },
        )

    except Exception as error:
        app.logger.exception("Sales export error")
        return f"Sales export error: {error}", 500


# ==================================================
# MESSAGE CENTER
# ==================================================

@app.route("/message-center")
def message_center():
    try:
        rows = fetch_all("""
            SELECT *
            FROM user_messages
            ORDER BY 1 DESC
        """)

        return render_template(
            "message_center.html",
            messages=rows,
        )

    except Exception as error:
        app.logger.exception("Message center error")
        return f"Message center error: {error}", 500


# ==================================================
# 404 ERROR HANDLER
# ==================================================

@app.errorhandler(404)
def page_not_found(error):
    app.logger.warning("Page not found: %s", request.path)
    return f"Page not found: {request.path}", 404


# ==================================================
# START FLASK
# Keep this at the very bottom
# ==================================================

if __name__ == "__main__":
    print(app.url_map)
    app.run(debug=True)
