from collections import OrderedDict
from functools import cached_property

import graphene
from django.db.models import Manager
from graphene import String, List
from graphene_django import DjangoObjectType
from graphene_django.types import ErrorType as _ErrorType, DjangoObjectTypeOptions, construct_fields

from graphene_django.filter.utils import get_filtering_args_from_filterset

from autographql.filters.types import ModelAutoFilterInputObjectType
from autographql.optimizer import query
from autographql.orderby.types import ModelAutoOrderByInputObjectType


class ErrorType(_ErrorType):
    errors = graphene.List(lambda: ErrorType)


class AutoDjangoObjectTypeOptions(DjangoObjectTypeOptions):
    @cached_property
    def filter_input_type(self):
        return type(self.model.__name__ + 'FilterInput', (ModelAutoFilterInputObjectType,), {
            'Meta': {
                'model': self.model,
                'fields': self.fields,
            },
        })

    @cached_property
    def orderby_input_type(self):
        return type(self.model.__name__ + 'OrderByInput', (ModelAutoOrderByInputObjectType,), {
            'Meta': {
                'model': self.model,
                'fields': self.fields,
            },
        })


class AutoDjangoObjectType(DjangoObjectType):
    """
    Cast select_related to queryset for ForeignKeys of model
    """
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
            cls,
            _meta=None,
            **options
    ):
        if not _meta:
            _meta = AutoDjangoObjectTypeOptions(cls)

        super().__init_subclass_with_meta__(
            _meta=_meta,
            **options
        )

    @classmethod
    def get_optimized_queryset(cls, info, args=OrderedDict()):
        queryset = cls._meta.model.objects
        return cls.optimize_queryset(queryset, info, args)

    @classmethod
    def optimize_queryset(cls, queryset, info, args=OrderedDict()):
        queryset = cls.get_filtered_queryset(queryset, info, args)
        queryset = query.QueryOptimizer(info).optimize(queryset)

        return queryset

    @classmethod
    def get_filtered_queryset(cls, queryset, info, args):
        queryset = cls.get_queryset(queryset, info)

        if hasattr(queryset, 'for_user'):
            queryset = queryset.for_user(info.context.user)

        # Apply filterset class if it exists
        filterset_class = cls._meta.filterset_class
        if filterset_class:
            filtering_args = get_filtering_args_from_filterset(filterset_class, cls)
            filter_kwargs = {k: v for k, v in args.items() if k in filtering_args}
            if len(filter_kwargs) > 0:
                queryset = filterset_class(
                    data=filter_kwargs,
                    queryset=queryset,
                    request=info.context,
                ).qs

        # Apply where filters if they exist
        if 'where' in args and args['where']:
            filter_input = args['where']
            lookup = filter_input.get_q_lookup(context=info.context)
            if lookup:
                queryset = queryset.filter(lookup)

        # Apply order by if it exists
        if 'order_by' in args and args['order_by']:
            order_by_input = args['order_by']
            order_by = []
            for obi in order_by_input:
                ob = obi.get_order_by(context=info.context)
                if ob:
                    order_by.append(ob)
            if order_by:
                queryset = queryset.order_by(*order_by)

        if isinstance(queryset, Manager):
            queryset = queryset.all()

        return queryset

    @classmethod
    def get_node(cls, info, id):
        try:
            queryset = cls.get_optimized_queryset(info)
            return queryset.get(pk=id)
        except cls._meta.model.DoesNotExist:
            return None
