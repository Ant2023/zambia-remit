from django.db import models


class PayoutMethod(models.TextChoices):
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK_DEPOSIT = "bank_deposit", "Bank deposit"
