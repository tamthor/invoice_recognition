from django.contrib import admin
from .models import Supplier, Product, WarehouseReceipt, ReceiptDetail, Inventory, Category, UserAccount

# Register your models here.

admin.site.register(Supplier)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(UserAccount)
admin.site.register(WarehouseReceipt)
admin.site.register(ReceiptDetail)
admin.site.register(Inventory)