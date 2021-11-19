from django.db.models import Prefetch


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


def merge_querysets(queryset_list):
    new_qs = None
    for qs in queryset_list:
        if new_qs is None:
            new_qs = qs
        else:
            new_qs = new_qs & qs

    return new_qs


def combine_querysets(queryset_list):
    """Recursive helper. Combines the querysets in queryset_list and recursively
        deduplicates and applies any prefetches"""
    merged_queryset = merge_querysets(queryset_list)

    # Combine duplicate prefetch types
    prefetch_list = []
    prefetch_map = {}

    for queryset in queryset_list:
        for prefetch in queryset._prefetch_related_lookups:
            if isinstance(prefetch, str):
                # String prefetch, just add it to the list
                prefetch_list.append(prefetch)
                continue

            through = prefetch.prefetch_through
            # If through is in prefetch_list as a string, remove it
            if through in prefetch_list:
                prefetch_list = list(filter(lambda p: p != through, prefetch_list))

            if through not in prefetch_map:
                prefetch_map[through] = []

            prefetch_map[through].append(prefetch.queryset)

    if not prefetch_map.items():
        # Base case, no prefetches, just returned the combined queryset
        return merged_queryset

    for through, prefetch_querysets in prefetch_map.items():
        # Has prefetches, recursive call
        prefetch_qs = combine_querysets(prefetch_querysets)
        prefetch_list.append(Prefetch(through, queryset=prefetch_qs))

    merged_queryset = merged_queryset.prefetch_related(None)
    merged_queryset = merged_queryset.prefetch_related(*prefetch_list)

    return merged_queryset
