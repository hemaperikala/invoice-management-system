from datetime import date, datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, make_response, abort, jsonify
)
from peewee import IntegrityError, fn

from database import db
from models import Customer, Item, Invoice, InvoiceItem


app = Flask(__name__)
app.secret_key = "dev-secret-change-me"


# Create tables on startup
with db:
    db.create_tables([Customer, Item, Invoice, InvoiceItem])


# Open / close database connection for every request
@app.before_request
def open_db():
    db.connect(reuse_if_open=True)


@app.teardown_request
def close_db(exc):
    if not db.is_closed():
        db.close()


@app.context_processor
def inject_globals():
    return {"currency": "₹"}


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/")
@app.route("/dashboard")
def dashboard():
    customer_count = Customer.select().count()
    item_count = Item.select().count()
    invoice_count = Invoice.select().count()

    revenue = (
        InvoiceItem
        .select(fn.SUM(InvoiceItem.quantity * InvoiceItem.price))
        .scalar()
    ) or 0

    recent = list(
        Invoice.select(Invoice, Customer)
        .join(Customer)
        .order_by(Invoice.id.desc())
        .limit(5)
    )

    return render_template(
        "dashboard.html",
        customer_count=customer_count,
        item_count=item_count,
        invoice_count=invoice_count,
        revenue=revenue,
        recent=recent,
    )


# --------------------------------------------------
# CUSTOMERS
# --------------------------------------------------

@app.route("/customers")
def customers():
    # The page is now rendered without customer data.
    # JavaScript will fetch the data using /api/customers.
    return render_template("customers.html")


@app.route("/api/customers")
def api_customers():
    customers = Customer.select().order_by(Customer.name)

    data = [
        {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
        }
        for customer in customers
    ]

    return jsonify(data)


@app.post("/customers/save")
def save_customer():
    data = {
        "name": request.form["name"].strip(),
        "email": request.form["email"].strip(),
        "phone": request.form["phone"].strip(),
        "address": request.form["address"].strip(),
    }

    cid = request.form.get("id")

    if cid:
        Customer.update(**data).where(
            Customer.id == int(cid)
        ).execute()

        flash("Customer updated.", "positive")

    else:
        Customer.create(**data)
        flash("Customer added.", "positive")

    return redirect(url_for("customers"))


@app.post("/customers/<int:id>/delete")
def delete_customer(id):
    customer = Customer.get_or_none(Customer.id == id)

    if not customer:
        abort(404)

    try:
        customer.delete_instance()
        flash("Customer deleted.", "positive")

    except IntegrityError:
        flash(
            "Can't delete this customer - they have invoices. "
            "Delete those invoices first.",
            "negative"
        )

    return redirect(url_for("customers"))


# --------------------------------------------------
# ITEMS
# --------------------------------------------------

@app.route("/items")
def items():
    rows = Item.select().order_by(Item.name)
    return render_template("items.html", items=rows)


@app.post("/items/save")
def save_item():
    data = {
        "name": request.form["name"].strip(),
        "description": request.form.get("description", "").strip(),
        "price": float(request.form["price"]),
    }

    iid = request.form.get("id")

    if iid:
        Item.update(**data).where(
            Item.id == int(iid)
        ).execute()

        flash("Item updated.", "positive")

    else:
        Item.create(**data)
        flash("Item added.", "positive")

    return redirect(url_for("items"))


@app.post("/items/<int:id>/delete")
def delete_item(id):
    item = Item.get_or_none(Item.id == id)

    if not item:
        abort(404)

    try:
        item.delete_instance()
        flash("Item deleted.", "positive")

    except IntegrityError:
        flash(
            "Can't delete this item - it is used in an invoice.",
            "negative"
        )

    return redirect(url_for("items"))


# --------------------------------------------------
# INVOICES
# --------------------------------------------------

@app.route("/invoices")
def invoices():
    invoice_list = list(
        Invoice.select(Invoice, Customer)
        .join(Customer)
        .order_by(Invoice.id.desc())
    )

    customer_list = list(
        Customer.select().order_by(Customer.name)
    )

    item_list = list(
        Item.select().order_by(Item.name)
    )

    invoices_json = {
        str(inv.id): {
            "customer": inv.customer_id,
            "date": inv.date.isoformat(),
            "notes": inv.notes or "",
            "lines": [
                {
                    "item": l.item_id,
                    "quantity": l.quantity
                }
                for l in inv.lines
            ],
        }
        for inv in invoice_list
    }

    items_json = [
        {
            "id": i.id,
            "name": i.name,
            "price": i.price
        }
        for i in item_list
    ]

    return render_template(
        "invoices.html",
        invoices=invoice_list,
        customers=customer_list,
        items=item_list,
        invoices_json=invoices_json,
        items_json=items_json,
        today=date.today().isoformat(),
    )


@app.post("/invoices/save")
def save_invoice():
    iid = request.form.get("id")

    customer_id = int(
        request.form["customer"]
    )

    inv_date = datetime.strptime(
        request.form["date"],
        "%Y-%m-%d"
    ).date()

    notes = request.form.get(
        "notes",
        ""
    ).strip()

    item_ids = request.form.getlist("item_id")
    quantities = request.form.getlist("quantity")

    lines = [
        (int(i), int(q))
        for i, q in zip(item_ids, quantities)
        if i and q
    ]

    if not lines:
        flash(
            "Add at least one item to the invoice.",
            "negative"
        )

        return redirect(url_for("invoices"))

    with db.atomic():

        if iid:
            invoice = Invoice.get_by_id(
                int(iid)
            )

            invoice.customer = customer_id
            invoice.date = inv_date
            invoice.notes = notes
            invoice.save()

            # Remember old prices so editing doesn't
            # change prices of existing invoice lines.
            old_prices = {
                l.item_id: l.price
                for l in invoice.lines
            }

            InvoiceItem.delete().where(
                InvoiceItem.invoice == invoice
            ).execute()

            flash(
                "Invoice updated.",
                "positive"
            )

        else:
            invoice = Invoice.create(
                customer=customer_id,
                date=inv_date,
                notes=notes
            )

            old_prices = {}

            flash(
                "Invoice created.",
                "positive"
            )

        for item_id, qty in lines:

            item = Item.get_by_id(item_id)

            InvoiceItem.create(
                invoice=invoice,
                item=item,
                quantity=qty,
                price=old_prices.get(
                    item_id,
                    item.price
                ),
            )

    return redirect(url_for("invoices"))


@app.post("/invoices/<int:id>/delete")
def delete_invoice(id):
    invoice = Invoice.get_or_none(
        Invoice.id == id
    )

    if not invoice:
        abort(404)

    invoice.delete_instance()

    flash(
        "Invoice deleted.",
        "positive"
    )

    return redirect(url_for("invoices"))


@app.route("/invoices/<int:id>/download")
def download_invoice(id):
    invoice = Invoice.get_or_none(
        Invoice.id == id
    )

    if not invoice:
        abort(404)

    lines = list(
        InvoiceItem
        .select(InvoiceItem, Item)
        .join(Item)
        .where(
            InvoiceItem.invoice == invoice
        )
    )

    html = render_template(
        "invoice_pdf.html",
        invoice=invoice,
        lines=lines
    )

    try:
        from weasyprint import HTML

        pdf = HTML(
            string=html
        ).write_pdf()

    except OSError as e:
        flash(
            f"WeasyPrint isn't set up correctly: {e}",
            "negative"
        )

        return redirect(
            url_for("invoices")
        )

    response = make_response(pdf)

    response.headers["Content-Type"] = (
        "application/pdf"
    )

    response.headers["Content-Disposition"] = (
        f"attachment; filename={invoice.number}.pdf"
    )

    return response


# --------------------------------------------------
# RUN
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)