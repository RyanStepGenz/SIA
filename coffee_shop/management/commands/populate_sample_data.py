from decimal import Decimal

from django.core.management.base import BaseCommand

from coffee_shop.models import MenuItem


class Command(BaseCommand):
    help = 'Populate the database with sample coffee shop menu items.'

    def handle(self, *args, **options):
        sample_items = [
            {'name': 'Caramel Macchiato', 'category': 'Hot Drinks', 'price': Decimal('150.00'), 'stock_quantity': 12,
             'description': 'Espresso with caramel and steamed milk.'},
            {'name': 'Iced Latte', 'category': 'Cold Drinks', 'price': Decimal('140.00'), 'stock_quantity': 8,
             'description': 'Refreshing iced latte with rich espresso flavor.'},
            {'name': 'Cappuccino', 'category': 'Hot Drinks', 'price': Decimal('130.00'), 'stock_quantity': 15,
             'description': 'Classic cappuccino with a velvety foam finish.'},
            {'name': 'Americano', 'category': 'Hot Drinks', 'price': Decimal('110.00'), 'stock_quantity': 10,
             'description': 'A smooth espresso-based black coffee.'},
            {'name': 'Chocolate Cake', 'category': 'Pastries', 'price': Decimal('95.00'), 'stock_quantity': 6,
             'description': 'Rich cake topped with decadent chocolate.'},
            {'name': 'Blueberry Muffin', 'category': 'Pastries', 'price': Decimal('90.00'), 'stock_quantity': 0,
             'description': 'Soft muffin with juicy blueberries.'},
            {'name': 'Croissant', 'category': 'Pastries', 'price': Decimal('85.00'), 'stock_quantity': 7,
             'description': 'Buttery and flaky baked pastry.'},
            {'name': 'French Fries', 'category': 'Snacks', 'price': Decimal('120.00'), 'stock_quantity': 4,
             'description': 'Crispy golden fries for a savory bite.'},
        ]

        created_count = 0
        for item_data in sample_items:
            item, created = MenuItem.objects.get_or_create(name=item_data['name'], defaults=item_data)
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Created {created_count} sample menu items.'))
