from django.utils.functional import cached_property


class GraphQLOptions:
    def __init__(self, model, graphqlmeta):
        self.model = model
        self.meta = graphqlmeta

    @cached_property
    def schema_factory(self):
        from autographql.schema import RelayDjangoSerializerSchemaFactory
        return type(self.model.__name__ + 'SchemaFactory', (RelayDjangoSerializerSchemaFactory,), {
            'Meta': type('Meta', (object, ), {
                'model': self.model,
                'fields': getattr(self.meta, 'fields', None),
            })
        })

    @cached_property
    def schema_factory_output(self):
        return self.schema_factory.build()

    @property
    def node_type(self):
        return self.schema_factory_output[0]

    @property
    def query(self):
        return self.schema_factory_output[1]

    @property
    def mutation(self):
        return self.schema_factory_output[2]
