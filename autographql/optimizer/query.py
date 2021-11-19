import functools

from django.db.models import ManyToOneRel, Prefetch
from graphene import GlobalID
from graphene.types.mutation import MutationOptions
from graphene.types.resolver import attr_resolver, dict_or_attr_resolver, dict_resolver
from graphene_django import DjangoObjectType
from graphene_django_optimizer.query import QueryOptimizer as _QueryOptimizer
from graphene_django_optimizer.query import QueryOptimizerStore as _QueryOptimizerStore
from graphql.execution.values import get_argument_values
from graphql.language.ast import (
    FragmentSpreadNode,
    InlineFragmentNode,
)

from autographql.auth.query import AuthQueryOptimizer
from autographql.optimizer.utils import remove_prefix, combine_querysets


class QueryOptimizer(_QueryOptimizer):
    def __init__(self, info):
        super(QueryOptimizer, self).__init__(info)
        self.auth_optimizer = AuthQueryOptimizer(info)
        self.variable_values = info.variable_values

    def optimize(self, queryset):
        queryset = super().optimize(queryset)
        queryset = self.auth_optimizer.optimize(queryset)
        queryset = combine_querysets([queryset])
        return queryset

    def _optimize_gql_selections(self, field_type, field_ast):
        store = QueryOptimizerStore()
        store.abort_only_optimization()

        # Optimize queryset
        selection_set = field_ast.selection_set
        if not selection_set:
            return store
        optimized_fields_by_model = {}
        schema = self.root_info.schema
        graphql_type = schema.get_type(field_type.name)
        possible_types = self._get_possible_types(graphql_type)
        for selection in selection_set.selections:
            if isinstance(selection, InlineFragmentNode):
                self.handle_inline_fragment(
                    selection, schema, possible_types, store)
            else:
                name = selection.name.value
                if isinstance(selection, FragmentSpreadNode):
                    self.handle_fragment_spread(store, name, field_type)
                else:
                    for possible_type in possible_types:
                        selection_field_def = possible_type.fields.get(name)
                        if not selection_field_def:
                            continue

                        graphene_type = possible_type.graphene_type
                        # Check if graphene type is a relay connection or a relay edge or mutation payload
                        if hasattr(graphene_type._meta, 'node') or (
                            hasattr(graphene_type, 'cursor') and
                            hasattr(graphene_type, 'node')
                        ) or (
                            isinstance(graphene_type._meta, MutationOptions)
                        ):
                            relay_store = self._optimize_gql_selections(
                                self._get_type(selection_field_def),
                                selection,
                            )
                            store.append(relay_store)
                            try:
                                from django.db.models import DEFERRED  # noqa: F401
                            except ImportError:
                                store.abort_only_optimization()
                        else:
                            model = getattr(graphene_type._meta, 'model', None)
                            # if model and name not in optimized_fields_by_model:
                            # Always optimize in case of duplicate field names
                            if model:
                                # Its possible that model is None like in the case of processing the pageInfo field
                                field_model = optimized_fields_by_model[name] = model
                                if field_model == model:
                                    self._optimize_field(
                                        store,
                                        model,
                                        selection,
                                        selection_field_def,
                                        possible_type,
                                    )
        return store

    def _get_name_from_resolver(self, resolver):
        resolver_fn = resolver
        optimization_hints = self._get_optimization_hints(resolver)
        if optimization_hints:
            name = optimization_hints.model_field
            if name:
                return name

        while isinstance(resolver_fn, functools.partial):
            if hasattr(resolver_fn, 'func') and (
                    resolver_fn.func == attr_resolver or
                    resolver_fn.func == dict_resolver or
                    resolver_fn.func == dict_or_attr_resolver
            ):
                return resolver_fn.args[0]

            resolver_fn = resolver_fn.args[0]

        if self._is_resolver_for_id_field(resolver):
            return 'id'

        # Unknown resolver type, just extract the field name from the resolver name
        return remove_prefix(resolver_fn.__name__, 'resolve_')

    def _optimize_field_by_name(self, store, model, selection, field_def):
        name = self._get_name_from_resolver(field_def.resolve)
        if not name:
            return False
        model_field = self._get_model_field_from_name(model, name)
        if not model_field:
            return False
        if self._is_foreign_key_id(model_field, name):
            store.only(name)
            return True
        if (
                model_field.many_to_one or
                model_field.one_to_one or
                model_field.one_to_many or
                model_field.many_to_many
        ):
            node_type = self._get_type(field_def)
            field_store = self._optimize_gql_selections(
                node_type,
                selection,
                # parent_type,
            )

            if isinstance(model_field, ManyToOneRel):
                field_store.only(model_field.field.name)

            arguments = get_argument_values(field_def, selection, self.variable_values)
            related_queryset = self.get_queryset(node_type, arguments)
            store.prefetch_related(name, field_store, related_queryset)
            return True
        if not model_field.is_relation:
            store.only(name)
            return True
        return False

    def get_queryset(self, node_type, args):
        gtype = node_type.graphene_type

        if hasattr(gtype._meta, 'node'):
            gtype = gtype._meta.node

        model = gtype._meta.model
        queryset = gtype.get_filtered_queryset(model.objects, self.root_info, args)
        return self.auth_optimizer.optimize(queryset)

    def _is_resolver_for_id_field(self, resolver):
        resolve_id = DjangoObjectType.resolve_id
        # For python 2 unbound method:
        if hasattr(resolve_id, 'im_func'):
            resolve_id = resolve_id.im_func

        # Check to see if its a relay GlobalID
        resolver_fn = resolver
        if isinstance(resolver_fn, functools.partial):
            if resolver_fn.func == GlobalID.id_resolver:
                resolver_fn = resolver_fn.args[0]

        return resolver_fn == resolve_id


class QueryOptimizerStore(_QueryOptimizerStore):
    def optimize_queryset(self, queryset):
        if len(self.select_list) > 0:
            # An empty select_list will have the queryset select everything possible
            queryset = queryset.select_related(*self.select_list)
        if len(self.prefetch_list) > 0:
            queryset = queryset.prefetch_related(*self.prefetch_list)

        if self.only_list:
            queryset = queryset.only(*self.only_list)
        return queryset

    def prefetch_related(self, name, store, queryset):
        """Overridden prefetch_related always use the prefetch object"""
        queryset = store.optimize_queryset(queryset)
        self.prefetch_list.append(Prefetch(name, queryset=queryset))
