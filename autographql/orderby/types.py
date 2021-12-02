import logging
from functools import partial

import graphene
from graphene import Dynamic
from graphene.types.inputobjecttype import InputObjectTypeOptions
from graphene_django.registry import get_global_registry
from graphene_django.utils import get_model_fields

from autographql.orderby.enums import OrderByDirection

logger = logging.getLogger(__name__)


def get_input_type(field):
    registry = get_global_registry()
    related_model = field.related_model
    model_type = registry.get_type_for_model(related_model)
    return model_type._meta.orderby_input_type


class ModelAutoOrderByInputObjectTypeOptions(InputObjectTypeOptions):
    model = None


class AutoOrderByInputObjectType(graphene.InputObjectType):
    pass


class ModelAutoOrderByInputObjectType(AutoOrderByInputObjectType):
    """
    Generated input type that takes a model in its meta and returns a class
    that contains the model's fields as orderable fields.
    """
    @classmethod
    def __init_subclass_with_meta__(cls, fields=None, model=None, _meta=None, **options):
        if not _meta:
            _meta = ModelAutoOrderByInputObjectTypeOptions(cls)

        if not model:
            raise RuntimeError('model is required in Meta class for {0}'.format(cls))
        _meta.model = model

        registry = get_global_registry()

        orderby_fields = {}
        model_fields = get_model_fields(model)
        model_fields = filter(lambda m: m[0] in fields.keys(), model_fields)
        for name, field in model_fields:
            n, f = cls._get_orderby_input(registry, field)
            orderby_fields[n] = f

        if _meta.fields:
            _meta.fields.update(orderby_fields)
        else:
            _meta.fields = orderby_fields

        super().__init_subclass_with_meta__(_meta=_meta, **options)

    @classmethod
    def _get_orderby_input(cls, registry, node):
        """Helper to generate the order by input type"""
        # Dynamic field
        if isinstance(registry.get_converted_field(node), Dynamic):
            return node.name, graphene.InputField(partial(get_input_type, node))

        # Order by direction
        return node.name, graphene.InputField(OrderByDirection)
