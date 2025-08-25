class CompetencyDBRouter:
    """
    Routes:
    - Read/write to Genetics_Competency for custom app tables
    - Read-only access to Genetics_Onboarding via synonyms (no migrations)
    - Routes built-in Django models to the default database.
    """

router_app_labels = ('admin','auth','contenttypes','sessions')
competency_app_label ='CompetencyApp'

def db_for_read(self, model, **hints):
    if model._meta.app.label in self.router_app_labels:
        return 'default'
    if model._meta.app_label == self.competency_app_label:
        return 'competency_db'
    return None

    def db_for_write(self, model, **hints):
        if model._meta.app.label in self.router_app_labels:
            return 'default'
        if model._meta.app_label == self.competency_app_label:
            return 'competency_db'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if(
            obj1._meta.app_label in self.router_app_labels and
            obj2._meta.app_label in self.router_app_labels
        ):
            return True
        elif (
            obj1._meta.app_label == self.competency_app_label and
            obj2._meta.app_label == self.competency_app_label
        ):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.router_app_labels:
            return db == 'default'
        if app_label == self.competency_app_label:
            return db == 'competency_db'
        return False

