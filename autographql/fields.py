from functools import partial

from django.db.models import Model, QuerySet
from graphene import Field, Dynamic
from graphene_django import DjangoObjectType, DjangoConnectionField


class AutoDjangoConnectionField(DjangoConnectionField):
    """
    Customized DjangoConnectionField to add order and filter fields
    """
    def __init__(self, type_, *args, **kwargs):
        kwargs.setdefault('order_by', Dynamic(lambda: type_._meta.orderby_input_type()))
        kwargs.setdefault('where', Dynamic(lambda: type_._meta.filter_input_type()))
        super().__init__(type_, *args, **kwargs)


class OptimizedDjangoConnectionField(AutoDjangoConnectionField):
    """
    Optimized connection field, applies all optimizations and filters to the queryset
    Should only be used at the root level queries
    """
    @classmethod
    def resolve_queryset(cls, connection, queryset, info, args):
        qs = super().resolve_queryset(connection, queryset, info, args)
        qs = connection._meta.node.optimize_queryset(qs, info, args)
        return qs


class OptimizedField(Field):
    def resolve_optimized_field(self, parent_resolver, root, info, **args):
        if not issubclass(self.type, DjangoObjectType):
            return parent_resolver(root, info, **args)

        if hasattr(parent_resolver, 'args'):
            attr_name = parent_resolver.args[0]
            value = getattr(root, attr_name)
        else:
            value = parent_resolver(root, info, **args)

        if isinstance(value, Model):
            # Model instance, need to use it to get new queryset
            return self.type.get_optimized_queryset(info, args).get(pk=value.pk)
        elif isinstance(value, QuerySet):
            # Received queryset, optimize it
            return self.type.optimize_queryset(value, info, args).get()

        return value

    def get_resolver(self, parent_resolver):
        if self.resolver:
            return self.resolver

        return partial(self.resolve_optimized_field, parent_resolver)
