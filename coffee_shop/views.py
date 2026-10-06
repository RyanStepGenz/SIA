from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.db.models import Q, Sum
from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import MenuItemForm, OrderForm, OrderItemForm
from .models import MenuItem, Order, OrderItem


def manager_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def staff_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def home(request):
    return redirect('dashboard')


def dashboard(request):
    total_items = MenuItem.objects.count()
    available_items = MenuItem.objects.filter(stock_quantity__gt=0).count()
    out_of_stock_items = MenuItem.objects.filter(stock_quantity=0).count()
    total_orders = Order.objects.count()

    today = timezone.now().date()
    todays_orders = Order.objects.filter(order_date__date=today)
    todays_order_count = todays_orders.count()
    todays_sales = todays_orders.filter(status='Completed').aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    recent_orders = Order.objects.order_by('-order_date')[:5]
    low_stock_items = MenuItem.objects.filter(stock_quantity__lt=5, stock_quantity__gt=0).order_by('stock_quantity')[:10]

    context = {
        'total_items': total_items,
        'available_items': available_items,
        'out_of_stock_items': out_of_stock_items,
        'total_orders': total_orders,
        'todays_order_count': todays_order_count,
        'todays_sales': todays_sales,
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
    }
    return render(request, 'coffee_shop/dashboard.html', context)


def menu_list(request):
    items = MenuItem.objects.all()
    search_query = request.GET.get('search', '').strip()
    category = request.GET.get('category', '')
    availability = request.GET.get('availability', '')

    if search_query:
        items = items.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))
    if category:
        items = items.filter(category=category)
    if availability:
        items = items.filter(availability=availability)

    context = {
        'items': items,
        'categories': [choice[0] for choice in MenuItem.CATEGORY_CHOICES],
        'search_query': search_query,
        'selected_category': category,
        'selected_availability': availability,
        'availability_choices': [choice[0] for choice in MenuItem.AVAILABILITY_CHOICES],
    }
    return render(request, 'coffee_shop/menu_list.html', context)


@manager_required
def menu_create(request):
    if request.method == 'POST':
        form = MenuItemForm(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, 'Menu item successfully added.')
            return redirect('menu_list')
    else:
        form = MenuItemForm()

    return render(request, 'coffee_shop/menu_form.html', {'form': form, 'title': 'Add Menu Item'})


@manager_required
def menu_update(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        form = MenuItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Menu item successfully updated.')
            return redirect('menu_list')
    else:
        form = MenuItemForm(instance=item)

    return render(request, 'coffee_shop/menu_form.html', {'form': form, 'item': item, 'title': 'Edit Menu Item'})


@manager_required
def menu_delete(request, pk):
    item = get_object_or_404(MenuItem, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Menu item successfully deleted.')
        return redirect('menu_list')
    return render(request, 'coffee_shop/menu_confirm_delete.html', {'item': item})


def order_list(request):
    orders = Order.objects.all().order_by('-order_date')
    return render(request, 'coffee_shop/order_list.html', {'orders': orders})


@staff_required
def order_create(request):
    OrderItemFormSet = formset_factory(OrderItemForm, extra=3)
    if request.method == 'POST':
        form = OrderForm(request.POST)
        formset = OrderItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.save()

            has_items = False
            for item_form in formset:
                cleaned = item_form.cleaned_data
                if not cleaned or cleaned.get('DELETE'):
                    continue
                menu_item = cleaned.get('menu_item')
                quantity = cleaned.get('quantity')
                if menu_item and quantity:
                    has_items = True
                    OrderItem.objects.create(order=order, menu_item=menu_item, quantity=quantity, price=menu_item.price)

            if not has_items:
                order.delete()
                messages.error(request, 'Please add at least one product before saving the order.')
                return render(request, 'coffee_shop/order_form.html', {'form': form, 'formset': formset})

            if order.status == 'Completed':
                order.complete_order()
            messages.success(request, 'Order successfully created.')
            return redirect('order_detail', order.pk)
    else:
        form = OrderForm(initial={'status': 'Pending'})
        formset = OrderItemFormSet()

    return render(request, 'coffee_shop/order_form.html', {'form': form, 'formset': formset})


def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    return render(request, 'coffee_shop/order_detail.html', {'order': order})


@staff_required
def complete_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        try:
            order.complete_order()
            messages.success(request, 'Order completed successfully.')
        except ValueError as error:
            messages.error(request, str(error))
    return redirect('order_detail', order.pk)


@staff_required
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.cancel_order()
        messages.success(request, 'Order cancelled successfully.')
    return redirect('order_detail', order.pk)
