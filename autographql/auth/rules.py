from bridgekeeper.rules import Attribute, Is, Relation as _Relation, ManyRelation as _ManyRelation, UNIVERSAL, EMPTY


def is_rule(f):
    return Is(f)


def attribute_rule(attr):
    def wrapper(matches, repr_string=None):
        return Attribute(attr, matches)
    return wrapper


class Relation(_Relation):
    def check(self, user, instance=None):
        if not hasattr(instance, self.attr):
            return False
        return super(Relation, self).check(user, instance)


class ManyRelation(_ManyRelation):
    def check(self, user, instance=None):
        if instance is None:
            return self.rule.check(user, None)
        attr = instance.__class__._meta.get_field(self.query_attr,).get_accessor_name()
        related_manager = getattr(instance, attr)

        qs = related_manager.get_queryset()
        if qs._prefetch_done:
            # Data already cached, we should use it
            for value in qs:
                if self.rule.check(user, value):
                    return True
            return False

        related_q = self.rule.query(user)
        if related_q is UNIVERSAL or related_q is EMPTY:
            return related_q
        return related_manager.filter(related_q).exists()
