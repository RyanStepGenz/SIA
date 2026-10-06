from django.contrib import admin

from .models import MenuItem, Order, OrderItem


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock_quantity', 'availability', 'date_added')
    list_filter = ('category', 'availability')
    search_fields = ('name', 'description')
    ordering = ('-date_added',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_date', 'total_amount', 'status')
    list_filter = ('status', 'order_date')
    search_fields = ('id',)
    ordering = ('-order_date',)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'menu_item', 'quantity', 'price', 'subtotal')
    list_filter = ('menu_item',)
    search_fields = ('menu_item__name',)
    ordering = ('order',)
