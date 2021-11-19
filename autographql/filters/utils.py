from functools import partial

import graphene
from graphene_django.registry import get_global_registry
from graphene_django.utils import get_model_fields

from autographql.filters.converters import get_input_type_from_lookup
from autographql.filters.fields import LogicalAndInputField, LogicalOrInputField, LogicalNotInputField
from autographql.filters.types import AutoFilterInputObjectType, AuthAutoFilterInputObjectType
from autographql.utils import to_pascal_case


def get_input_type(field, registry):
    related_model = field.related_model
    model_type = registry.get_type_for_model(related_model)
    return model_type._meta.filter_input_type


def convert_model_to_input_type(model, registry, django_fields):
    if not registry:
        registry = get_global_registry()
    model_fields = get_model_fields(model)
    # We only will include fields that are included in the model type to avoid exposing anything we shouldn't
    model_fields = filter(lambda m: m[0] in django_fields.keys(), model_fields)
    fields = {}

    # Add AND, OR, and NOT fields
    def get_self_input_type():
        model_type = registry.get_type_for_model(model)
        return model_type._meta.filter_input_type
    fields['and'] = LogicalAndInputField(
        name='_and',
        of_type=get_self_input_type,
        description='Logical AND is applied to all filters in the contained list.'
    )
    fields['or'] = LogicalOrInputField(
        name='_or',
        of_type=get_self_input_type,
        description='Logical OR is applied to all filters in the contained list.'
    )
    fields['not'] = LogicalNotInputField(
        get_self_input_type,
        name='_not',
        description='Logical NOT is applied to the result of contained the filter.'
    )

    # Add model fields
    for name, field in model_fields:
        converted = django_fields[name]
        if isinstance(converted, graphene.Dynamic):
            fields[name] = graphene.InputField(partial(get_input_type, field, registry))
        else:
            # Copy the converted class for this field from the model type
            lookup_fields = {}
            for lookup in field.get_lookups().values():
                # Need to instantiate a dummy object here because singledispatch takes instances
                dummy = lookup.__new__(lookup)
                n, f = get_input_type_from_lookup(dummy, field)
                lookup_fields[n] = f
            fields[name] = graphene.InputField(
                type(
                    model.__name__ + to_pascal_case(field.attname) + 'FilterInput',
                    (AutoFilterInputObjectType,),
                    {
                        'Meta': {
                            'model': model
                        },
                        **lookup_fields
                    }
                )
            )

    return type(model.__name__ + 'FilterInput', (AuthAutoFilterInputObjectType,), {
        'Meta': {
            'model': model
        },
        **fields
    })
