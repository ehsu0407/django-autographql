from django.db import models
from django.db.models.base import ModelBase
from autographql.managers import AuthModelManager
from autographql.options import GraphQLOptions


class GraphQLModelBase(ModelBase):
    def __new__(cls, name, bases, attrs, **kwargs):
        model = super().__new__(cls, name, bases, attrs, **kwargs)
        if model._meta.abstract:
            return model

        attr_graphql_meta = attrs.pop('GraphQLMeta', None)
        model.add_to_class('_graphql_meta', GraphQLOptions(
            model,
            attr_graphql_meta,
        ))

        return model


class GraphQLModel(models.Model, metaclass=GraphQLModelBase):
    """
    Abstract base model for all models
    """
    _graphql_meta: GraphQLOptions = None
    # Default to a custom model manager that has a for_user field
    objects = AuthModelManager()

    class Meta:
        abstract = True
