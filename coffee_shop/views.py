from decimal import Decimal
from functools import wraps
import json
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import MenuItemForm, OrderFilterForm, OrderForm
from .models import MenuItem, Order, OrderItem


def staff_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def manager_required(view_func):
    return staff_required(view_func)


def home(request):
    return redirect('dashboard')


@staff_required
def dashboard(request):
    today = timezone.localdate()
    todays_orders = Order.objects.filter(order_date__date=today)
    todays_sales = todays_orders.filter(status=Order.Status.COMPLETED).aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')

    context = {
        'total_items': MenuItem.objects.count(),
        'available_items': MenuItem.objects.filter(stock_quantity__gt=0).count(),
        'out_of_stock_items': MenuItem.objects.filter(stock_quantity=0).count(),
        'total_orders': Order.objects.count(),
        'todays_order_count': todays_orders.count(),
        'todays_sales': todays_sales,
        'recent_orders': Order.objects.order_by('-order_date')[:5],
        'low_stock_items': MenuItem.objects.filter(
            stock_quantity__lt=5,
            stock_quantity__gt=0,
        ).order_by('stock_quantity')[:10],
    }
    return render(request, 'coffee_shop/dashboard.html', context)


@staff_required
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
            form.save()
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


def _order_products():
    return list(MenuItem.objects.order_by('category', 'name').values(
        'id', 'name', 'category', 'price', 'stock_quantity',
    ))


def _order_form_context(form, initial_items=None, order=None):
    if initial_items is None and form.is_bound:
        try:
            initial_items = json.loads(form.data.get('items', '[]'))
        except (TypeError, json.JSONDecodeError):
            initial_items = []
        if not isinstance(initial_items, list):
            initial_items = []
    return {
        'form': form,
        'products': _order_products(),
        'initial_items': initial_items or [],
        'order': order,
    }


def _save_order(form, user, order=None):
    requested_items = form.cleaned_data['items']
    with transaction.atomic():
        if order is not None:
            order = Order.objects.select_for_update().get(pk=order.pk)
            if order.status not in (Order.Status.PENDING, Order.Status.PREPARING):
                form.add_error(None, 'Only pending or preparing orders can be edited.')
                return None, False
        else:
            existing_order = Order.objects.filter(
                submission_token=form.cleaned_data['submission_token']
            ).first()
            if existing_order:
                return existing_order, False

        products = {
            item.pk: item
            for item in MenuItem.objects.select_for_update().filter(
                pk__in=[line['product_id'] for line in requested_items]
            )
        }
        if len(products) != len(requested_items):
            form.add_error('items', 'One or more selected products no longer exist.')
            return None, False

        for line in requested_items:
            product = products[line['product_id']]
            if product.stock_quantity <= 0:
                form.add_error('items', f'{product.name} is currently unavailable.')
                return None, False
            if line['quantity'] > product.stock_quantity:
                form.add_error(
                    'items',
                    f'Only {product.stock_quantity} unit(s) of {product.name} are available.',
                )
                return None, False

        if order is None:
            try:
                with transaction.atomic():
                    order = Order.objects.create(
                        customer_name=form.cleaned_data['customer_name'],
                        notes=form.cleaned_data['notes'],
                        created_by=user,
                        submission_token=form.cleaned_data['submission_token'],
                    )
            except IntegrityError:
                existing_order = Order.objects.filter(
                    submission_token=form.cleaned_data['submission_token']
                ).first()
                if existing_order:
                    return existing_order, False
                raise
        else:
            order.customer_name = form.cleaned_data['customer_name']
            order.notes = form.cleaned_data['notes']
            order.save(update_fields=['customer_name', 'notes'])
            order.items.all().delete()
            order.total_amount = Decimal('0.00')
            order.save(update_fields=['total_amount'])

        for line in requested_items:
            OrderItem.objects.create(
                order=order,
                menu_item=products[line['product_id']],
                quantity=line['quantity'],
                price=products[line['product_id']].price,
            )
    return order, True


@staff_required
def order_list(request):
    filter_form = OrderFilterForm(request.GET or None)
    orders = Order.objects.select_related('created_by').annotate(
        item_count=Count('items'),
        item_units=Sum('items__quantity'),
    )

    if filter_form.is_valid():
        filters = filter_form.cleaned_data
        search = filters['search']
        if search:
            search_filter = Q(customer_name__icontains=search)
            if search.startswith('#'):
                search = search[1:]
            if search.isdigit():
                search_filter |= Q(pk=int(search))
            orders = orders.filter(search_filter)
        if filters['status']:
            orders = orders.filter(status=filters['status'])
        if filters['date_from']:
            orders = orders.filter(order_date__date__gte=filters['date_from'])
        if filters['date_to']:
            orders = orders.filter(order_date__date__lte=filters['date_to'])
        orders = orders.order_by(
            'order_date' if filters['sort'] == 'oldest' else '-order_date'
        )
    else:
        orders = orders.order_by('-order_date')

    paginator = Paginator(orders, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)
    return render(request, 'coffee_shop/order_list.html', {
        'orders': page_obj.object_list,
        'page_obj': page_obj,
        'filter_form': filter_form,
        'query_string': query_params.urlencode(),
        'is_history': request.resolver_match.url_name == 'order_history',
    })


@staff_required
def order_create(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            existing_order = Order.objects.filter(
                submission_token=form.cleaned_data['submission_token']
            ).first()
            if existing_order:
                messages.info(request, 'This order was already submitted.')
                return redirect('order_detail', pk=existing_order.pk)
            order, created = _save_order(form, request.user)
            if order:
                if created:
                    messages.success(request, 'Order successfully created.')
                else:
                    messages.info(request, 'This order was already submitted.')
                return redirect('order_detail', pk=order.pk)
    else:
        form = OrderForm(initial={
            'items': '[]',
            'submission_token': uuid4(),
        })

    return render(
        request,
        'coffee_shop/order_form.html',
        _order_form_context(form),
    )


@staff_required
def order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.status not in (Order.Status.PENDING, Order.Status.PREPARING):
        messages.error(request, 'Only pending or preparing orders can be edited.')
        return redirect('order_detail', pk=order.pk)

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            saved_order, _ = _save_order(form, request.user, order=order)
            if saved_order:
                messages.success(request, 'Order successfully updated.')
                return redirect('order_detail', pk=saved_order.pk)
    else:
        form = OrderForm(initial={
            'customer_name': order.customer_name,
            'notes': order.notes,
            'items': '[]',
            'submission_token': uuid4(),
        })

    initial_items = None
    if request.method == 'GET':
        initial_items = [
            {'product_id': line.menu_item_id, 'quantity': line.quantity}
            for line in order.items.select_related('menu_item')
        ]
    return render(
        request,
        'coffee_shop/order_form.html',
        _order_form_context(form, initial_items=initial_items, order=order),
    )


@staff_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('created_by').prefetch_related('items__menu_item'),
        pk=pk,
    )
    return render(request, 'coffee_shop/order_detail.html', {'order': order})


@staff_required
def order_receipt(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('created_by').prefetch_related('items__menu_item'),
        pk=pk,
    )
    return render(request, 'coffee_shop/order_receipt.html', {'order': order})


@staff_required
def order_status_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method != 'POST':
        return redirect('order_detail', pk=order.pk)

    try:
        order.transition_to(request.POST.get('status', ''))
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        messages.success(request, f'Order status updated to {order.status}.')
    return redirect('order_detail', pk=order.pk)


@staff_required
def complete_order(request, pk):
    if request.method == 'POST':
        request.POST = request.POST.copy()
        request.POST['status'] = Order.Status.COMPLETED
        return order_status_update(request, pk)
    return redirect('order_detail', pk=pk)


@staff_required
def cancel_order(request, pk):
    if request.method == 'POST':
        request.POST = request.POST.copy()
        request.POST['status'] = Order.Status.CANCELLED
        return order_status_update(request, pk)
    return redirect('order_detail', pk=pk)
