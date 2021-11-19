import graphene
from django.core.exceptions import PermissionDenied
from graphene import InputField, ClientIDMutation
from graphene.types.utils import yank_fields_from_attrs
from graphene_django.forms.mutation import DjangoModelFormMutation
from graphene_django.rest_framework.mutation import SerializerMutationOptions
from graphql_relay import from_global_id
from graphql_relay.connection.arrayconnection import offset_to_cursor
from rest_framework.exceptions import ErrorDetail

from autographql.auth.constants import PERMISSION_DENIED_MESSAGE
from autographql.auth.utils import get_model_permission, CREATE, DELETE, UPDATE
from autographql.converters import get_input_fields_from_serializer
from autographql.fields import OptimizedField
from autographql.types import ErrorType


class SerializerMutation(ClientIDMutation):
    class Meta:
        abstract = True

    errors = graphene.List(
        ErrorType,
        description='May contain more than one error for same field.'
    )

    @classmethod
    def __init_subclass_with_meta__(
            cls,
            serializer_class=None,
            method=None,
            _meta=None,
            **options
    ):

        if not serializer_class:
            raise Exception('serializer_class is required for the SerializerMutation')

        if method not in ('create', 'update'):
            raise Exception('meta method must be either create or update')

        serializer = serializer_class()
        input_fields = get_input_fields_from_serializer(serializer, method)

        if not _meta:
            _meta = SerializerMutationOptions(cls)
        _meta.serializer_class = serializer_class
        _meta.method = method

        input_fields = yank_fields_from_attrs(
            input_fields,
            _as=InputField,
        )
        super(SerializerMutation, cls).__init_subclass_with_meta__(_meta=_meta, input_fields=input_fields, **options)

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input):
        input = cls.convert_global_id_inputs(cls.Input, **input)
        serializer = cls.get_serializer(root, info, **input)

        if serializer.is_valid():
            return cls.perform_mutate(serializer, info)
        else:
            errors = [
                ErrorType(field=key, messages=value)
                for key, value in serializer.errors.items()
            ]

            return cls(errors=errors)

    @classmethod
    def get_serializer(cls, root, info, **input):
        return cls._meta.serializer_class(data=input)

    @classmethod
    def convert_global_id_inputs(cls, input_class, **input):
        cleaned_input = {}
        for field in input:
            value = input[field]
            input_field = getattr(input_class, field)
            if isinstance(input_field, graphene.GlobalID):
                cleaned_input[field] = int(from_global_id(input[field])[1]) if input[field] else None
            elif isinstance(value, dict):
                next_type = input_field.type
                if hasattr(next_type, 'of_type') and next_type.of_type:
                    next_type = next_type.of_type
                cleaned_input[field] = cls.convert_global_id_inputs(next_type, **value)
            else:
                cleaned_input[field] = input[field]
        return cleaned_input

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(errors=None, **obj)

    @classmethod
    def get_serializer_errors(cls, serializer):
        errors = [
            cls._get_serializer_errors(key, value)
            for key, value in serializer.errors.items()
        ]

        return errors

    @classmethod
    def _get_serializer_errors(cls, key, value):
        """Recursive helper to build a nested ErrorType object"""
        # Base case, ErrorDetail
        if isinstance(value, list):
            return ErrorType(field=key, messages=value)

        # Recursive call
        if isinstance(value, dict):
            return ErrorType(
                field=key,
                messages=[ErrorDetail('One or more nested fields is not valid.')],
                errors=[
                    cls._get_serializer_errors(key2, value2)
                    for key2, value2 in value.items()
                ]
            )


class CrudSerializerMutationOptions(SerializerMutationOptions):
    type = None
    permission = None


class CrudSerializerMutation(SerializerMutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls,
        permission=None,
        type=None,
        _meta=None,
        **options
    ):
        if not type:
            raise Exception('type is required for the CrudSerializerMutation')

        if not _meta:
            _meta = CrudSerializerMutationOptions(cls)

        _meta.type = type
        _meta.permission = permission

        super(CrudSerializerMutation, cls).__init_subclass_with_meta__(_meta=_meta, **options)


class CreateSerializerMutation(CrudSerializerMutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, **options):
        super(CreateSerializerMutation, cls).__init_subclass_with_meta__(
            method='create',
            **options
        )
        cls._meta.fields['edge'] = OptimizedField(cls._meta.type._meta.connection.Edge)

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input):
        # Permission check
        if not info.context.user.has_perm(cls._meta.permission):
            raise PermissionDenied(PERMISSION_DENIED_MESSAGE)

        cleaned_input = cls.convert_global_id_inputs(cls.Input, **input)
        return cls.create(root, info, **cleaned_input)

    @classmethod
    def create(cls, root, info, **input):
        serializer_class = cls._meta.serializer_class
        serializer = serializer_class(data=input, context={'request': info.context})
        if serializer.is_valid():
            instance = serializer.save()
        else:
            errors = cls.get_serializer_errors(serializer)
            return cls(errors=errors)

        edge = cls._meta.type._meta.connection.Edge(cursor=offset_to_cursor(0), node=instance)
        kwargs = {}
        kwargs['edge'] = edge

        return cls(errors=None, **kwargs)


class UpdateSerializerMutation(CrudSerializerMutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(cls, **options):
        super(UpdateSerializerMutation, cls).__init_subclass_with_meta__(
            method='update',
            **options,
        )
        cls._meta.fields['edge'] = OptimizedField(cls._meta.type._meta.connection.Edge)

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input):
        cleaned_input = cls.convert_global_id_inputs(cls.Input, **input)
        return cls.update(root, info, **cleaned_input)

    @classmethod
    def update(cls, root, info, **input):
        if 'id' not in input:
            return cls(errors=[
                ErrorType(
                    field='id',
                    messages=[ErrorDetail('The id field is required.')],
                )
            ])

        serializer_class = cls._meta.serializer_class
        model_class = serializer_class.Meta.model
        instance = model_class.objects.get(id=input['id'])

        # Permission check
        if not info.context.user.has_perm(cls._meta.permission, instance):
            raise PermissionDenied(PERMISSION_DENIED_MESSAGE)

        serializer = serializer_class(
            instance,
            data=input,
            context={'request': info.context},
            partial=True
        )
        if serializer.is_valid():
            instance = serializer.save()
        else:
            errors = cls.get_serializer_errors(serializer)
            return cls(errors=errors)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        kwargs = {}
        edge = cls._meta.type._meta.connection.Edge(cursor=offset_to_cursor(0), node=instance)
        kwargs['edge'] = edge

        return cls(errors=None, **kwargs)


class DjangoSerializerMutationFieldFactory(object):
    class Meta:
        type = None
        serializer_class = None

    @classmethod
    def get_create_field(cls):
        return cls.get_create_mutation().Field()

    @classmethod
    def get_create_mutation(cls):
        # Get required permissions
        add_permission = get_model_permission(cls.Meta.type._meta.model, CREATE)

        class CreateInstance(CreateSerializerMutation):
            class Meta:
                name = 'Create' + cls.Meta.serializer_class.Meta.model.__name__ + 'Payload'
                serializer_class = cls.Meta.serializer_class
                type = cls.Meta.type
                permission = add_permission

        return CreateInstance

    @classmethod
    def get_update_field(cls):
        return cls.get_update_mutation().Field()

    @classmethod
    def get_update_mutation(cls):
        # Get required permissions
        change_permission = get_model_permission(cls.Meta.type._meta.model, UPDATE)

        class UpdateInstance(UpdateSerializerMutation):
            class Meta:
                name = 'Update' + cls.Meta.serializer_class.Meta.model.__name__ + 'Payload'
                serializer_class = cls.Meta.serializer_class
                type = cls.Meta.type
                permission = change_permission

        return UpdateInstance

    @classmethod
    def get_delete_field(cls):
        return cls.get_delete_mutation().Field()

    @classmethod
    def get_delete_mutation(cls):
        # Get required permissions
        delete_permission = get_model_permission(cls.Meta.type._meta.model, DELETE)

        class DeleteInstance(ClientIDMutation):
            class Meta:
                name = 'Delete' + cls.Meta.serializer_class.Meta.model.__name__ + 'Payload'

            class Input:
                id = graphene.String()

            deletedId = graphene.String()
            count = graphene.Int()

            @classmethod
            def mutate_and_get_payload(inner_cls, root, info, **input):
                return inner_cls.delete(root, info, **input)

            @classmethod
            def delete(inner_cls, root, info, **input):
                deletedId = from_global_id(input['id'])[1]
                model_class = cls.Meta.serializer_class.Meta.model
                instance = model_class.objects.get(id=deletedId)

                # Permission check
                if not info.context.user.has_perm(delete_permission, instance):
                    raise PermissionDenied(PERMISSION_DENIED_MESSAGE)

                deleted = instance.delete()

                return DeleteInstance(
                    deletedId=input['id'],
                    count=deleted[0]
                )

        return DeleteInstance


class CoreDjangoModelFormMutation(DjangoModelFormMutation):
    class Meta:
        abstract = True

    errors = graphene.List(ErrorType)
