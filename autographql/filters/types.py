import logging
from functools import partial
from inspect import isclass

import graphene
from bridgekeeper import perms
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.db.models import Q, Transform, Lookup
from django.db.models.constants import LOOKUP_SEP
from django.db.models.query_utils import RegisterLookupMixin
from graphene import InputField, List, Dynamic
from graphene.types.enum import EnumMeta
from graphene.types.inputobjecttype import InputObjectTypeOptions
from graphene.types.scalars import ScalarOptions
from graphene_django.registry import get_global_registry
from graphene_django.utils import get_model_fields

from autographql.auth.utils import get_model_permission, VIEW
from autographql.filters.converters import get_input_type_from_lookup
from autographql.filters.fields import LogicalInputField, AND, OR, NOT, LogicalAndInputField, LogicalOrInputField, \
    LogicalNotInputField
from autographql.utils import to_pascal_case

logger = logging.getLogger(__name__)


def get_input_type(field):
    registry = get_global_registry()
    related_model = field.related_model
    model_type = registry.get_type_for_model(related_model)
    return model_type._meta.filter_input_type


class ModelAutoFilterInputObjectTypeOptions(InputObjectTypeOptions):
    model = None


class AutoFilterInputObjectType(graphene.InputObjectType):
    def get_q_lookup(self, **kwargs):
        lookups = self._get_lookups(**kwargs)
        lookup = self._get_q_lookup_helper(lookups)
        return lookup

    def _get_q_lookup_helper(self, lookup, operator=AND):
        """Recursive helper to build the Q lookup"""
        # Base case, we have a tuple
        if isinstance(lookup, tuple):
            args = {lookup[0]: lookup[1]}
            return Q(**args)

        # We have a list, recur for each element and and them together
        if isinstance(lookup, list) and len(lookup) >= 1:
            result = None
            for l in lookup:
                r = self._get_q_lookup_helper(l)
                if not result:
                    result = r
                else:
                    if operator == AND:
                        result = result & r
                    elif operator == OR:
                        result = result | r
            return result

        # We have a dict, use the logical operator stored to process the result
        if isinstance(lookup, dict) and lookup:
            op, records = list(lookup.items())[0]
            if op == NOT:
                l = self._get_q_lookup_helper(records)
                return ~l
            else:
                return self._get_q_lookup_helper(records, op)

    def _is_scalar(self, field):
        t = field.type
        if isinstance(t, List):
            t = t.of_type

        if hasattr(t, '_meta') and isinstance(t._meta, ScalarOptions):
            return True
        return False

    def _get_lookups(self, lookup_path='', **kwargs):
        """Helper function to build lookups"""
        lookups = []
        for field_name, field in self._meta.fields.items():
            attr_value = getattr(self, field_name, None)
            if not attr_value:
                # This filter is not set
                continue

            if lookup_path:
                cur_path = LOOKUP_SEP.join([lookup_path, field_name])
            else:
                cur_path = field_name

            if self._is_scalar(field):
                # Base case, scalar value or list of scalar value
                lookups.append((cur_path, attr_value))
                continue

            if isinstance(field.type, EnumMeta):
                # Base case, enum type
                lookups.append((cur_path, attr_value.value))
                continue

            if isinstance(attr_value, AutoFilterInputObjectType):
                # Recursive call to get the lookups
                child_lookups = attr_value._get_lookups(cur_path, **kwargs)
                lookups += child_lookups
                continue

            if isinstance(field.type, LogicalInputField):
                operator = field.type.get_operator()
                operator_lookups = {operator: []}
                for child in attr_value:
                    child_lookups = child._get_lookups(lookup_path, **kwargs)
                    operator_lookups[operator] += child_lookups
                lookups.append(operator_lookups)
                continue

            raise RuntimeError('Unknown lookup field type found: {0}'.format(str(field.type)))

        return lookups


class ModelAutoFilterInputObjectType(AutoFilterInputObjectType):
    """
    Input object that only allows users who have permission to view the model to
    use it as a filter.
    """
    @classmethod
    def __init_subclass_with_meta__(cls, fields=None, model=None, _meta=None, **options):
        if not _meta:
            _meta = ModelAutoFilterInputObjectTypeOptions(cls)

        if not model:
            raise RuntimeError('model is required in Meta class for {0}'.format(cls))
        _meta.model = model

        registry = get_global_registry()

        # Add AND, OR, and NOT fields
        def get_self_input_type():
            model_type = registry.get_type_for_model(model)
            return model_type._meta.filter_input_type

        input_fields = {}
        input_fields['and'] = InputField.mounted(LogicalAndInputField(
            name='_and',
            of_type=get_self_input_type,
        ))
        input_fields['or'] = InputField.mounted(LogicalOrInputField(
            name='_or',
            of_type=get_self_input_type,
        ))
        input_fields['not'] = InputField.mounted(LogicalNotInputField(
            get_self_input_type,
            name='_not',
        ))

        model_fields = get_model_fields(model)
        model_fields = filter(lambda m: m[0] in fields.keys(), model_fields)
        for name, field in model_fields:
            n, f = cls._get_filter_input(registry, model, field, name=model.__name__)
            input_fields[n] = f

        if _meta.fields:
            _meta.fields.update(input_fields)
        else:
            _meta.fields = input_fields

        super().__init_subclass_with_meta__(_meta=_meta, **options)

    @classmethod
    def _convert_input_type_from_lookup(cls, dummy, field):
        try:
            return get_input_type_from_lookup(dummy, field)
        except ImproperlyConfigured as e:
            logger.warning(str(e))
            return None, None

    @classmethod
    def _get_filter_input(cls, registry, model, node, name, field=None):
        """Recursive helper to generate the input filters"""
        # Base case, dynamic field
        if isinstance(registry.get_converted_field(node), Dynamic):
            return node.name, graphene.InputField(partial(get_input_type, node))

        # Base case, field is of a lookup type
        if isclass(node) and issubclass(node, Lookup):
            dummy = node.__new__(node)
            return cls._convert_input_type_from_lookup(dummy, field)

        # field registers transforms
        if isclass(node) and issubclass(node, Transform):
            lookups = node.get_lookups()
            if not lookups:
                dummy = node.__new__(node)
                return cls._convert_input_type_from_lookup(dummy, field)

            lookup_fields = {}
            for lookup_name, lookup in lookups.items():
                next_name = name + to_pascal_case(lookup_name)
                n, f = cls._get_filter_input(registry, model, lookup, name=next_name, field=lookup)
                if f:
                    lookup_fields[n] = f

            return node.lookup_name, graphene.InputField(
                type(
                    name + to_pascal_case(node.lookup_name) + 'FilterInput',
                    (AutoFilterInputObjectType,),
                    lookup_fields
                )
            )

        # field registers lookups
        if isinstance(node, RegisterLookupMixin):
            lookup_fields = {}
            field_name = node.attname
            next_name = name + to_pascal_case(field_name)

            lookups = node.get_lookups()
            for lookup in lookups.values():
                n, f = cls._get_filter_input(registry, model, lookup, name=next_name, field=node)
                if f:
                    lookup_fields[n] = f

            return field_name, graphene.InputField(
                type(
                    next_name + 'FilterInput',
                    (AutoFilterInputObjectType,),
                    lookup_fields
                )
            )

        raise RuntimeError('Failed to generate filter tree')

    def _get_lookups(self, lookup_path='', context=None):
        user = context.user
        lookups = super()._get_lookups(lookup_path, context=context)
        if not lookups:
            return lookups

        # Permission check
        permission = get_model_permission(self._meta.model, VIEW)
        logger.debug('Checking permission {0} for user [{1}] to use filter [{2}]'.format(permission, user, self.__class__))

        if (permission in perms and perms[permission].is_possible_for(user)) or user.has_perm(permission):
            return lookups
        raise PermissionDenied('User {0} does not have permission to use the {1} filter'.format(str(user), self.__class__))
