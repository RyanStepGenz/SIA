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
    list_display = ('id', 'order_date', 'customer_name', 'total_amount', 'status', 'created_by')
    list_filter = ('status', 'order_date')
    search_fields = ('customer_name', 'created_by__username')
    ordering = ('-order_date',)
    readonly_fields = (
        'order_date',
        'total_amount',
        'status',
        'customer_name',
        'notes',
        'created_by',
        'submission_token',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('coffee_shop.view_order')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'menu_item', 'quantity', 'price', 'subtotal')
    list_filter = ('menu_item',)
    search_fields = ('menu_item__name',)
    ordering = ('order',)
    readonly_fields = ('order', 'menu_item', 'quantity', 'price', 'subtotal')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('coffee_shop.view_orderitem')
