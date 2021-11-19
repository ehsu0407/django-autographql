========================
autographql
========================

autographql is a Django app to automatically generate a GraphQL api from
Django models.

Detailed documentation is in the "docs" directory.

Features
------------------------

- Automatic optimization of querysets to prevent N+1 lookups
- Record level permissions system provided by Bridgekeeper integration
- Easily extended automatic filters based on django Lookups

Quick start
------------------------

1. Add "autographql", "graphene_django, and "bridgekeeper" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...
        'autographql',
        'graphene_django',
        'bridgekeeper',
    ]

2. Add the following settings to your settings.py::

    GRAPHENE = {
        'SCHEMA': 'autographql.schema.schema',
        'MIDDLEWARE': [
            'autographql.auth.middleware.AuthorizationMiddleware',
        ]
    }

    AUTHENTICATION_BACKENDS = [
        'bridgekeeper.backends.RulePermissionBackend',
        'django.contrib.auth.backends.ModelBackend', # this is default
    ]

3. Add the graphql URLconf in your project urls.py like this::

    path('graphql', csrf_exempt(GraphQLView.as_view(graphiql=True)), name='graphql'),

4. Write your models extending GraphQLModel instead of models.Model::

    # cookbook/ingredients/models.py
    from django.db import models
    from autographql import GraphQLModel


    class Category(GraphQLModel):
        name = models.CharField(max_length=100)

        def __str__(self):
            return self.name


    class Ingredient(GraphQLModel):
        name = models.CharField(max_length=100)
        notes = models.TextField()
        category = models.ForeignKey(Category, related_name='ingredients')

        def __str__(self):
            return self.name

5. Add some access control rules to your models::

    # cookbook/ingredients/permissions.py
    from bridgekeeper import perms
    from bridgekeeper.rules import always_allow

    from autographql.auth.utils import get_model_permission, VIEW, CREATE, UPDATE, DELETE
    from cookbook.models import Category, Ingredient

    perms[get_model_permission(Category, VIEW)] = always_allow
    perms[get_model_permission(Category, CREATE)] = always_allow
    perms[get_model_permission(Category, UPDATE)] = always_allow
    perms[get_model_permission(Category, DELETE)] = always_allow
    perms[get_model_permission(Ingredient, VIEW)] = always_allow
    perms[get_model_permission(Ingredient, CREATE)] = always_allow
    perms[get_model_permission(Ingredient, UPDATE)] = always_allow
    perms[get_model_permission(Ingredient, DELETE)] = always_allow

6. Import the permissions file in your app's ready function::

    # cookbook/ingredients/app.py
    from django.apps import AppConfig


    class IngredientsConfig(AppConfig):
        default_auto_field = 'django.db.models.BigAutoField'
        name = 'ingredients'

        def ready(self):
            # Apply permissions
            import ingredients.permissions

7. Start the development server and visit http://127.0.0.1:8000/graphql/
   to view your fully featured graphql api!

Related Projects
------------------------

- graphene (https://github.com/graphql-python/graphene)
- graphene-django (https://github.com/graphql-python/graphene-django)
- bridgekeeper (https://github.com/excitedleigh/bridgekeeper)
