from datetime import date
from peewee import (Model, CharField, TextField, FloatField, IntegerField,
                    DateField, ForeignKeyField)
from database import db


class BaseModel(Model):
    class Meta:
        database = db


class Customer(BaseModel):
    name = CharField()
    email = CharField()
    phone = CharField()
    address = TextField()


class Item(BaseModel):
    name = CharField()
    description = CharField(default="")
    price = FloatField()


class Invoice(BaseModel):
    customer = ForeignKeyField(Customer, backref="invoices")
    date = DateField(default=date.today)
    notes = TextField(default="")

    @property
    def number(self):
        return f"INV-{self.id:04d}"

    @property
    def total(self):
        return sum(line.total for line in self.lines)


class InvoiceItem(BaseModel):
   
    invoice = ForeignKeyField(Invoice, backref="lines", on_delete="CASCADE")
    item = ForeignKeyField(Item, backref="invoice_lines")
    quantity = IntegerField()
    price = FloatField()

    @property
    def total(self):
        return self.quantity * self.price