from graphene_django.registry import Registry as _Registry


class Registry(_Registry):
    def __init__(self):
        super(Registry, self).__init__()
        self.serializer_create_input_registry = {}
        self.serializer_update_input_registry = {}

    def register_serializer_create_input_field(self, field, converted):
        self.serializer_create_input_registry[field] = converted

    def register_serializer_update_input_field(self, field, converted):
        self.serializer_update_input_registry[field] = converted

    def get_serializer_create_input_field(self, field):
        return self.serializer_create_input_registry.get(field)

    def get_serializer_update_input_field(self, field):
        return self.serializer_update_input_registry.get(field)
