=====
autographql
=====

autographql is a Django app to automatically generate a GraphQL api from
Django models.

Detailed documentation is in the "docs" directory.

Features
-----------

- Record level permissions system provided by Bridgekeeper integration
- Easily extended automatic filters based on django Lookups
- Automatic optimization of querysets to prevent the N+1 lookups problem

Quick start
-----------

1. Add "autographql" to your INSTALLED_APPS setting like this::

    INSTALLED_APPS = [
        ...
        'autographql',
    ]

2. Add the graphql URLconf in your project urls.py like this::

    path('graphql', csrf_exempt(GraphQLView.as_view(graphiql=True)), name='graphql'),

3. Write your models extending GraphQLModel instead of models.Model

4. Start the development server and visit http://127.0.0.1:8000/graphql/
   to view your fully featured graphql api!
