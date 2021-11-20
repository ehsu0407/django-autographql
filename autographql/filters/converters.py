from enum import Enum
from functools import singledispatch

import graphene
from django.core.exceptions import ImproperlyConfigured
from django.db.models import lookups
from django.db.models.functions import ExtractYear, ExtractMonth, ExtractDay, ExtractWeekDay, ExtractIsoWeekDay, \
    ExtractWeek, ExtractIsoYear, ExtractQuarter, ExtractHour, ExtractMinute, ExtractSecond, TruncDate, TruncTime
from graphene import Int
from graphene_django.converter import convert_django_field, convert_field_to_boolean, convert_field_to_string, \
    get_django_field_description, convert_field_to_int, convert_date_to_string, convert_time_to_string


def get_lookup_name(lookup):
    return lookup.lookup_name


def convert_lookup(converter, lookup, field):
    converted = converter(field)
    cls = converted.__class__
    name = get_lookup_name(lookup)
    return name, cls(
        description=get_django_field_description(field),
        required=False,
    )


@singledispatch
def get_input_type_from_lookup(lookup, field):
    raise ImproperlyConfigured(
        "Don't know how to convert the lookup %s (%s) "
        "to Graphene type" % (lookup, lookup.__class__)
    )


@get_input_type_from_lookup.register(lookups.In)
def convert_lookup_to_list_field_type(lookup, field):
    return get_lookup_name(lookup), graphene.List(
        of_type=convert_django_field(field).__class__,
        description=get_django_field_description(field),
        required=False,
    )


@get_input_type_from_lookup.register(TruncDate)
def convert_lookup_to_date(lookup, field):
    return convert_lookup(convert_date_to_string, lookup, field)


@get_input_type_from_lookup.register(TruncTime)
def convert_lookup_to_date(lookup, field):
    return convert_lookup(convert_time_to_string, lookup, field)


@get_input_type_from_lookup.register(lookups.YearExact)
@get_input_type_from_lookup.register(lookups.YearGt)
@get_input_type_from_lookup.register(lookups.YearGte)
@get_input_type_from_lookup.register(lookups.YearLt)
@get_input_type_from_lookup.register(lookups.YearLte)
@get_input_type_from_lookup.register(ExtractMonth)
@get_input_type_from_lookup.register(ExtractDay)
@get_input_type_from_lookup.register(ExtractWeekDay)
@get_input_type_from_lookup.register(ExtractIsoWeekDay)
@get_input_type_from_lookup.register(ExtractWeek)
@get_input_type_from_lookup.register(ExtractQuarter)
@get_input_type_from_lookup.register(ExtractHour)
@get_input_type_from_lookup.register(ExtractMinute)
@get_input_type_from_lookup.register(ExtractSecond)
def convert_lookup_to_int(lookup, field):
    return get_lookup_name(lookup), Int(required=False)


# def convert_lookup_to_week_day(lookup, field):
#     return get_lookup_name(lookup), Enum(
#         'WeekDay', [
#             ('Sunday', 1),
#             ('Monday', 2),
#             ('Tuesday', 3),
#             ('Wednesday', 4),
#             ('Thursday', 5),
#             ('Friday', 6),
#             ('Saturday', 7),
#         ],
#     )


@get_input_type_from_lookup.register(lookups.IsNull)
def convert_lookup_to_boolean(lookup, field):
    return convert_lookup(convert_field_to_boolean, lookup, field)


@get_input_type_from_lookup.register(lookups.Regex)
@get_input_type_from_lookup.register(lookups.IRegex)
def convert_lookup_to_string(lookup, field):
    return convert_lookup(convert_field_to_string, lookup, field)


@get_input_type_from_lookup.register(lookups.Exact)
@get_input_type_from_lookup.register(lookups.IExact)
@get_input_type_from_lookup.register(lookups.GreaterThan)
@get_input_type_from_lookup.register(lookups.GreaterThanOrEqual)
@get_input_type_from_lookup.register(lookups.IntegerGreaterThanOrEqual)
@get_input_type_from_lookup.register(lookups.IntegerLessThan)
@get_input_type_from_lookup.register(lookups.LessThan)
@get_input_type_from_lookup.register(lookups.LessThanOrEqual)
@get_input_type_from_lookup.register(lookups.Contains)
@get_input_type_from_lookup.register(lookups.IContains)
@get_input_type_from_lookup.register(lookups.StartsWith)
@get_input_type_from_lookup.register(lookups.IStartsWith)
@get_input_type_from_lookup.register(lookups.EndsWith)
@get_input_type_from_lookup.register(lookups.IEndsWith)
@get_input_type_from_lookup.register(lookups.Range)
def convert_lookup_to_field_type(lookup, field):
    return convert_lookup(convert_django_field, lookup, field)
