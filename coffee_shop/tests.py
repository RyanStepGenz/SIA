from decimal import Decimal
import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import MenuItem, Order, OrderItem


class StaffLoginTests(TestCase):
    def test_staff_and_manager_can_sign_in(self):
        user_model = get_user_model()
        for username in ('staff', 'manager'):
            with self.subTest(role=username):
                user_model.objects.create_user(
                    username=username,
                    password='secret123',
                    is_staff=True,
                )
                page = self.client.get(reverse('login'))
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'Staff &amp; Manager Login')
                self.assertContains(page, 'name="username"')
                self.assertContains(page, 'name="password"')

                response = self.client.post(reverse('login'), {
                    'username': username,
                    'password': 'secret123',
                })
                self.assertRedirects(response, reverse('dashboard'))
                self.client.logout()


class CoffeeShopModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='staff', password='secret123', email='staff@example.com'
        )
        self.manager = get_user_model().objects.create_user(
            username='manager', password='secret123', email='manager@example.com', is_staff=True
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
        order.transition_to(Order.Status.PREPARING)
        order.transition_to(Order.Status.READY)
        order.complete_order()
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_quantity, 7)
        self.assertEqual(order.status, 'Completed')

    def test_order_with_insufficient_stock_fails(self):
        self.item.stock_quantity = 1
        self.item.save()
        order = Order.objects.create(status='Pending')
        line = OrderItem(order=order, menu_item=self.item, quantity=2, price=self.item.price)
        with self.assertRaises(ValidationError):
            line.clean()


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username='cashier',
            password='secret123',
            is_staff=True,
        )
        self.customer_user = get_user_model().objects.create_user(
            username='customer',
            password='secret123',
        )
        self.product = MenuItem.objects.create(
            name='Latte',
            category='Hot Drinks',
            price=Decimal('135.50'),
            stock_quantity=8,
        )
        self.client.force_login(self.staff)

    def make_order(self, status=Order.Status.PENDING, quantity=1):
        order = Order.objects.create(status=status)
        OrderItem.objects.create(
            order=order,
            menu_item=self.product,
            quantity=quantity,
            price=self.product.price,
        )
        return order

    def test_order_creation_uses_database_price_and_prevents_duplicate_submission(self):
        token = uuid4()
        payload = {
            'customer_name': 'A Customer',
            'notes': 'Oat milk',
            'items': json.dumps([{
                'product_id': self.product.pk,
                'quantity': 2,
                'price': '0.01',
            }]),
            'submission_token': str(token),
        }

        response = self.client.post(reverse('order_create'), payload)
        order = Order.objects.get()
        self.assertRedirects(response, reverse('order_detail', args=[order.pk]))
        self.assertEqual(order.total_amount, Decimal('271.00'))
        self.assertEqual(order.created_by, self.staff)
        self.assertEqual(order.customer_name, 'A Customer')
        self.assertEqual(order.items.get().price, Decimal('135.50'))

        self.client.post(reverse('order_create'), payload)
        self.assertEqual(Order.objects.count(), 1)

    def test_order_requires_at_least_one_valid_item(self):
        response = self.client.post(reverse('order_create'), {
            'customer_name': '',
            'notes': '',
            'items': '[]',
            'submission_token': str(uuid4()),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, 'Add at least one product')

    def test_order_rejects_unknown_and_unavailable_products(self):
        payload = {
            'customer_name': '',
            'notes': '',
            'items': json.dumps([{'product_id': 999999, 'quantity': 1}]),
            'submission_token': str(uuid4()),
        }
        self.client.post(reverse('order_create'), payload)
        self.assertEqual(Order.objects.count(), 0)

        self.product.stock_quantity = 0
        self.product.save()
        payload['items'] = json.dumps([{
            'product_id': self.product.pk,
            'quantity': 1,
        }])
        payload['submission_token'] = str(uuid4())
        response = self.client.post(reverse('order_create'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, 'currently unavailable')

    def test_order_form_and_print_receipt_render(self):
        response = self.client.get(reverse('order_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'available-products')
        self.assertContains(response, 'Latte')
        order = self.make_order()
        receipt = self.client.get(reverse('order_receipt', args=[order.pk]))
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, 'The Cozy Bean')
        self.assertContains(receipt, f'Order #{order.pk}')

    def test_staff_permissions_are_required(self):
        self.client.logout()
        response = self.client.get(reverse('order_list'))
        self.assertRedirects(
            response,
            f'{reverse("login")}?next={reverse("order_list")}',
        )
        self.client.force_login(self.customer_user)
        self.assertEqual(self.client.get(reverse('order_list')).status_code, 403)

    def test_status_transitions_are_validated_and_complete_stock_once(self):
        order = self.make_order(quantity=2)
        response = self.client.post(reverse('order_status_update', args=[order.pk]), {
            'status': Order.Status.COMPLETED,
        })
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock_quantity, 8)

        for status in (Order.Status.PREPARING, Order.Status.READY, Order.Status.COMPLETED):
            response = self.client.post(reverse('order_status_update', args=[order.pk]), {
                'status': status,
            })
        self.assertRedirects(response, reverse('order_detail', args=[order.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.COMPLETED)
        self.client.post(reverse('order_status_update', args=[order.pk]), {
            'status': Order.Status.CANCELLED,
        })
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.COMPLETED)

    def test_cancelled_order_does_not_reduce_stock(self):
        order = self.make_order(quantity=2)
        order.cancel_order()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_completed_order_cannot_be_edited(self):
        order = self.make_order(status=Order.Status.COMPLETED)
        response = self.client.get(reverse('order_update', args=[order.pk]))
        self.assertRedirects(response, reverse('order_detail', args=[order.pk]))

    def test_order_item_price_is_a_historical_snapshot(self):
        order = self.make_order()
        line = order.items.get()
        self.product.price = Decimal('150.00')
        self.product.save()
        line.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(line.price, Decimal('135.50'))
        self.assertEqual(order.total_amount, Decimal('135.50'))

    def test_order_history_filters_and_paginates_orders(self):
        older = self.make_order()
        older.customer_name = 'Mika'
        older.save(update_fields=['customer_name'])
        newer = self.make_order()
        newer.customer_name = 'Noah'
        newer.status = Order.Status.CANCELLED
        newer.save(update_fields=['customer_name', 'status'])

        response = self.client.get(reverse('order_history'), {
            'search': 'Mika',
            'status': Order.Status.PENDING,
            'sort': 'oldest',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['orders']), [older])

    def test_dashboard_counts_orders_and_only_completed_sales(self):
        completed = self.make_order(quantity=2)
        for status in (Order.Status.PREPARING, Order.Status.READY, Order.Status.COMPLETED):
            completed.transition_to(status)
        cancelled = self.make_order()
        cancelled.cancel_order()

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['total_orders'], 2)
        self.assertEqual(response.context['todays_order_count'], 2)
        self.assertEqual(response.context['todays_sales'], Decimal('271.00'))
        self.assertEqual(response.context['recent_orders'].count(), 2)
