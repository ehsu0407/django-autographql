import graphene
from graphql.language.ast import VariableNode, ArgumentNode, ListValueNode, ValueNode, ObjectValueNode

from autographql import types


def get_meta(meta, attribute, default):
    if hasattr(meta, attribute) and getattr(meta, attribute) is not None:
        return getattr(meta, attribute)
    else:
        return default


def get_arg_value(info, value):
    """Helper method to replace variables with values"""
    if isinstance(value, VariableNode):
        try:
            return info.variable_values[value.name.value]
        except KeyError:
            return None
    else:
        return value


def flatten_args(info, args):
    results = {}
    for arg in args:
        value = flatten_arg(info, arg)
        results.update(value)

    return results


def flatten_arg(info, arg):
    """Recursive helper function to parse args"""
    if isinstance(arg, ArgumentNode):
        return {arg.name.value: flatten_arg(info, arg.value)}
    elif isinstance(arg, VariableNode):
        try:
            return flatten_arg(info, info.variable_values[arg.name.value])
        except KeyError:
            # Variable not set
            return None
    elif isinstance(arg, list):
        values = []
        for v in arg:
            values.append(flatten_arg(info, v))
        return values
    elif isinstance(arg, graphene.InputObjectType):
        value = dict(arg)
        for k in value.keys():
            value[k] = flatten_arg(info, value[k])
        return value
    elif isinstance(arg, ObjectValueNode):
        value = {}
        for field in arg.fields:
            value[field.name.value] = flatten_arg(info, field.value)
        return value
    elif isinstance(arg, ListValueNode):
        return flatten_arg(info, arg.values)
    elif isinstance(arg, ValueNode) and hasattr(arg, 'value'):
        return flatten_arg(info, arg.value)
    else:
        # Scalar value
        return arg


def convert_arguments_to_filter_kwargs(info, arguments, filter_arg_name):
    """Converts a list of Argument objects to fields and values pairs to be used in .filter"""
    flattened_args = flatten_args(info, arguments)
    if filter_arg_name not in flattened_args or not flattened_args[filter_arg_name]:
        return None

    args = flattened_args[filter_arg_name]

    filter_kwargs = {}
    for key, input_type in types.FILTER_INPUT_TYPE_MAP.items():
        if key in args:
            for fields in args[key]:
                key = fields['expr']
                value = fields['value']
                filter_kwargs[key] = value

    return filter_kwargs


def convert_arguments_to_order_by_args(info, arguments, order_by_arg_name):
    flattened_args = flatten_args(info, arguments)
    if order_by_arg_name not in flattened_args or not flattened_args[order_by_arg_name]:
        return None

    return flattened_args[order_by_arg_name]


def to_pascal_case(string):
    return string.replace('_', ' ').title().replace(' ', '')
