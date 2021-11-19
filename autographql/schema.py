import graphene
import graphql_jwt
from django.apps import apps
from graphene import relay
from graphene.utils.str_converters import to_snake_case
from rest_framework.serializers import ModelSerializer

from autographql.models import GraphQLModelBase
from autographql.mutation import DjangoSerializerMutationFieldFactory
from autographql.query import DjangoQueryFactory
from autographql.utils import get_meta
from autographql.types import AutoDjangoObjectType

ALLOWED_ACTIONS = ['retrieve', 'list', 'create', 'update', 'delete']


class RelayDjangoSerializerSchemaFactory(object):
    class Meta:
        fields = None
        node_type = None
        type_name = None
        serializer_class = None
        allowed_actions = None
        retrieve_attribute_name = None
        list_attribute_name = None
        create_attribute_name = None
        update_attribute_name = None
        delete_attribute_name = None

    @classmethod
    def build(cls):
        model = get_meta(cls.Meta, 'model', None)
        fields = get_meta(cls.Meta, 'fields', None)
        node_type = get_meta(cls.Meta, 'node_type', None)
        serializer_class = get_meta(cls.Meta, 'serializer_class', None)

        # Get model class
        if model:
            model_class = model
        elif node_type:
            model_class = node_type._meta.model
        elif serializer_class:
            model_class = serializer_class.Meta.model
        else:
            raise Exception('None of model, node_type, or serializer_class is defined.')

        model_name = model_class.__name__
        model_name_snaked = to_snake_case(model_name)
        type_name = get_meta(cls.Meta, 'type_name', model_name)
        allowed_actions = get_meta(cls.Meta, 'allowed_actions', ALLOWED_ACTIONS)
        b_retrieve_attribute_name = get_meta(cls.Meta, 'retrieve_attribute_name', model_name_snaked)
        b_list_attribute_name = get_meta(cls.Meta, 'list_attribute_name', 'list_' + model_name_snaked)
        b_create_attribute_name = get_meta(cls.Meta, 'create_attribute_name', 'create_' + model_name_snaked)
        b_update_attribute_name = get_meta(cls.Meta, 'update_attribute_name', 'update_' + model_name_snaked)
        b_delete_attribute_name = get_meta(cls.Meta, 'delete_attribute_name', 'delete_' + model_name_snaked)

        # Autogenerate Type
        if node_type:
            Type = node_type
        else:
            type_fields = fields if fields else '__all__'
            Type = type(type_name, (AutoDjangoObjectType,), {
                'Meta': type('Meta', (object,), {
                    'model': model_class,
                    'interfaces': (relay.Node,),
                    'fields': type_fields,
                })
            })

        # Autogenerate SerializerClass
        if serializer_class:
            schema_serializer_class = serializer_class
        else:
            SerializerClass = type(type_name + 'Serializer', (ModelSerializer,), {
                'Meta': type('Meta', (object,), {
                    'model': model_class,
                    'fields': '__all__',
                })
            })
            schema_serializer_class = SerializerClass

        class QueryFactory(DjangoQueryFactory):
            class Meta:
                type = Type
                retrieve = 'retrieve' in allowed_actions
                list = 'list' in allowed_actions
                retrieve_attribute_name = b_retrieve_attribute_name
                list_attribute_name = b_list_attribute_name

        class MutationFieldFactory(DjangoSerializerMutationFieldFactory):
            class Meta:
                type = Type
                serializer_class = schema_serializer_class

        CreateMutation = MutationFieldFactory.get_create_mutation()
        UpdateMutation = MutationFieldFactory.get_update_mutation()
        DeleteMutation = MutationFieldFactory.get_delete_mutation()

        class Mutation(object):
            if 'create' in allowed_actions:
                vars()[b_create_attribute_name] = CreateMutation.Field()
            if 'update' in allowed_actions:
                vars()[b_update_attribute_name] = UpdateMutation.Field()
            if 'delete' in allowed_actions:
                vars()[b_delete_attribute_name] = DeleteMutation.Field()

        return (
            Type,
            QueryFactory.build_query(),
            Mutation
        )


class SchemaGenerator(object):
    """
    Class to automagically create the schema via introspection
    """
    @classmethod
    def get_mutation(cls):
        models = apps.get_models()
        mutation_classes = []
        for model in models:
            if isinstance(model, GraphQLModelBase):
                mutation_classes.append(model._graphql_meta.mutation)
        Mutation = type('Mutation', (*mutation_classes, graphene.ObjectType,), {
            'token_auth': graphql_jwt.relay.ObtainJSONWebToken.Field(),
            'verify_token': graphql_jwt.relay.Verify.Field(),
            'refresh_token': graphql_jwt.relay.Refresh.Field(),
            'revoke_token': graphql_jwt.relay.Revoke.Field(),
        })

        return Mutation

    @classmethod
    def get_query(cls):
        models = apps.get_models()
        query_classes = []
        for model in models:
            if isinstance(model, GraphQLModelBase):
                query_classes.append(model._graphql_meta.query)

        Query = type('Query', (*query_classes, graphene.ObjectType,), {
            'node': relay.Node.Field(),
        })

        return Query

    @classmethod
    def get_schema(cls):
        Query = cls.get_query()
        Mutation = cls.get_mutation()
        schema = graphene.Schema(query=Query, mutation=Mutation)
        return schema


schema = SchemaGenerator.get_schema()
