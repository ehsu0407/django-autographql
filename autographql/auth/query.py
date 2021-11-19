from bridgekeeper import perms
from bridgekeeper.rules import BinaryCompositeRule, Attribute, Relation, ManyRelation
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Prefetch
from django.db.models.fields.related import ForeignKey

from autographql.auth.utils import get_model_permission, VIEW


class AuthQueryOptimizer(object):
    def __init__(self, info):
        self.root_info = info
        self.user = info.context.user

    def optimize(self, queryset):
        permission = get_model_permission(queryset.model, VIEW)
        if permission not in perms:
            # Nothing to optimize
            return queryset

        rule = perms[permission]

        queryset = self.optimize_queryset(queryset, rule)
        return queryset

    def optimize_queryset(self, queryset, rule):
        store = AuthQueryOptimizerStore()
        queryset = self.optimize_queryset_rule(queryset, store, rule)
        return store.optimize(queryset)

    def get_queryset(self, model):
        return model.objects.for_user(self.user)

    def optimize_queryset_rule(self, queryset, store, rule):
        """Recursive helper to process rule tree"""
        # BinaryCompositeRule
        if isinstance(rule, BinaryCompositeRule):
            # Left and right, recursive call
            queryset = self.optimize_queryset_rule(queryset, store, rule.left)
            queryset = self.optimize_queryset_rule(queryset, store, rule.right)

        # Relation rule
        elif isinstance(rule, Relation):
            model_field = self.get_model_field_from_name(queryset.model, rule.attr)
            queryset = queryset.prefetch_related(
                Prefetch(
                    rule.attr,
                    queryset=self.optimize_queryset(
                        self.get_queryset(model_field.related_model),
                        rule.rule,
                    )
                )
            )

        # ManyRelation rule
        elif isinstance(rule, ManyRelation):
            attr = queryset.model.__class__._meta.get_field(rule.query_attr,).get_accessor_name()
            model_field = self.get_model_field_from_name(queryset.model, attr)
            queryset = queryset.prefetch_related(
                Prefetch(
                    attr,
                    queryset=self.optimize_queryset(
                        self.get_queryset(model_field.related_model),
                        rule.rule,
                    )
                )
            )

        # Attribute rule
        elif isinstance(rule, Attribute):
            model_field = self.get_model_field_from_name(queryset.model, rule.attr)
            store.optimize_field(model_field, rule.attr)

        return queryset
    
    def get_model_field_from_name(self, model, name):
        try:
            return model._meta.get_field(name)
        except FieldDoesNotExist:
            descriptor = model.__dict__.get(name)
            if not descriptor:
                return None
            return getattr(descriptor, 'rel', None) \
                   or getattr(descriptor, 'related', None)


class AuthQueryOptimizerStore(object):
    def __init__(self):
        self.select_list = []
        self.prefetch_list = []
        self.only_list = []

    def optimize(self, queryset):
        # Add the selects to the queryset
        if len(self.select_list) > 0:
            queryset = queryset.select_related(*self.select_list)

        # Add the prefetches to the queryest
        if len(self.prefetch_list) > 0:
            queryset = queryset.prefetch_related(*self.prefetch_list)

        # Add the onlys to the queryset
        # .only overwrites old onlys so we need to pull the existing onlys from the queryset
        if len(self.only_list) > 0:
            only_list = self.only_list
            loaded_field_names = queryset.query.get_loaded_field_names()
            if loaded_field_names:
                only_list = list(loaded_field_names[queryset.model]) + only_list
                queryset = queryset.only(*only_list)

        return queryset
    
    def optimize_field(self, model_field, field):
        if self._is_foreign_key_id(model_field, field):
            self.only(field)
            return True
        if model_field.many_to_one or model_field.one_to_one:
            self.select_related(field)
            return True
        if model_field.one_to_many or model_field.many_to_many:
            self.prefetch_related(field)
            return True
        return False

    def only(self, field):
        if field not in self.only_list:
            self.only_list.append(field)

    def select_related(self, field):
        if field not in self.select_list:
            self.select_list.append(field)

    def prefetch_related(self, field):
        if field not in self.prefetch_list:
            self.prefetch_list.append(field)

    def _is_foreign_key_id(self, model_field, name):
        return (
            isinstance(model_field, ForeignKey) and
            model_field.name != name and
            model_field.get_attname() == name
        )
