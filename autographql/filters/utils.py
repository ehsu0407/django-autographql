from graphene_django.registry import get_global_registry


def get_input_type(field):
    registry = get_global_registry()
    related_model = field.related_model
    model_type = registry.get_type_for_model(related_model)
    return model_type._meta.filter_input_type
