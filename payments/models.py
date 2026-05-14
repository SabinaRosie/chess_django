from django.db import models
from django.contrib.auth.models import User

class Transaction(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETE', 'Complete'),
        ('FAILED', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_id = models.CharField(max_length=255) # e.g. "coins_500"
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_uuid = models.CharField(max_length=255, unique=True)
    esewa_ref_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.product_id} - {self.status}"
