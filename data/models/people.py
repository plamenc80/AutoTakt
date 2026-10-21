"""Потребители, клиенти и механици."""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Потребителите влизат с имейл (вместо потребителско име)."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)  # PBKDF2 + salt
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    """Потребител на системата. Ролята е група: Admin, Receptionist, Mechanic, Customer."""

    username = None
    email = models.EmailField("Имейл", unique=True)
    full_name = models.CharField("Име и фамилия", max_length=100)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def has_role(self, *roles):
        return self.is_authenticated and self.groups.filter(name__in=roles).exists()

    @property
    def role(self):
        group = self.groups.first()
        return group.name if group else None

    @property
    def first_name_display(self):
        return (self.full_name or self.email).split(" ")[0]

    def __str__(self):
        return self.full_name or self.email


class Customer(models.Model):
    full_name = models.CharField("Име и фамилия", max_length=100)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("Имейл", max_length=100, blank=True, null=True)
    address = models.CharField("Адрес", max_length=200, blank=True, null=True)
    created_on = models.DateTimeField("Регистриран на", default=timezone.now)
    # Потребителски акаунт (ако клиентът има достъп до „Моят гараж“).
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="customer")

    def __str__(self):
        return self.full_name


class Mechanic(models.Model):
    full_name = models.CharField("Име и фамилия", max_length=100)
    specialty = models.CharField("Специалност", max_length=100, blank=True, null=True)
    hourly_rate = models.DecimalField("Ставка (€/час)", max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField("Активен", default=True)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="mechanic")

    def __str__(self):
        return self.full_name
