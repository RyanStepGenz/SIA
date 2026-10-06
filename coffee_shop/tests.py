from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import MenuItem, Order, OrderItem


class CoffeeShopModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='staff', password='secret123', email='staff@example.com'
        )
        self.manager = get_user_model().objects.create_user(
            username='manager', password='secret123', email='manager@example.com'
        )
        self.item = MenuItem.objects.create(
            name='Cappuccino',
            category='Hot Drinks',
            price=Decimal('120.00'),
            stock_quantity=10,
        )

    def test_menu_item_creation_and_stock_validation(self):
        self.assertEqual(MenuItem.objects.count(), 1)
        self.assertEqual(self.item.availability, 'Available')

        with self.assertRaises(ValueError):
            MenuItem.objects.create(
                name='Bad Item',
                category='Hot Drinks',
                price=Decimal('-10.00'),
                stock_quantity=1,
            )

    def test_out_of_stock_behavior(self):
        self.item.stock_quantity = 0
        self.item.save()
        self.assertEqual(self.item.availability, 'Out of Stock')

    def test_order_creation_and_total_calculation(self):
        order = Order.objects.create(status='Pending')
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=2, price=self.item.price)
        self.assertEqual(order.total_amount, Decimal('240.00'))

    def test_completed_order_reduces_inventory(self):
        order = Order.objects.create(status='Pending')
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=3, price=self.item.price)
        order.complete_order()
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_quantity, 7)
        self.assertEqual(order.status, 'Completed')

    def test_order_with_insufficient_stock_fails(self):
        self.item.stock_quantity = 1
        self.item.save()
        order = Order.objects.create(status='Pending')
        line = OrderItem(order=order, menu_item=self.item, quantity=2, price=self.item.price)
        with self.assertRaises(ValueError):
            line.clean()
