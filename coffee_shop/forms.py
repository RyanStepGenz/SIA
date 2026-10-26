import json

from django import forms

from .models import MenuItem, Order


class MenuItemForm(forms.ModelForm):
    recommended_drinks = [
        'Cappuccino',
        'Caramel Macchiato',
        'Iced Latte',
        'Americano',
        'Espresso',
        'Mocha',
        'Vanilla Latte',
        'Hazelnut Latte',
    ]

    class Meta:
        model = MenuItem
        fields = ['name', 'category', 'price', 'stock_quantity', 'availability', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'list': 'recommended-drinks',
                'placeholder': 'Enter item name',
            }),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price <= 0:
            raise forms.ValidationError('Price must be greater than zero.')
        return price

    def clean_stock_quantity(self):
        stock_quantity = self.cleaned_data.get('stock_quantity')
        if stock_quantity is not None and stock_quantity < 0:
            raise forms.ValidationError('Stock quantity cannot be negative.')
        return stock_quantity


class OrderForm(forms.Form):
    customer_name = forms.CharField(
        max_length=150,
        required=False,
        label='Customer name (optional)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'name'}),
    )
    notes = forms.CharField(
        required=False,
        label='Order notes (optional)',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    items = forms.CharField(widget=forms.HiddenInput())
    submission_token = forms.UUIDField(widget=forms.HiddenInput())

    def clean_items(self):
        try:
            items = json.loads(self.cleaned_data['items'])
        except (TypeError, json.JSONDecodeError) as error:
            raise forms.ValidationError('Order items are invalid. Please review the items.') from error

        if not isinstance(items, list) or not items:
            raise forms.ValidationError('Add at least one product to the order.')

        validated_items = []
        seen_product_ids = set()
        for item in items:
            if not isinstance(item, dict):
                raise forms.ValidationError('Order items are invalid. Please review the items.')
            raw_product_id = item.get('product_id')
            raw_quantity = item.get('quantity')
            if (
                isinstance(raw_product_id, bool)
                or isinstance(raw_quantity, bool)
                or not str(raw_product_id).isdigit()
                or not str(raw_quantity).isdigit()
            ):
                raise forms.ValidationError(
                    'Each product must have a valid product and quantity.'
                )
            product_id = int(raw_product_id)
            quantity = int(raw_quantity)

            if product_id <= 0 or quantity <= 0:
                raise forms.ValidationError('Product and quantity must be greater than zero.')
            if product_id in seen_product_ids:
                raise forms.ValidationError('Each product can only appear once in an order.')
            seen_product_ids.add(product_id)
            validated_items.append({'product_id': product_id, 'quantity': quantity})

        return validated_items


class OrderFilterForm(forms.Form):
    search = forms.CharField(
        required=False,
        label='Search',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Order number or customer name',
        }),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All statuses'), *Order.STATUS_CHOICES],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    date_from = forms.DateField(
        required=False,
        label='From',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    date_to = forms.DateField(
        required=False,
        label='To',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    sort = forms.ChoiceField(
        required=False,
        choices=[('newest', 'Newest first'), ('oldest', 'Oldest first')],
        initial='newest',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError('The start date must be on or before the end date.')
        return cleaned_data


class OrderItemForm(forms.Form):
    menu_item = forms.ModelChoiceField(
        queryset=MenuItem.objects.order_by('name'),
        label='Menu Item',
        empty_label='Select an item',
    )
    quantity = forms.IntegerField(min_value=1, label='Quantity')

    def clean(self):
        cleaned_data = super().clean()
        menu_item = cleaned_data.get('menu_item')
        quantity = cleaned_data.get('quantity')

        if menu_item and quantity is not None:
            if menu_item.stock_quantity <= 0:
                raise forms.ValidationError(f'{menu_item.name} is currently out of stock.')
            if quantity > menu_item.stock_quantity:
                raise forms.ValidationError(f'Only {menu_item.stock_quantity} unit(s) available for {menu_item.name}.')

        return cleaned_data
