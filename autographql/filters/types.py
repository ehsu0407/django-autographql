import logging

import graphene
from bridgekeeper import perms
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.constants import LOOKUP_SEP
from graphene.types.inputobjecttype import InputObjectTypeOptions
from graphene.types.scalars import ScalarOptions

from autographql.auth.utils import get_model_permission, VIEW
from autographql.filters.fields import LogicalInputField, AND, OR, NOT


logger = logging.getLogger(__name__)


class AuthAutoInputObjectTypeOptions(InputObjectTypeOptions):
    model = None


class AutoFilterInputObjectType(graphene.InputObjectType):
    def get_q_lookup(self):
        lookups = self._get_lookups()
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

    def _get_lookups(self, lookup_path='', **kwargs):
        """Helper function to build lookups"""
        lookups = []
        for field_name, field in self._meta.fields.items():
            if lookup_path:
                cur_path = LOOKUP_SEP.join([lookup_path, field_name])
            else:
                cur_path = field_name

            attr_value = getattr(self, field_name, None)
            if not attr_value:
                # This filter is not set
                continue

            if hasattr(field.type, '_meta') and isinstance(field.type._meta, ScalarOptions):
                # Base case, scalar value
                lookups.append((cur_path, attr_value))
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

        return lookups


class AuthAutoFilterInputObjectType(AutoFilterInputObjectType):
    """
    Input object that only allows users who have permission to view the model to
    use it as a filter.
    """
    @classmethod
    def __init_subclass_with_meta__(cls, model=None, container=None, _meta=None, **options):
        if not _meta:
            _meta = AuthAutoInputObjectTypeOptions(cls)

        _meta.model = model
        super().__init_subclass_with_meta__(container=None, _meta=_meta, **options)

    def get_q_lookup(self, user=None):
        lookups = self._get_lookups(user=user)
        lookup = self._get_q_lookup_helper(lookups)
        return lookup

    # def _get_lookups(self, lookup_path='', user=None):
    #     lookups = super()._get_lookups(lookup_path, user=user)
    #     if not lookups:
    #         return lookups
    #     # Permission check
    #     permission = get_model_permission(self._meta.model, VIEW)
    #     logger.debug('Checking permission {0} for user [{1}] to use filter [{2}]'.format(permission, user, self.__class__))
    #
    #     if (permission in perms and perms[permission].is_possible_for(user)) or user.has_perm(permission):
    #         return lookups
    #     raise PermissionDenied('User {0} does not have permission to use the {1} filter'.format(str(user), self.__class__))
