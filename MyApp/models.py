from django.db import models


class Product(models.Model):
    Item_ID = models.AutoField(primary_key=True)
    Item_name = models.CharField(max_length=100)

    Category = models.CharField(max_length=20)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    Stock_Quantity = models.IntegerField()

    Availability_Status = models.CharField(max_length=20)

    Date_Added = models.DateField(auto_now_add=True)

    Description = models.TextField()

    def __str__(self):
        return self.Item_name
