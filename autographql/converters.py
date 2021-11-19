import graphene
from django.db import models
from graphene import Dynamic
from graphene_django import DjangoListField
from graphene_django.registry import get_global_registry
from graphene_django.rest_framework.serializer_converter import get_graphene_type_from_serializer_field
from rest_framework import serializers
from rest_framework.fields import HiddenField
from graphene_django.converter import convert_django_field, get_django_field_description

from autographql.base_types import Binary
from autographql.fields import AutoDjangoConnectionField


@get_graphene_type_from_serializer_field.register(serializers.RelatedField)
def convert_related_field_to_global_id(field):
    return graphene.GlobalID


@get_graphene_type_from_serializer_field.register(serializers.IntegerField)
def convert_serializer_field_to_int(field):
    if field.field_name == 'id':
        return graphene.GlobalID
    return graphene.Int


@get_graphene_type_from_serializer_field.register(serializers.ChoiceField)
def convert_serializer_field_to_enum(field):
    """This was added in graphene-django 2.6.0, causes multiple mutations made from a serializer to break"""
    return graphene.String


def convert_serializer_field(field, method, is_input=True, force_required=None):
    """
    Converts a django rest frameworks field to a graphql field
    and marks the field as required if we are creating an input type
    and the field itself is required
    """

    graphql_type = get_graphene_type_from_serializer_field(field)

    args = []
    if force_required is not None:
        required = force_required
    else:
        required = is_input and field.required
    kwargs = {"description": field.help_text, "required": required}

    # if it is a tuple or a list it means that we are returning
    # the graphql type and the child type
    if isinstance(graphql_type, (list, tuple)):
        kwargs["of_type"] = graphql_type[1]
        graphql_type = graphql_type[0]

    if isinstance(field, serializers.ModelSerializer):
        if is_input:
            graphql_type = convert_serializer_to_input_type(field.__class__, method)
        else:
            global_registry = get_global_registry()
            field_model = field.Meta.model
            args = [global_registry.get_type_for_model(field_model)]
    elif isinstance(field, serializers.ListSerializer):
        field = field.child
        if is_input:
            kwargs["of_type"] = convert_serializer_to_input_type(field.__class__, method)
        else:
            del kwargs["of_type"]
            global_registry = get_global_registry()
            field_model = field.Meta.model
            args = [global_registry.get_type_for_model(field_model)]

    return graphql_type(*args, **kwargs)


def get_input_fields_from_serializer(serializer, method):
    items = {}
    for name, field in serializer.fields.items():
        # Always skip hidden fields
        if isinstance(field, HiddenField):
            continue

        # Skip read only fields except for the id field
        if field.read_only and name != 'id':
            continue

        if method == 'create':
            # id field should be skipped on create
            if name == 'id':
                continue

            items[name] = convert_serializer_field(field, method)

        elif method == 'update':
            # all fields should be not required except id
            if name == 'id':
                items[name] = convert_serializer_field(field, method, force_required=True)
                continue
            items[name] = convert_serializer_field(field, method, force_required=False)

        else:
            raise ValueError('method must be create or update')

    return items


def convert_serializer_to_input_type(serializer_class, method):
    """
    Modified converter to cache the serializer input type and reuse it
    If we don't cache it, graphene_django will recreate the input type for nested serializers
    each time which results in the same input type being declared twice
    """
    global_registry = get_global_registry()
    if method == 'create':
        get_field = global_registry.get_serializer_create_input_field
        register_field = global_registry.register_serializer_create_input_field
    elif method == 'update':
        get_field = global_registry.get_serializer_update_input_field
        register_field = global_registry.register_serializer_update_input_field
    else:
        raise ValueError('method argument must be either create or update')

    input_type = get_field(serializer_class)
    if input_type:
        return input_type

    serializer = serializer_class()

    items = get_input_fields_from_serializer(serializer, method)

    input_type = type(
        "{}{}Input".format(serializer.__class__.__name__, method.capitalize()),
        (graphene.InputObjectType,),
        items,
    )
    register_field(serializer_class, input_type)

    return input_type


@convert_django_field.register(models.ManyToManyField)
@convert_django_field.register(models.ManyToManyRel)
@convert_django_field.register(models.ManyToOneRel)
def convert_field_to_list_or_connection(field, registry=None):
    model = field.related_model

    def dynamic_type():
        _type = registry.get_type_for_model(model)
        if not _type:
            return

        if isinstance(field, models.ManyToManyField):
            description = get_django_field_description(field)
        else:
            description = get_django_field_description(field.field)

        # If there is a connection, we should transform the field
        # into a DjangoConnectionField
        if _type._meta.connection:
            return AutoDjangoConnectionField(_type, required=True, description=description)

        return DjangoListField(
            _type,
            required=True,  # A Set is always returned, never None.
            description=description,
        )

    return Dynamic(dynamic_type)


@convert_django_field.register(models.BinaryField)
def convert_binary_to_string(field, registry=None):
    return Binary(
        description=get_django_field_description(field),
        required=not field.null,
    )
