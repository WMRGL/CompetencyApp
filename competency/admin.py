from django.contrib import admin
from competency.models import *

class CompetenciesAdmin(admin.ModelAdmin):
    model = Competencies

admin.site.register(Competencies, CompetenciesAdmin)

