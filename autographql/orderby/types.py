import logging
from functools import partial

import graphene
from bridgekeeper import perms
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import ManyToOneRel, ManyToManyRel
from django.db.models.constants import LOOKUP_SEP
from graphene import Dynamic
from graphene.types.inputobjecttype import InputObjectTypeOptions
from graphene_django.registry import get_global_registry
from graphene_django.utils import get_model_fields

from autographql.auth.utils import get_model_permission, VIEW
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
    def get_order_by(self, **kwargs):
        order_by = self._get_order_by(**kwargs)
        return order_by

    def _get_order_by(self, lookup_path='', **kwargs):
        """Recursive helper to build the order bys"""
        # Validate the input and make sure only one path is defined
        order_by = ''
        for field_name, field in self._meta.fields.items():
            attr_value = getattr(self, field_name, None)
            if not attr_value:
                # This filter is not set
                continue

            if order_by:
                # We already have a path defined?
                # User must have defined two paths in one order_by input
                raise ValidationError('Multiple paths found in a single orderBy input')

            if lookup_path:
                cur_path = LOOKUP_SEP.join([lookup_path, field_name])
            else:
                cur_path = field_name

            # Recursive call, AutoOrderByInputObjectType type
            if isinstance(attr_value, AutoOrderByInputObjectType):
                order_by = attr_value._get_order_by(cur_path, **kwargs)
                continue

            # Base case, ascending or descending
            if attr_value.value == 'desc':
                order_by = '-' + cur_path
            else:
                order_by = cur_path

        return order_by


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
            if f:
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
            if isinstance(node, ManyToOneRel) or isinstance(node, ManyToManyRel):
                # Array relationship, we don't handle these yet
                # TODO: Add aggregation and allow ordering by the aggregates
                return None, None
            return node.name, graphene.InputField(partial(get_input_type, node))

        # Order by direction
        return node.name, graphene.InputField(OrderByDirection)

    def _get_order_by(self, lookup_path='', context=None):
        user = context.user
        order_by = super()._get_order_by(lookup_path, context=context)
        if not order_by:
            return order_by

        # Permission check
        permission = get_model_permission(self._meta.model, VIEW)
        logger.debug('Checking permission {0} for user [{1}] to order on model [{2}]'.format(permission, user, self.__class__))

        if (permission in perms and perms[permission].is_possible_for(user)) or user.has_perm(permission):
            return order_by
        raise PermissionDenied('User {0} does not have permission to order using {1}'.format(str(user), self.__class__))
