from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Supplier, Product, WarehouseReceipt, ReceiptDetail, Inventory, Category, UserAccount

class UserAccountAdmin(UserAdmin):
    model = UserAccount
    list_display = ('username', 'email', 'is_staff', 'is_active',)
    list_filter = ('username', 'email', 'is_staff', 'is_active',)
    fieldsets = (
        (None, {'fields': ('username', 'email', 'password')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('username', 'email',)
    ordering = ('username',)

# Register your models here.
admin.site.register(Supplier)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(UserAccount, UserAccountAdmin)
admin.site.register(WarehouseReceipt)
admin.site.register(ReceiptDetail)
admin.site.register(Inventory)