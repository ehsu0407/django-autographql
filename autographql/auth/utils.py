VIEW = 'view'
CREATE = 'create',
UPDATE = 'update',
DELETE = 'delete'

permission_map = {
    VIEW: '%(app_label)s.view_%(model_name)s',
    CREATE: '%(app_label)s.add_%(model_name)s',
    UPDATE: '%(app_label)s.change_%(model_name)s',
    DELETE: '%(app_label)s.delete_%(model_name)s',
}


def get_model_permission(model, type):
    kwargs = {
        'app_label': model._meta.app_label,
        'model_name': model._meta.model_name
    }
    return permission_map[type] % kwargs
