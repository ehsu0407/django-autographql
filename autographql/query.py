from graphene import relay
from graphene.utils.str_converters import to_snake_case

from autographql.fields import OptimizedDjangoConnectionField


class DjangoQueryFactory(object):
    class Meta:
        type = None
        retrieve_attribute_name = None
        list_attribute_name = None
        retrieve = True
        list = True
        resolve_decorators = []

    @classmethod
    def build_query(cls):
        if cls.Meta.type is None:
            # type must be defined
            raise Exception('type meta must be defined!')

        if hasattr(cls.Meta, 'retrieve') and cls.Meta.retrieve is False:
            # No retrieve
            retrieve_attribute_name = None
        elif hasattr(cls.Meta, 'retrieve_attribute_name') and cls.Meta.retrieve_attribute_name is not None:
            retrieve_attribute_name = cls.Meta.retrieve_attribute_name
        else:
            # Default to snake case model name
            retrieve_attribute_name = to_snake_case(cls.Meta.type._meta.model.__name__)

        if hasattr(cls.Meta, 'list') and cls.Meta.list is False:
            # No list
            list_attribute_name = None
        elif hasattr(cls.Meta, 'list_attribute_name') and cls.Meta.list_attribute_name is not None:
            list_attribute_name = cls.Meta.list_attribute_name
        else:
            # Default to list_ + snake cased model name
            list_attribute_name = 'list_' + to_snake_case(cls.Meta.type._meta.model.__name__)

        class Query(object):
            if retrieve_attribute_name is not None:
                vars()[retrieve_attribute_name] = relay.Node.Field(cls.Meta.type)

            if list_attribute_name is not None:
                vars()[list_attribute_name] = OptimizedDjangoConnectionField(cls.Meta.type)

        return Query
