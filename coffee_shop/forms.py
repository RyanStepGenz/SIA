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


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['status']


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
