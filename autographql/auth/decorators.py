import six

from functools import wraps
from django.core.exceptions import PermissionDenied


def context(f):
    def decorator(func):
        def wrapper(*args, **kwargs):
            info = args[f.__code__.co_varnames.index('info')]
            return func(info.context, *args, **kwargs)
        return wrapper
    return decorator


def user_passes_test(test_func, error_message=None):
    def decorator(f):
        @wraps(f)
        @context(f)
        def wrapper(context, *args, **kwargs):
            if test_func(context.user):
                return f(*args, **kwargs)
            raise PermissionDenied(error_message)
        return wrapper
    return decorator


def permission_required(perm, obj=None):
    def check_perms(user):
        if isinstance(perm, six.string_types):
            perms = (perm,)
        else:
            perms = perm

        if user.has_perms(perms, obj):
            return True
        return False
    return user_passes_test(check_perms, 'You do not have permission to perform this action')


login_required = user_passes_test(lambda u: u.is_authenticated, 'User must be authenticated')
