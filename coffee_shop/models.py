from decimal import Decimal

from django.db import models


class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ('Hot Drinks', 'Hot Drinks'),
        ('Cold Drinks', 'Cold Drinks'),
        ('Pastries', 'Pastries'),
        ('Snacks', 'Snacks'),
    ]

    AVAILABILITY_CHOICES = [
        ('Available', 'Available'),
        ('Out of Stock', 'Out of Stock'),
    ]

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    availability = models.CharField(max_length=20, choices=AVAILABILITY_CHOICES, default='Available')
    description = models.TextField(blank=True)
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('category', 'name')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.price <= 0:
            raise ValueError('Price must be greater than zero.')
        if self.stock_quantity < 0:
            raise ValueError('Stock quantity cannot be negative.')

        self.availability = 'Available' if self.stock_quantity > 0 else 'Out of Stock'
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity < 5


class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    order_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')

    class Meta:
        ordering = ('-order_date',)

    def __str__(self):
        return f'Order #{self.pk}'

    def calculate_total(self):
        return sum((item.subtotal for item in self.items.all()), Decimal('0.00'))

    def save(self, *args, **kwargs):
        if self.pk:
            self.total_amount = self.calculate_total()
        super().save(*args, **kwargs)

    def complete_order(self):
        if self.status == 'Completed':
            return self

        for item in self.items.all():
            if item.quantity > item.menu_item.stock_quantity:
                raise ValueError(f'Not enough stock for {item.menu_item.name}.')

        for item in self.items.all():
            item.menu_item.stock_quantity -= item.quantity
            item.menu_item.save()

        self.status = 'Completed'
        self.save(update_fields=['status', 'total_amount'])
        return self

    def cancel_order(self):
        if self.status == 'Completed':
            return self
        self.status = 'Cancelled'
        self.save(update_fields=['status'])
        return self


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ('id',)

    def __str__(self):
        return f'{self.quantity} x {self.menu_item.name}'

    def clean(self):
        if self.quantity <= 0:
            raise ValueError('Quantity must be greater than zero.')
        if self.menu_item is None:
            raise ValueError('Select a menu item.')
        if self.menu_item.stock_quantity <= 0:
            raise ValueError(f'{self.menu_item.name} is currently out of stock.')
        if self.quantity > self.menu_item.stock_quantity:
            raise ValueError(f'Only {self.menu_item.stock_quantity} unit(s) available for {self.menu_item.name}.')

    def save(self, *args, **kwargs):
        self.clean()
        self.price = self.menu_item.price
        self.subtotal = self.quantity * self.price
        super().save(*args, **kwargs)
        self.order.total_amount = self.order.calculate_total()
        self.order.save(update_fields=['total_amount'])
