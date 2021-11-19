from collections import OrderedDict

import graphene
from django.db.models import Manager
from graphene import String, List
from graphene_django import DjangoObjectType
from graphene_django.types import ErrorType as _ErrorType, DjangoObjectTypeOptions, construct_fields

from graphene_django.filter.utils import get_filtering_args_from_filterset

from autographql.filters.utils import convert_model_to_input_type
from autographql.optimizer import query


class ErrorType(_ErrorType):
    errors = graphene.List(lambda: ErrorType)


class OrderByType(List):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('of_type', String)
        super().__init__(*args, **kwargs)


class AutoDjangoObjectTypeOptions(DjangoObjectTypeOptions):
    filter_type = None


class AutoDjangoObjectType(DjangoObjectType):
    """
    Cast select_related to queryset for ForeignKeys of model
    """
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
            cls,
            model=None,
            registry=None,
            skip_registry=False,
            only_fields=None,  # deprecated in favour of `fields`
            fields=None,
            exclude_fields=None,  # deprecated in favour of `exclude`
            exclude=None,
            filter_fields=None,
            filterset_class=None,
            connection=None,
            connection_class=None,
            use_connection=None,
            interfaces=(),
            convert_choices_to_enum=True,
            _meta=None,
            **options
    ):
        if not _meta:
            _meta = AutoDjangoObjectTypeOptions(cls)

        django_fields = construct_fields(model, registry, fields, exclude, convert_choices_to_enum)
        input_type = convert_model_to_input_type(model, registry, django_fields)
        _meta.filter_input_type = input_type

        super().__init_subclass_with_meta__(
            model=model,
            registry=registry,
            skip_registry=skip_registry,
            only_fields=only_fields,  # deprecated in favour of `fields`
            fields=fields,
            exclude_fields=exclude_fields,  # deprecated in favour of `exclude`
            exclude=exclude,
            filter_fields=filter_fields,
            filterset_class=filterset_class,
            connection=connection,
            connection_class=connection_class,
            use_connection=use_connection,
            interfaces=interfaces,
            convert_choices_to_enum=convert_choices_to_enum,
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
            user = info.context.user
            lookup = filter_input.get_q_lookup(user)
            if lookup:
                queryset = queryset.filter(lookup)

        # Apply order by if it exists
        if 'orderBy' in args and args['orderBy']:
            order_by_input = args['orderBy']
            queryset = queryset.order_by(*order_by_input)

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
