import graphene


NOT = 'NOT'
AND = 'AND'
OR = 'OR'


class LookupInputField(graphene.InputField):
    def __init__(self, lookup_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookup_class = lookup_class


class LogicalInputField(graphene.List):
    @classmethod
    def get_operator(cls):
        raise NotImplementedError


class LogicalAndInputField(LogicalInputField):
    @classmethod
    def get_operator(cls):
        return AND


class LogicalOrInputField(LogicalInputField):
    @classmethod
    def get_operator(cls):
        return OR


class LogicalNotInputField(LogicalInputField):
    @classmethod
    def get_operator(cls):
        return NOT
