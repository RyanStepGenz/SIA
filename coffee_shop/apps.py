from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoffeeShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'coffee_shop'

    def ready(self):
        from django.contrib.auth.models import Group

        def create_default_groups(sender, **kwargs):
            Group.objects.get_or_create(name='Manager')
            Group.objects.get_or_create(name='Staff')

        post_migrate.connect(create_default_groups, sender=self)
