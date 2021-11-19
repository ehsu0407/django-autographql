from bridgekeeper import perms
from django.core.exceptions import FieldError
from django.db import models

from autographql.auth.utils import get_model_permission, VIEW


class AuthQuerySet(models.QuerySet):
    def for_user(self, user):
        # Default functionality is identical to all()
        queryset = self.all()

        # Super users can see everything
        if user.is_superuser:
            return queryset

        # Filter queryset based on user permissions
        permission = get_model_permission(self.model, VIEW)
        if permission in perms:
            queryset = perms[permission].filter(user, queryset)

        return queryset


class AuthModelManager(models.Manager):
    def get_queryset(self):
        return AuthQuerySet(self.model, using=self._db)

    def for_user(self, user):
        return self.get_queryset().for_user(user)
