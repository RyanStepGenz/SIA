from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


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
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PREPARING = 'Preparing', 'Preparing'
        READY = 'Ready', 'Ready'
        COMPLETED = 'Completed', 'Completed'
        CANCELLED = 'Cancelled', 'Cancelled'

    STATUS_CHOICES = Status.choices
    ALLOWED_TRANSITIONS = {
        Status.PENDING: (Status.PREPARING, Status.CANCELLED),
        Status.PREPARING: (Status.READY, Status.CANCELLED),
        Status.READY: (Status.COMPLETED, Status.CANCELLED),
        Status.COMPLETED: (),
        Status.CANCELLED: (),
    }

    order_date = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=Status.PENDING)
    customer_name = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coffee_shop_orders',
    )
    submission_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ('-order_date',)

    def __str__(self):
        return f'Order #{self.pk}'

    def calculate_total(self):
        return sum((item.subtotal for item in self.items.all()), Decimal('0.00'))

    def transition_to(self, new_status):
        if new_status not in self.Status.values:
            raise ValidationError('Select a valid order status.')

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=self.pk)
            if new_status not in self.ALLOWED_TRANSITIONS[order.status]:
                raise ValidationError(
                    f'An order cannot move from {order.status} to {new_status}.'
                )

            if new_status == self.Status.COMPLETED:
                items = list(order.items.select_related('menu_item'))
                if not items:
                    raise ValidationError('An order must contain at least one item.')
                menu_items = {
                    item.pk: item
                    for item in MenuItem.objects.select_for_update().filter(
                        pk__in=[line.menu_item_id for line in items]
                    )
                }
                quantities = {}
                for line in items:
                    quantities[line.menu_item_id] = (
                        quantities.get(line.menu_item_id, 0) + line.quantity
                    )
                for menu_item_id, quantity in quantities.items():
                    menu_item = menu_items[menu_item_id]
                    if quantity > menu_item.stock_quantity:
                        raise ValidationError(
                            f'Not enough stock for {menu_item.name}; '
                            f'{menu_item.stock_quantity} unit(s) remain.'
                        )

                for menu_item_id, quantity in quantities.items():
                    menu_item = menu_items[menu_item_id]
                    menu_item.stock_quantity -= quantity
                    menu_item.save(update_fields=['stock_quantity', 'availability'])

            order.status = new_status
            order.save(update_fields=['status'])
            self.status = order.status
        return self

    def complete_order(self):
        return self.transition_to(self.Status.COMPLETED)

    def cancel_order(self):
        return self.transition_to(self.Status.CANCELLED)


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
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.menu_item is None:
            raise ValidationError({'menu_item': 'Select a menu item.'})
        if self.menu_item.stock_quantity <= 0:
            raise ValidationError(
                {'menu_item': f'{self.menu_item.name} is currently out of stock.'}
            )
        if self.quantity > self.menu_item.stock_quantity:
            raise ValidationError({
                'quantity': (
                    f'Only {self.menu_item.stock_quantity} unit(s) available '
                    f'for {self.menu_item.name}.'
                )
            })

    def save(self, *args, **kwargs):
        if self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self._state.adding:
            self.price = self.menu_item.price
        self.subtotal = self.quantity * self.price
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'subtotal'}
        super().save(*args, **kwargs)
        self.order.total_amount = self.order.calculate_total()
        self.order.save(update_fields=['total_amount'])
