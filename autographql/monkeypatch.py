from graphene_django import registry

from autographql.registry import Registry

# Monkey patch this
registry.Registry = Registry
