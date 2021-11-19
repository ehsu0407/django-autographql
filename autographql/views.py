import traceback

from django.conf import settings
from graphene_django.views import GraphQLView


class OptimizedGraphQLView(GraphQLView):
    def execute_graphql_request(self, *args, **kwargs):
        """
        By default, graphene will eat any exceptions that occur
        Extract any exceptions and echo them to console
        """
        result = super().execute_graphql_request(*args, **kwargs)
        if result and result.errors:
            for error in result.errors:
                try:
                    if hasattr(error, 'original_error'):
                        raise error.original_error
                except Exception as e:
                    if settings.DEBUG:
                        traceback.print_exc()

        return result
