from django.shortcuts import render
from .models import Product
# Create your views here.
def product_list(request):
    product = Product.objects.all()
    
    context = {
        'product': product,
    }
    
    return render(request, 'CozyBean.html', context)
