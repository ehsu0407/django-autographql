import logging

from bridgekeeper import perms
from django.core.exceptions import PermissionDenied
from django.db.models import Model
from graphene import Connection

from autographql.auth.utils import VIEW, get_model_permission
from autographql.auth.constants import PERMISSION_DENIED_MESSAGE

logger = logging.getLogger(__name__)


class AuthorizationMiddleware(object):
    def resolve(self, next, root, info, **args):
        instance = next(root, info, **args)

        if info.context.user.is_superuser:
            # Superusers have all permissions
            return instance

        value = instance
        user = info.context.user

        # If model, check user has permission to access this model instance
        if isinstance(value, Model):
            # Check access permissions
            permission = get_model_permission(value._meta.model, VIEW)
            logger.debug('Checking permission {0} for user [{1}] to access instance'.format(permission, user))
            if not user.has_perm(permission, value):
                logger.debug('Permission denied for user [{0}] to instance'.format(user))
                raise PermissionDenied(PERMISSION_DENIED_MESSAGE)

        # Connection field, check user has permissions to list this model's instances
        elif isinstance(value, Connection):
            # Make sure it has a model meta on the type. If it doesn't probably not a django connection
            if hasattr(value._meta.node._meta, 'model'):
                model = value._meta.node._meta.model
                permission = get_model_permission(model, VIEW)
                logger.debug('Checking permission {0} for user [{1}] to list [{2}]'.format(permission, user, value))

                # Check bridgekeeper first for possible permissions
                if permission in perms and perms[permission].is_possible_for(user):
                    pass
                # Check against django auth chain
                elif user.has_perm(permission):
                    pass
                else:
                    logger.debug('Permission denied for user [{0}] to list [{1}]'.format(user, value))
                    raise PermissionDenied(PERMISSION_DENIED_MESSAGE)

        return instance
